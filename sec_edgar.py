"""
US Census Bureau Value in Place (VIP) construction spending integration.

Pulls the monthly Construction Put in Place series for the data center category
and adjacent categories (power, office, commercial, manufacturing) that provide
context for evaluating credit exposure in the data center and broader CRE space.

Public functions:
    fetch_construction_data(cache_path='construction_cache.json', force_refresh=False)
      -> (construction_dict, warnings_list, metadata_dict)

The Census API is free; an API key is recommended but not required for low-volume use.
Register at https://api.census.gov/data/key_signup.html and set CENSUS_API_KEY as a
GitHub secret. Without a key the API throttles after ~500 calls/day; we make ~10/day.

Data source: US Census Bureau, Value of Construction Put in Place Survey (VIP).
The data center category was broken out from "office" starting in January 2014.

Returned structure:
    {
      "data_center": {
        "value": 3940.0,           # latest monthly value, $M
        "as_of": "2026-01",        # YYYY-MM
        "prior_value": 3851.0,
        "prior_as_of": "2025-12",
        "change": 89.0,
        "change_pct": 2.3,
        "yoy_change": 856.0,
        "yoy_change_pct": 27.7,
        "ttm_total": 39400.0,      # trailing 12-month total
        "history": [
          {"date": "2026-01", "value": 3940.0},
          ...
        ],
        "_category_code": "DATACEN",
        "_units": "$M",
        "_seasonal": "Not Seasonally Adjusted",
        "_fetched_at": "2026-05-16T..."
      },
      "power": {...},
      "office": {...},
      ...
    }
"""

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

# Cache freshness: VIP is monthly so a 12-hour TTL is fine
CACHE_TTL_HOURS = 12

CENSUS_VIP_URL = "https://api.census.gov/data/timeseries/eits/vip"

# Categories to track. Each entry: (key, census category_code, label, history_months)
# The Census category_code for data centers was added in 2024 when the category was
# formally split out from office. Pattern matches the FRED naming convention
# (TLPWRCON for power, TLOFCONS for office, etc.). We attempt the most likely code
# first; if it returns nothing on the first fetch, run with FORCE_DISCOVERY=True
# below to enumerate available codes.
CATEGORIES = [
    ("data_center",   "DATACEN",  "Data Center Construction",    36),
    ("power",         "PWR",      "Power Construction",          36),
    ("office",        "OFFICE",   "Office Construction",         36),
    ("commercial",    "COMM",     "Commercial Construction",     36),
    ("manufacturing", "MFG",      "Manufacturing Construction",  36),
    ("total_private", "TLPRV",    "Total Private Construction",  36),
    ("total",         "TLCON",    "Total Construction",          36),
]

# We want private, not seasonally adjusted, monthly values.
# data_type_code conventions:
#   TOTAL = total spending
#   PRV   = private only
#   PUB   = public only
# seasonally_adj: yes / no
DATA_TYPE_CODE = "PRV"
SEASONALLY_ADJ = "no"

