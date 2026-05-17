"""
US Data Center Construction Spending integration for the credit digest.

Pulls monthly private data center construction spending from Our World in Data,
which mirrors the US Census Bureau Value of Construction Put in Place Survey (VIP)
data with monthly updates and a clean CSV interface.

WHY OWID INSTEAD OF CENSUS DIRECT:
The Census Bureau's VIP timeseries API requires a category_code parameter that
isn't publicly documented for the data center subcategory. We tried five plausible
candidates (p001ofdc, p001ofd, p99dc, private_data_center, p001dc) and all returned
JSON errors. Rather than continuing to guess, we use OWID's CSV mirror which
publishes the same underlying Census data with a stable, documented URL.

DATA DETAIL:
OWID applies an inflation adjustment using the BLS Producer Price Index for new
office building construction. Values are in constant 2021 US dollars rather than
nominal dollars. This means absolute values are slightly lower than headline
Census figures, but the trajectory and inflection points are identical. The chart
in the dashboard notes "real terms" so the difference is transparent.

Source chain: US Census Bureau VIP -> OWID processing (PPI adjustment) -> CSV
Update cadence: monthly, ~6 weeks after the reference month
License: CC BY 4.0 (cite OWID + Census)

Public function (interface unchanged from prior version):
    fetch_data_center_construction(cache_path='data_center_cache.json',
                                   force_refresh=False, api_key=None)
      -> (data_dict, warnings_list, metadata_dict)

Returned data_dict structure (also unchanged):
    {
      "series": [
        {"period": "2014-01", "value": 776.0},
        ...
        {"period": "2026-03", "value": 3775.0},
      ],
      "latest": {"period": "2026-03", "value": 3775.0},
      "yoy_pct": 22.0,
      "mom_change": 89.0,
      "three_month_avg_mom": 99.0,
      "five_year_growth_pct": 387.0,
      "_source": "Our World in Data (Census Bureau VIP + BLS PPI)",
      "_fetched_at": "...",
      "_last_full_refresh": "..."
    }
"""

import json
import os
import time
import urllib.request
import urllib.error
import csv
import io
from datetime import datetime, timezone

# Cache TTL: OWID updates monthly, daily cache check is plenty
CACHE_TTL_HOURS = 24

# OWID CSV URL for monthly US data center construction spending
OWID_CSV_URL = (
    "https://ourworldindata.org/grapher/monthly-spending-data-center-us.csv"
    "?v=1&csvType=full&useColumnShortNames=false"
)

# OWID metadata URL (for reference, not used in critical path)
OWID_METADATA_URL = (
    "https://ourworldindata.org/grapher/monthly-spending-data-center-us.metadata.json"
    "?v=1&csvType=full&useColumnShortNames=false"
)

# OWID asks data fetchers to identify themselves. They specifically request
# this User-Agent format in their documentation.
OWID_USER_AGENT = "Our World In Data data fetch/1.0"


def _http_get_text(url, retries=3, sleep=0.8):
    """Fetch URL contents as text with retry on 429/5xx."""
    req = urllib.request.Request(url, headers={
        "Accept": "text/csv, application/json, */*",
        "User-Agent": OWID_USER_AGENT,
    })
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8")
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
            print(f"  OWID HTTP {e.code} on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  OWID fetch error: {last_err}")
            time.sleep(sleep)
    print(f"  OWID fetch failed after {retries} attempts: {last_err}")
    return None


def _parse_csv(text):
    """
    Parse OWID CSV. Expected columns:
      Entity,Code,Year,<indicator column name>

    The "Year" column encoding is one of:
      (a) Calendar year (e.g. 2014, 2015) — annual data
      (b) YYYY-MM-DD or YYYY-MM string — string date
      (c) Days since some epoch (commonly 2020-01-21 for OWID monthly grapher data)
      (d) Days since 1900-01-01 (Excel/Lotus convention)

    We try each strategy and pick whichever produces dates between 2010 and 2030
    (a sanity window for this series, which runs 2014-present).

    Returns list of {period: 'YYYY-MM', value: float} sorted chronological.
    """
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        return []

    # Identify the time column. OWID grapher CSVs use one of: "Year" (annual data),
    # "Day" (sub-annual data with YYYY-MM-DD strings), "Date", or similar.
    time_col = None
    for candidate in ("Day", "Year", "Date", "Month"):
        if candidate in fieldnames:
            time_col = candidate
            break
    if not time_col:
        print(f"  OWID CSV no recognizable time column. Fieldnames: {fieldnames}")
        return []
    # Identify the value column: not Entity/Code and not the time column.
    standard_cols = {"Entity", "Code", time_col}
    value_cols = [c for c in fieldnames if c not in standard_cols]
    if not value_cols:
        print(f"  OWID CSV unexpected schema. Fieldnames: {fieldnames}")
        return []
    value_col = value_cols[0]
    print(f"  OWID time column: '{time_col}', value column: '{value_col}'")

    # Collect raw rows first
    raw_rows = list(reader)
    if not raw_rows:
        return []

    from datetime import date, timedelta

    def try_decode_year(year_raw):
        """Return a date object or None if decode fails."""
        if not year_raw:
            return None
        s = str(year_raw).strip()
        # Strategy 1: YYYY-MM-DD or YYYY-MM string
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                return datetime.strptime(s, fmt).date()
            except (ValueError, TypeError):
                continue
        # Strategy 2: integer
        try:
            n = int(s)
        except (ValueError, TypeError):
            return None
        # Try multiple epochs and pick whichever produces a date in our window
        candidates = [
            ("calendar_year", lambda x: date(x, 6, 15) if 1900 <= x <= 2100 else None),
            ("owid_epoch_2020_01_21", lambda x: date(2020, 1, 21) + timedelta(days=x)),
            ("excel_1900_01_01",     lambda x: date(1900, 1, 1) + timedelta(days=x)),
            ("unix_epoch_1970",      lambda x: date(1970, 1, 1) + timedelta(days=x)),
        ]
        for _name, fn in candidates:
            try:
                d = fn(n)
            except (OverflowError, ValueError, TypeError):
                continue
            if d and date(2010, 1, 1) <= d <= date(2035, 12, 31):
                return d
        return None

    # Sample first 5 rows to identify the right time encoding, log the choice
    sample_decoded = []
    for row in raw_rows[:5]:
        d = try_decode_year(row.get(time_col, ""))
        if d:
            sample_decoded.append((row.get(time_col, ""), d))
    if sample_decoded:
        print(f"  OWID time decode sample: {sample_decoded[0][0]} -> {sample_decoded[0][1].strftime('%Y-%m-%d')}")

    # Detect whether values are in raw dollars or millions of dollars by checking
    # the magnitude of the first valid value. Values >= 1,000,000 are raw dollars
    # (OWID's default for this series); values < 100,000 are already in $M.
    scale_divisor = 1.0
    for row in raw_rows[:10]:
        val_raw = row.get(value_col, "")
        try:
            v = float(val_raw)
            if v >= 1_000_000:
                scale_divisor = 1_000_000.0
                print(f"  OWID values appear to be in raw dollars; dividing by 1M to get $M")
            break
        except (ValueError, TypeError):
            continue

    rows = []
    for row in raw_rows:
        time_raw = row.get(time_col, "")
        val_raw = row.get(value_col, "")
        d = try_decode_year(time_raw)
        if not d:
            continue
        try:
            val = float(val_raw) / scale_divisor
        except (ValueError, TypeError):
            continue
        period = d.strftime("%Y-%m")
        rows.append({"period": period, "value": val})

    # Dedupe by period (last write wins)
    by_period = {}
    for r in rows:
        by_period[r["period"]] = r["value"]
    out = [{"period": p, "value": v} for p, v in by_period.items()]
    out.sort(key=lambda r: r["period"])
    return out


