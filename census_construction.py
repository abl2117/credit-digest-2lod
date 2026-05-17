"""
US Census Bureau Construction Spending integration for the credit digest.

Pulls monthly private data center construction spending from the Value of
Construction Put in Place (VIP) timeseries API. Free, no API key required for
moderate usage, no FRED dependency.

The Census Bureau began breaking out data centers as a separate category under
"private office" in July 2024, with history extending back to January 2014.
The C30 report releases on the first business day of each month covering data
roughly 6 weeks back (e.g., May release covers March data).

Public function:
    fetch_data_center_construction(cache_path='data_center_cache.json',
                                   force_refresh=False, api_key=None)
      -> (data_dict, warnings_list, metadata_dict)

Returned data_dict structure:
    {
      "series": [
        {"period": "2014-01", "value": 776.0},
        {"period": "2014-02", "value": 753.0},
        ...
        {"period": "2026-03", "value": 3775.0},
      ],
      "latest": {"period": "2026-03", "value": 3775.0},
      "yoy_pct": 22.0,
      "mom_change": 89.0,
      "three_month_avg_mom": 99.0,
      "five_year_growth_pct": 387.0,
      "_source": "US Census Bureau VIP",
      "_category_code": "...",
      "_fetched_at": "..."
    }
"""

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

# Cache TTL: Census releases monthly, daily cache check is plenty
CACHE_TTL_HOURS = 24

# VIP endpoint. Series prefix is "vip" under the EITS timeseries namespace.
VIP_ENDPOINT = "https://api.census.gov/data/timeseries/eits/vip"

# Candidate category codes for private data center construction. The Census
# Bureau's coding scheme for VIP follows a pattern like "p001ofdc" where:
#   p = private, 001 = total, of = office, dc = data center
# Different documentation sources show slightly different codes; we walk the
# candidate list and accept the first that returns rows. On success the code
# is cached so subsequent runs skip the discovery step.
CATEGORY_CODE_CANDIDATES = [
    "p001ofdc",   # private, total, office subcategory, data center
    "p001ofd",
    "p99dc",
    "private_data_center",
    "p001dc",
]

# Data type code for the Seasonally Adjusted Annual Rate value column. VIP
# publishes both SAAR and not-seasonally-adjusted versions; SAAR is the
# headline figure used in Census press releases and equivalent to what FRED
# publishes for office and commercial subcategories.
DATA_TYPE_SAAR = "VIP"


