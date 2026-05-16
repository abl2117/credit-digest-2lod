"""
FRED (Federal Reserve Economic Data) integration for the credit digest.

Pulls macro indicators relevant to credit surveillance: rates, spreads, inflation,
labor, and PMI. Free API, requires registration at https://fred.stlouisfed.org/.
Set FRED_API_KEY as a GitHub secret (or environment variable for local runs).

Public functions:
    fetch_macro_data(cache_path='macro_cache.json', force_refresh=False)
      -> (macro_dict, warnings_list, metadata_dict)

The returned macro_dict is keyed by series name with structure:
    {
      "fed_funds": {
        "value": 4.33,
        "as_of": "2026-05-15",
        "prior_value": 4.33,
        "prior_as_of": "2026-04-30",
        "change": 0.0,
        "change_pct": 0.0,
        "history": [{"date": "2026-05-15", "value": 4.33}, ...],
        "_series_id": "DFF",
        "_units": "Percent",
        "_frequency": "Daily",
        "_fetched_at": "2026-05-16T..."
      },
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

# Cache freshness: refresh if older than this. FRED updates daily/monthly so
# a 1-day TTL is appropriate. Some series (CPI, PMI) only update monthly, but
# the cache TTL governs when we re-check, not when the underlying data moves.
CACHE_TTL_HOURS = 20

# Series to track. Each entry: (key, FRED_series_id, label, category, history_points)
# Categories: rates, spreads, inflation, labor, activity
SERIES = [
    # --- Rates (Treasury curve + policy rate) ---
    ("fed_funds",    "DFF",        "Fed Funds Effective Rate",       "rates",     30),
    ("ust_3m",       "DGS3MO",     "3-Month Treasury Yield",         "rates",     30),
    ("ust_2y",       "DGS2",       "2-Year Treasury Yield",          "rates",     30),
    ("ust_10y",      "DGS10",      "10-Year Treasury Yield",         "rates",     90),
    ("ust_30y",      "DGS30",      "30-Year Treasury Yield",         "rates",     30),
    ("ust_10y_2y",   "T10Y2Y",     "10Y-2Y Treasury Spread",         "rates",     90),

    # --- Credit spreads (ICE BofA OAS indices) ---
    ("ig_oas",       "BAMLC0A0CM", "IG Corporate OAS Spread",        "spreads",   90),
    ("bbb_oas",      "BAMLC0A4CBBB", "BBB Corporate OAS Spread",     "spreads",   90),
    ("hy_oas",       "BAMLH0A0HYM2", "High Yield OAS Spread",        "spreads",   90),
    ("ccc_oas",      "BAMLH0A3HYC",  "CCC & Lower OAS Spread",       "spreads",   90),

    # --- Inflation ---
    ("cpi_yoy",      "CPIAUCSL",   "CPI All Items",                  "inflation", 24),
    ("core_cpi_yoy", "CPILFESL",   "Core CPI",                       "inflation", 24),
    ("pce_yoy",      "PCEPI",      "PCE Price Index",                "inflation", 24),

    # --- Labor ---
    ("unemployment", "UNRATE",     "Unemployment Rate",              "labor",     24),
    ("jobless_claims","ICSA",      "Initial Jobless Claims",         "labor",     12),
    ("nonfarm_payrolls", "PAYEMS", "Nonfarm Payrolls",               "labor",     12),

    # --- Activity ---
    ("ism_mfg",      "MANEMP",     "Manufacturing Employment",       "activity",  12),
    ("retail_sales", "RSXFS",      "Retail Sales ex-Food Services",  "activity",  12),
    ("industrial_production", "INDPRO", "Industrial Production",     "activity",  12),
]

# Series for which we want YoY % change rather than the raw value (price indices)
YOY_SERIES = {"cpi_yoy", "core_cpi_yoy", "pce_yoy"}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

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
            if e.code == 400:
                # Bad series id or expired key — surface cleanly
                try:
                    body = e.read().decode("utf-8", errors="replace")[:200]
                    last_err += f" body={body}"
                except Exception:
                    pass
                print(f"  FRED HTTP 400 on {url}: {last_err}")
                return None
            print(f"  FRED HTTP error on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  FRED fetch error on {url}: {last_err}")
            time.sleep(sleep)
    print(f"  FRED fetch failed after {retries} attempts: {last_err}")
    return None


# ---------------------------------------------------------------------------
# Series fetching
# ---------------------------------------------------------------------------

def _fetch_series(api_key, series_id, history_points=30):
    """
    Fetch a single FRED series. Returns dict with observations or None on failure.
    Pulls the last ~2 years to ensure we have enough history for YoY comparisons
    and any sparkline rendering, capped to history_points in the returned slice.
    """
    end = datetime.now().date()
    start = end - timedelta(days=2 * 365 + 30)  # ~25 months for YoY headroom

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.strftime("%Y-%m-%d"),
        "observation_end": end.strftime("%Y-%m-%d"),
        "sort_order": "desc",
    }
    url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    if not data or "observations" not in data:
        return None

    # Parse and clean. FRED returns "." for missing observations.
    obs = []
    for o in data.get("observations", []):
        val = o.get("value")
        if val in (".", "", None):
            continue
        try:
            obs.append({"date": o.get("date"), "value": float(val)})
        except (TypeError, ValueError):
            continue

    if not obs:
        return None

    # Fetch series metadata for label/units/frequency
    meta_params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    meta_url = "https://api.stlouisfed.org/fred/series?" + urllib.parse.urlencode(meta_params)
    meta_data = _http_get_json(meta_url) or {}
    seriess = meta_data.get("seriess", [])
    meta = seriess[0] if seriess else {}

    return {
        "observations": obs,  # newest first
        "history_points": history_points,
        "units": meta.get("units_short", meta.get("units", "")),
        "frequency": meta.get("frequency_short", meta.get("frequency", "")),
        "title": meta.get("title", ""),
    }


def _compute_yoy(observations):
    """
    Given a price-index series newest-first, compute YoY % change at the latest point.
    Returns (yoy_pct, as_of_date, prior_year_value, prior_as_of) or (None, None, None, None).
    """
    if not observations or len(observations) < 2:
        return None, None, None, None
    latest = observations[0]
    try:
        latest_date = datetime.strptime(latest["date"], "%Y-%m-%d").date()
    except Exception:
        return None, None, None, None
    target = latest_date - timedelta(days=365)
    # Find observation closest to (and not after) target date
    best = None
    best_gap = None
    for o in observations[1:]:
        try:
            d = datetime.strptime(o["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        gap = abs((d - target).days)
        if best is None or gap < best_gap:
            best = o
            best_gap = gap
    if best is None or best["value"] == 0:
        return None, None, None, None
    yoy = (latest["value"] - best["value"]) / best["value"] * 100
    return round(yoy, 1), latest["date"], best["value"], best["date"]


def _extract_metrics(key, series_id, history_points, raw):
    """Convert raw series data into the dashboard's metric structure."""
    obs = raw["observations"]  # newest-first
    if not obs:
        return None

    latest = obs[0]
    history = obs[:history_points]  # newest-first slice for sparklines

    # For price indices, headline value is YoY % change
    if key in YOY_SERIES:
        yoy, as_of, prior_val, prior_as_of = _compute_yoy(obs)
        if yoy is None:
            return None
        return {
            "value": yoy,
            "as_of": as_of,
            "prior_value": None,
            "prior_as_of": prior_as_of,
            "change": None,
            "change_pct": None,
            "history": history,  # raw index values for chart context
            "_series_id": series_id,
            "_units": "% YoY",
            "_frequency": raw.get("frequency", ""),
            "_title": raw.get("title", ""),
        }

    # Standard series: report latest value and change from prior observation
    prior = obs[1] if len(obs) > 1 else None
    change = None
    change_pct = None
    if prior and prior["value"] not in (None, 0):
        change = round(latest["value"] - prior["value"], 4)
        # For rate/spread series, pct change is rarely meaningful; we still compute it
        change_pct = round((latest["value"] - prior["value"]) / abs(prior["value"]) * 100, 2)

    return {
        "value": latest["value"],
        "as_of": latest["date"],
        "prior_value": prior["value"] if prior else None,
        "prior_as_of": prior["date"] if prior else None,
        "change": change,
        "change_pct": change_pct,
        "history": history,
        "_series_id": series_id,
        "_units": raw.get("units", ""),
        "_frequency": raw.get("frequency", ""),
        "_title": raw.get("title", ""),
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
        print(f"WARNING: failed to write FRED cache: {e}")


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
    if len(real_entries) < len(SERIES) * 0.5:
        return False
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_macro_data(cache_path="macro_cache.json", force_refresh=False, api_key=None):
    """
    Args:
      cache_path: where to read/write the cache JSON
      force_refresh: bypass cache freshness check
      api_key: FRED API key (defaults to FRED_API_KEY env var)

    Returns:
      macro_dict, warnings_list, metadata_dict

    Behavior on missing API key:
      - If env var is unset and api_key not passed, returns empty dict + warning.
      - This is non-fatal: the dashboard should degrade gracefully if macro data
        isn't available (e.g. local development without the secret configured).
    """
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "series_attempted": 0,
        "series_succeeded": 0,
        "series_failed": [],
    }

    if api_key is None:
        api_key = os.environ.get("FRED_API_KEY")

    if not api_key:
        # Try cache as fallback
        cache = _load_cache(cache_path)
        if cache:
            print("FRED: no API key set; using cached macro data.")
            metadata["from_cache"] = True
            out = {k: v for k, v in cache.items() if not k.startswith("_")}
            return out, ["FRED_API_KEY not set; using cached data"], metadata
        print("FRED: no API key set and no cache available; skipping macro data.")
        return {}, ["FRED_API_KEY not set; macro data unavailable"], metadata

    cache = _load_cache(cache_path)
    if cache and _cache_is_fresh(cache) and not force_refresh:
        print(f"FRED: cache is fresh (fetched {cache.get('_fetched_at')}); using cached data.")
        metadata["from_cache"] = True
        out = {k: v for k, v in cache.items() if not k.startswith("_")}
        metadata["series_succeeded"] = sum(1 for v in out.values()
                                           if isinstance(v, dict) and v.get("value") is not None)
        metadata["series_attempted"] = len(out)
        return out, [], metadata

    print("FRED: cache stale or force refresh — pulling fresh macro data...")
    results = {}
    warnings_all = []

    for key, series_id, label, category, history_points in SERIES:
        metadata["series_attempted"] += 1
        try:
            raw = _fetch_series(api_key, series_id, history_points=history_points)
            time.sleep(0.1)  # FRED rate limit is 120/min; we're well under that
            if not raw:
                metadata["series_failed"].append(f"{key} ({series_id})")
                warnings_all.append(f"{key}: no data returned from FRED")
                continue
            metrics = _extract_metrics(key, series_id, history_points, raw)
            if not metrics:
                metadata["series_failed"].append(f"{key} ({series_id})")
                warnings_all.append(f"{key}: insufficient data to compute metrics")
                continue
            metrics["_label"] = label
            metrics["_category"] = category
            metrics["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            results[key] = metrics
            metadata["series_succeeded"] += 1
        except Exception as e:
            metadata["series_failed"].append(f"{key}: {str(e)[:80]}")
            warnings_all.append(f"{key}: fetch error: {str(e)[:80]}")

    cache_payload = dict(results)
    cache_payload["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    cache_payload["_last_full_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _save_cache(cache_path, cache_payload)

    print(f"FRED: refresh complete. Succeeded: {metadata['series_succeeded']}/{metadata['series_attempted']}, "
          f"failed: {len(metadata['series_failed'])}, warnings: {len(warnings_all)}")

    return results, warnings_all, metadata


# ---------------------------------------------------------------------------
# Dashboard helper: compact summary for header strip
# ---------------------------------------------------------------------------

def get_credit_relevant_summary(macro_data):
    """
    Return a compact list of the most credit-relevant indicators for an Overview
    tab strip. Each entry: {"key", "label", "value", "as_of", "units", "change"}.
    Designed for rendering 4-5 tiles across the top of the dashboard.
    """
    priority_keys = ["ust_10y", "ig_oas", "hy_oas", "fed_funds", "cpi_yoy"]
    out = []
    for key in priority_keys:
        m = macro_data.get(key)
        if not m:
            continue
        out.append({
            "key": key,
            "label": m.get("_label", key),
            "value": m.get("value"),
            "as_of": m.get("as_of"),
            "units": m.get("_units", ""),
            "change": m.get("change"),
        })
    return out


def get_by_category(macro_data):
    """
    Group macro data by category for the Macro tab.
    Returns dict: {"rates": [...], "spreads": [...], ...}
    """
    by_cat = {}
    for key, m in macro_data.items():
        if not isinstance(m, dict):
            continue
        cat = m.get("_category", "other")
        by_cat.setdefault(cat, []).append({
            "key": key,
            "label": m.get("_label", key),
            "value": m.get("value"),
            "as_of": m.get("as_of"),
            "units": m.get("_units", ""),
            "change": m.get("change"),
            "history": m.get("history", []),
        })
    # Stable ordering
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x["key"])
    return by_cat