def _compute_derived_metrics(series):
    """Given a sorted (oldest first) series, compute KPI fields."""
    if not series:
        return {}
    latest = series[-1]
    metrics = {"latest": latest}

    if len(series) >= 2:
        prev = series[-2]
        metrics["mom_change"] = round(latest["value"] - prev["value"], 1)

    deltas = []
    for i in range(max(1, len(series) - 3), len(series)):
        deltas.append(series[i]["value"] - series[i - 1]["value"])
    if deltas:
        metrics["three_month_avg_mom"] = round(sum(deltas) / len(deltas), 1)

    if len(series) >= 13:
        yoy_base = series[-13]
        if yoy_base["value"] > 0:
            metrics["yoy_pct"] = round(
                (latest["value"] - yoy_base["value"]) / yoy_base["value"] * 100, 1
            )

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
        print(f"WARNING: failed to write OWID cache: {e}")


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
    Pull monthly US data center construction spending from Our World in Data.

    Args:
      cache_path: where to read/write the cache JSON
      force_refresh: bypass cache freshness check
      api_key: unused (kept for interface compatibility with prior version)

    Returns:
      data_dict, warnings_list, metadata_dict

    On failure: returns empty dict + warning rather than raising. Dashboard
    will show the placeholder. Stale cache (if present) is used as fallback.
    """
    _ = api_key  # accepted for backwards compatibility, not used by OWID
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "rows_returned": 0,
    }

    cache = _load_cache(cache_path)
    if cache and _cache_is_fresh(cache) and not force_refresh:
        print(f"OWID Data Center: cache fresh ({cache.get('_fetched_at')}); using cached data.")
        metadata["from_cache"] = True
        metadata["rows_returned"] = len(cache.get("series", []))
        return cache, [], metadata

    print("OWID Data Center: cache stale or force refresh, pulling fresh CSV...")
    text = _http_get_text(OWID_CSV_URL)
    if not text:
        msg = "OWID CSV fetch failed"
        print(f"WARNING: {msg}")
        if cache:
            print("OWID Data Center: falling back to stale cache.")
            metadata["from_cache"] = True
            metadata["rows_returned"] = len(cache.get("series", []))
            return cache, [msg + "; using stale cache"], metadata
        return {}, [msg], metadata

    series = _parse_csv(text)
    if not series:
        msg = "OWID CSV downloaded but no parseable rows found"
        print(f"WARNING: {msg}")
        # Show first 200 chars of response for diagnostics
        print(f"  CSV preview: {text[:200]!r}")
        if cache:
            print("OWID Data Center: falling back to stale cache.")
            metadata["from_cache"] = True
            metadata["rows_returned"] = len(cache.get("series", []))
            return cache, [msg + "; using stale cache"], metadata
        return {}, [msg], metadata

    derived = _compute_derived_metrics(series)

    payload = {
        "series": series,
        **derived,
        "_source": "Our World in Data (Census Bureau VIP + BLS PPI inflation adjustment)",
        "_unit": "constant 2021 US$ millions",
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_last_full_refresh": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    _save_cache(cache_path, payload)
    latest_period = derived.get("latest", {}).get("period", "n/a")
    latest_value = derived.get("latest", {}).get("value", 0)
    print(f"OWID Data Center: refresh complete. {len(series)} monthly observations, "
          f"latest = {latest_period} = ${latest_value:,.1f}M (constant 2021$)")

    metadata["rows_returned"] = len(series)
    return payload, [], metadata