def _http_get_json(url, retries=3, sleep=0.5):
    """Lightweight GET with retry on 429/5xx."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Credit Digest Personal Research",
    })
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(sleep * (2 ** attempt))
                continue
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
                last_err += f" body={body}"
            except Exception:
                pass
            print(f"  Census HTTP {e.code} on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  Census fetch error: {last_err}")
            time.sleep(sleep)
    print(f"  Census fetch failed after {retries} attempts: {last_err}")
    return None


def _build_query(category_code, time_range, api_key=None):
    """Build a VIP query URL."""
    params = {
        "get": "cell_value,data_type_code,time_slot_id,time,category_code,seasonally_adj",
        "category_code": category_code,
        "time": time_range,
    }
    if api_key:
        params["key"] = api_key
    return f"{VIP_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _try_category_codes(time_range, api_key=None):
    """
    Walk candidate category codes. Return (rows, code) for the first that
    yields data. The rows are the raw JSON array from the API.
    """
    for code in CATEGORY_CODE_CANDIDATES:
        url = _build_query(code, time_range, api_key)
        rows = _http_get_json(url)
        time.sleep(0.2)
        if rows and isinstance(rows, list) and len(rows) > 1:
            print(f"  Census: category_code={code} returned {len(rows)-1} rows")
            return rows, code
    return None, None


def _parse_rows(rows):
    """
    Convert Census API JSON array response into structured records.
    First row is headers, subsequent rows are values.
    """
    if not rows or len(rows) < 2:
        return []
    headers = rows[0]
    out = []
    for row in rows[1:]:
        rec = dict(zip(headers, row))
        # Parse cell_value as float; skip rows with non-numeric values
        try:
            val = float(rec.get("cell_value", "").replace(",", ""))
        except (ValueError, TypeError, AttributeError):
            continue
        # Filter to seasonally adjusted values only (matches Census press releases)
        adj = str(rec.get("seasonally_adj", "")).lower()
        if adj not in ("yes", "y", "true", "1"):
            continue
        period = rec.get("time", "")
        if not period:
            continue
        out.append({"period": period, "value": val})
    # Sort chronological
    out.sort(key=lambda r: r["period"])
    return out


def _compute_derived_metrics(series):
    """
    Given a sorted (oldest first) list of {period, value}, compute the
    derived KPI fields used by the dashboard tile row.
    """
    if not series:
        return {}
    latest = series[-1]
    metrics = {"latest": latest}

    # MoM change
    if len(series) >= 2:
        prev = series[-2]
        metrics["mom_change"] = round(latest["value"] - prev["value"], 1)

    # 3-month avg MoM (last 3 monthly deltas)
    deltas = []
    for i in range(max(1, len(series) - 3), len(series)):
        deltas.append(series[i]["value"] - series[i - 1]["value"])
    if deltas:
        metrics["three_month_avg_mom"] = round(sum(deltas) / len(deltas), 1)

    # YoY % (12 months back)
    if len(series) >= 13:
        yoy_base = series[-13]
        if yoy_base["value"] > 0:
            metrics["yoy_pct"] = round(
                (latest["value"] - yoy_base["value"]) / yoy_base["value"] * 100, 1
            )

    # 5-year growth (60 months back)
    if len(series) >= 61:
        base = series[-61]
        if base["value"] > 0:
            metrics["five_year_growth_pct"] = round(
                (latest["value"] - base["value"]) / base["value"] * 100, 1
            )

    return metrics


def _load_cache(cache_path):
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(cache_path, data):
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"WARNING: failed to write Census cache: {e}")


def _cache_is_fresh(cache):
    if not cache:
        return False
    last = cache.get("_fetched_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
        if age_hours >= CACHE_TTL_HOURS:
            return False
    except Exception:
        return False
    return bool(cache.get("series"))


def fetch_data_center_construction(cache_path="data_center_cache.json",
                                   force_refresh=False, api_key=None):
    """
    Pull monthly US private data center construction spending from Census VIP.

    Args:
      cache_path: where to read/write the cache JSON
      force_refresh: bypass cache freshness check
      api_key: optional Census API key (raises rate limit beyond 500/day)

    Returns:
      data_dict, warnings_list, metadata_dict

    Behavior on failure: returns empty dict + warning rather than raising,
    so the dashboard degrades gracefully (chart shows "data unavailable").
    """
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "rows_returned": 0,
    }

    if api_key is None:
        api_key = os.environ.get("CENSUS_API_KEY")

    cache = _load_cache(cache_path)
    if cache and _cache_is_fresh(cache) and not force_refresh:
        print(f"Census: cache fresh ({cache.get('_fetched_at')}); using cached data.")
        metadata["from_cache"] = True
        metadata["rows_returned"] = len(cache.get("series", []))
        return cache, [], metadata

    print("Census: cache stale or force refresh, pulling fresh data...")

    # Pull from 2014 (when data centers were first broken out) to present.
    # The 'from YYYY' syntax is documented in Census EITS examples.
    time_range = "from+2014"

    rows, used_code = _try_category_codes(time_range, api_key)
    if not rows:
        msg = "Census API returned no data for any candidate category_code"
        print(f"WARNING: {msg}. Tried: {CATEGORY_CODE_CANDIDATES}")
        if cache:
            print("Census: falling back to stale cache.")
            metadata["from_cache"] = True
            metadata["rows_returned"] = len(cache.get("series", []))
            return cache, [msg + "; using stale cache"], metadata
        return {}, [msg], metadata

    series = _parse_rows(rows)
    if not series:
        msg = "Census API returned rows but none were parseable (likely all unadjusted)"
        print(f"WARNING: {msg}")
        return {}, [msg], metadata

    derived = _compute_derived_metrics(series)

    payload = {
        "series": series,
        **derived,
        "_source": "US Census Bureau VIP",
        "_category_code": used_code,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_last_full_refresh": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    _save_cache(cache_path, payload)
    print(f"Census: refresh complete. {len(series)} monthly observations, "
          f"latest = {derived.get('latest', {}).get('period', 'n/a')} = "
          f"${derived.get('latest', {}).get('value', 0):,.1f}M")

    metadata["rows_returned"] = len(series)
    return payload, [], metadata