# Set to True on first run to enumerate available category codes if the defaults
# above return no data. The module logs all category codes it finds so you can
# update the CATEGORIES table.
FORCE_DISCOVERY = False


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _http_get_json(url, retries=3, sleep=0.5):
    """Lightweight GET with retry on transient failures."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Credit Digest Personal Research",
    })
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(sleep * (2 ** attempt))
                continue
            if e.code in (400, 404):
                try:
                    body = e.read().decode("utf-8", errors="replace")[:300]
                    last_err += f" body={body}"
                except Exception:
                    pass
                print(f"  Census HTTP {e.code} on {url}: {last_err}")
                return None
            print(f"  Census HTTP error on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  Census fetch error on {url}: {last_err}")
            time.sleep(sleep)
    print(f"  Census fetch failed after {retries} attempts: {last_err}")
    return None


# ---------------------------------------------------------------------------
# Category discovery
# ---------------------------------------------------------------------------

def _discover_categories(api_key=None, lookback_months=3):
    """
    Hit the VIP endpoint without a category_code filter and enumerate all codes
    that come back. Useful when the expected DATACEN code doesn't match and we
    need to find the actual code Census assigned.
    """
    end = datetime.now().date().replace(day=1) - timedelta(days=1)
    start_month = end - timedelta(days=lookback_months * 31)
    time_param = f"from {start_month.strftime('%Y-%m')} to {end.strftime('%Y-%m')}"

    params = {
        "get": "category_code,data_type_code,cell_value,seasonally_adj",
        "time": time_param,
        "for": "us:*",
        "seasonally_adj": SEASONALLY_ADJ,
    }
    if api_key:
        params["key"] = api_key
    url = CENSUS_VIP_URL + "?" + urllib.parse.urlencode(params)

    data = _http_get_json(url)
    if not data or len(data) < 2:
        return []

    # First row is headers
    headers = data[0]
    cat_idx = headers.index("category_code") if "category_code" in headers else None
    if cat_idx is None:
        return []

    codes = set()
    for row in data[1:]:
        if cat_idx < len(row):
            codes.add(row[cat_idx])
    return sorted(codes)


# ---------------------------------------------------------------------------
# Single-category fetch
# ---------------------------------------------------------------------------

def _fetch_category(category_code, history_months, api_key=None):
    """
    Fetch a single Census VIP category. Returns list of {date, value} newest-first,
    or None on failure.
    """
    end = datetime.now().date()
    # Pull ~3 years for YoY and TTM headroom
    start = end - timedelta(days=3 * 365 + 60)
    time_param = f"from {start.strftime('%Y-%m')} to {end.strftime('%Y-%m')}"

    params = {
        "get": "cell_value,time_slot_id,time_slot_name,data_type_code,category_code",
        "time": time_param,
        "category_code": category_code,
        "data_type_code": DATA_TYPE_CODE,
        "seasonally_adj": SEASONALLY_ADJ,
        "for": "us:*",
    }
    if api_key:
        params["key"] = api_key
    url = CENSUS_VIP_URL + "?" + urllib.parse.urlencode(params)

    data = _http_get_json(url)
    if not data or len(data) < 2:
        return None

    headers = data[0]
    val_idx = headers.index("cell_value") if "cell_value" in headers else None
    time_idx = None
    # Census returns time as the "time" field added to the row tail by some
    # endpoints, or as time_slot_name. Locate whatever date-like header we have.
    for key in ("time", "time_slot_name", "time_slot_date"):
        if key in headers:
            time_idx = headers.index(key)
            break
    if val_idx is None or time_idx is None:
        return None

    obs = []
    for row in data[1:]:
        if val_idx >= len(row) or time_idx >= len(row):
            continue
        raw_val = row[val_idx]
        raw_time = row[time_idx]
        if raw_val in (None, "", "."):
            continue
        # Normalize date to YYYY-MM
        date_str = _normalize_date(raw_time)
        if not date_str:
            continue
        try:
            obs.append({"date": date_str, "value": float(raw_val)})
        except (TypeError, ValueError):
            continue

    if not obs:
        return None

    # Dedupe by date (some endpoints return multiple rows for same period) and
    # sort newest-first
    by_date = {}
    for o in obs:
        by_date[o["date"]] = o
    deduped = list(by_date.values())
    deduped.sort(key=lambda x: x["date"], reverse=True)
    return deduped[:history_months]


def _normalize_date(raw):
    """Census returns dates in various formats; normalize to YYYY-MM."""
    if not raw:
        return None
    raw = str(raw).strip()
    # Try YYYY-MM directly
    if len(raw) >= 7 and raw[4] == "-":
        return raw[:7]
    # Try YYYY-MM-DD
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:7]
    # Try MMM-YYYY (e.g. "Jan-2026")
    try:
        dt = datetime.strptime(raw, "%b-%Y")
        return dt.strftime("%Y-%m")
    except ValueError:
        pass
    try:
        dt = datetime.strptime(raw, "%B %Y")
        return dt.strftime("%Y-%m")
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_metrics(observations):
    """
    Convert raw monthly observations (newest-first) into dashboard metrics.
    Returns dict or None if insufficient data.
    """
    if not observations:
        return None

    latest = observations[0]
    prior = observations[1] if len(observations) > 1 else None

    # YoY: find observation ~12 months back
    yoy_ref = None
    try:
        latest_dt = datetime.strptime(latest["date"], "%Y-%m")
    except ValueError:
        return None
    target_year_ago = latest_dt.replace(year=latest_dt.year - 1)
    for o in observations:
        try:
            d = datetime.strptime(o["date"], "%Y-%m")
        except ValueError:
            continue
        if d.year == target_year_ago.year and d.month == target_year_ago.month:
            yoy_ref = o
            break

    change = None
    change_pct = None
    if prior and prior["value"] not in (None, 0):
        change = round(latest["value"] - prior["value"], 1)
        change_pct = round((latest["value"] - prior["value"]) / prior["value"] * 100, 2)

    yoy_change = None
    yoy_change_pct = None
    if yoy_ref and yoy_ref["value"] not in (None, 0):
        yoy_change = round(latest["value"] - yoy_ref["value"], 1)
        yoy_change_pct = round((latest["value"] - yoy_ref["value"]) / yoy_ref["value"] * 100, 2)

    # Trailing 12-month total
    ttm_total = None
    if len(observations) >= 12:
        ttm_total = round(sum(o["value"] for o in observations[:12]), 1)

    return {
        "value": latest["value"],
        "as_of": latest["date"],
        "prior_value": prior["value"] if prior else None,
        "prior_as_of": prior["date"] if prior else None,
        "change": change,
        "change_pct": change_pct,
        "yoy_change": yoy_change,
        "yoy_change_pct": yoy_change_pct,
        "ttm_total": ttm_total,
        "history": observations,
    }


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

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
    real_entries = [v for k, v in cache.items()
                    if not k.startswith("_") and isinstance(v, dict)
                    and v.get("value") is not None]
    if len(real_entries) < 1:
        return False
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_construction_data(cache_path="construction_cache.json", force_refresh=False, api_key=None):
    """
    Args:
      cache_path: where to read/write the cache JSON
      force_refresh: bypass cache freshness check
      api_key: Census API key (defaults to CENSUS_API_KEY env var)

    Returns:
      construction_dict, warnings_list, metadata_dict

    Behavior on missing API key: works without one (Census API is open), but
    rate-limited after ~500 unkeyed calls per IP per day. We use ~7 calls per run.
    """
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "categories_attempted": 0,
        "categories_succeeded": 0,
        "categories_failed": [],
        "discovered_codes": [],
    }

    if api_key is None:
        api_key = os.environ.get("CENSUS_API_KEY")

    cache = _load_cache(cache_path)
    if cache and _cache_is_fresh(cache) and not force_refresh:
        print(f"Census VIP: cache is fresh (fetched {cache.get('_fetched_at')}); using cached data.")
        metadata["from_cache"] = True
        out = {k: v for k, v in cache.items() if not k.startswith("_")}
        metadata["categories_succeeded"] = sum(1 for v in out.values()
                                               if isinstance(v, dict) and v.get("value") is not None)
        metadata["categories_attempted"] = len(out)
        return out, [], metadata

    print("Census VIP: cache stale or force refresh — pulling construction data...")

    # Optional discovery pass: if FORCE_DISCOVERY is set or we suspect the
    # default category codes are wrong, enumerate what's available.
    if FORCE_DISCOVERY:
        print("Census VIP: discovery mode — enumerating available category codes...")
        codes = _discover_categories(api_key=api_key)
        metadata["discovered_codes"] = codes
        if codes:
            print(f"Census VIP: found {len(codes)} category codes: {codes}")

    results = {}
    warnings_all = []

    for key, cat_code, label, history_months in CATEGORIES:
        metadata["categories_attempted"] += 1
        try:
            obs = _fetch_category(cat_code, history_months, api_key=api_key)
            time.sleep(0.2)
            if not obs:
                # Try discovery if first category fails — likely a code mismatch
                if metadata["categories_succeeded"] == 0 and not metadata["discovered_codes"]:
                    print(f"Census VIP: {cat_code} returned nothing; running discovery...")
                    codes = _discover_categories(api_key=api_key)
                    metadata["discovered_codes"] = codes
                    if codes:
                        print(f"Census VIP: available codes are: {codes}")
                        warnings_all.append(
                            f"Configured code '{cat_code}' not found. "
                            f"Available: {', '.join(codes)}"
                        )
                metadata["categories_failed"].append(f"{key} ({cat_code})")
                warnings_all.append(f"{key}: category code '{cat_code}' returned no data")
                continue

            metrics = _compute_metrics(obs)
            if not metrics:
                metadata["categories_failed"].append(f"{key} ({cat_code})")
                warnings_all.append(f"{key}: insufficient data to compute metrics")
                continue

            metrics["_category_code"] = cat_code
            metrics["_label"] = label
            metrics["_units"] = "$M"
            metrics["_seasonal"] = "Not Seasonally Adjusted"
            metrics["_data_type"] = DATA_TYPE_CODE
            metrics["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            results[key] = metrics
            metadata["categories_succeeded"] += 1

        except Exception as e:
            metadata["categories_failed"].append(f"{key}: {str(e)[:80]}")
            warnings_all.append(f"{key}: fetch error: {str(e)[:80]}")

    cache_payload = dict(results)
    cache_payload["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    cache_payload["_last_full_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _save_cache(cache_path, cache_payload)

    print(f"Census VIP: refresh complete. Succeeded: {metadata['categories_succeeded']}/{metadata['categories_attempted']}, "
          f"failed: {len(metadata['categories_failed'])}, warnings: {len(warnings_all)}")

    return results, warnings_all, metadata


# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------

def get_data_center_summary(construction_data):
    """
    Compact tile data for the data center pillar of the dashboard.
    Includes data center + power (grid capacity is the supply-side constraint).
    """
    out = []
    for key in ("data_center", "power"):
        m = construction_data.get(key)
        if not m:
            continue
        out.append({
            "key": key,
            "label": m.get("_label", key),
            "value": m.get("value"),
            "as_of": m.get("as_of"),
            "units": m.get("_units", ""),
            "yoy_change_pct": m.get("yoy_change_pct"),
            "ttm_total": m.get("ttm_total"),
        })
    return out


def get_construction_comparison(construction_data):
    """
    Comparison view: data center vs office (the inflection story), plus power
    and manufacturing for sector context. Returns list ordered for chart rendering.
    """
    keys_in_order = ["data_center", "office", "power", "manufacturing", "commercial"]
    out = []
    for key in keys_in_order:
        m = construction_data.get(key)
        if not m:
            continue
        out.append({
            "key": key,
            "label": m.get("_label", key),
            "value": m.get("value"),
            "as_of": m.get("as_of"),
            "ttm_total": m.get("ttm_total"),
            "yoy_change_pct": m.get("yoy_change_pct"),
            "history": m.get("history", []),
        })
    return out
