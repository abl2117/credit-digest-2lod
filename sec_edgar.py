"""
SEC EDGAR integration for the credit digest.

Pulls audited financial data directly from SEC's XBRL-tagged company facts API.
No API key required. Respects SEC's User-Agent requirement.

Public functions:
    fetch_financials(watchlist, cache_path='financials_cache.json', force_refresh=False)
      -> (financials_dict, warnings_list, run_metadata_dict)

The returned financials_dict is keyed by company name with structure:
    {
      "Whirlpool": {
        "revenue_ltm": 15234.5,
        "ebitda_ltm": 1456.2,
        "fcf_ltm": 234.1,
        "cash": 1234.0,
        "total_debt": 4700.0,
        "net_debt": 3466.0,
        "nd_ebitda": 2.38,
        "ebitda_margin": 9.56,
        "op_margin": 6.55,
        "revenue_yoy_pct": -3.2,
        "_source": "SEC:CIK0000106640",
        "_filing_form": "10-Q",
        "_period_end": "2026-03-31",
        "_fetched_at": "2026-05-15T08:02:14Z",
        "_warnings": []
      },
      ...
    }
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# SEC requires identifying User-Agent: "Sample Company Name AdminContact@samplecompany.com"
# Format must include human-readable name + contact email separated by a space
SEC_USER_AGENT = "Credit Digest Personal Research contact@example.com"

# Cache freshness: refresh full dataset if cache is older than this
CACHE_TTL_DAYS = 6

# Concept tag fallback chains (try in order, take first available)
TAG_CHAINS = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "op_income": [
        "OperatingIncomeLoss",
    ],
    "da": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "ocf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "lt_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "st_debt": [
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
    ],
}


def _http_get(url, retries=3, sleep=0.5):
    """SEC requires User-Agent; rate limit is generous but we throttle anyway."""
    req = urllib.request.Request(url, headers={
        "User-Agent": SEC_USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Host": url.split("/")[2] if "://" in url else "www.sec.gov",
    })
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                content = r.read()
                # Handle gzip if needed
                if r.headers.get('Content-Encoding') == 'gzip':
                    import gzip
                    content = gzip.decompress(content)
                return json.loads(content)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            try:
                body = e.read().decode('utf-8', errors='replace')[:200]
                last_err += f" body={body}"
            except:
                pass
            if e.code == 404:
                return None  # company has no facts; surface as missing
            if e.code in (429, 503):
                time.sleep(sleep * (2 ** attempt))
                continue
            # Other HTTP errors - log and bail
            print(f"  SEC HTTP error on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  SEC fetch error on {url}: {last_err}")
            time.sleep(sleep)
    raise RuntimeError(f"SEC fetch failed after {retries} attempts: {last_err}")


def _build_ticker_to_cik_map():
    """Returns dict: TICKER (upper) -> CIK (zero-padded 10-digit string)."""
    print(f"SEC EDGAR: fetching company_tickers.json with User-Agent='{SEC_USER_AGENT}'")
    data = _http_get("https://www.sec.gov/files/company_tickers.json")
    if not data:
        print("SEC EDGAR: company_tickers.json returned None (see error above)")
        return {}
    out = {}
    for _, entry in data.items():
        cik = str(entry.get("cik_str", "")).zfill(10)
        ticker = (entry.get("ticker") or "").upper()
        if ticker and cik:
            out[ticker] = cik
    return out


def _pick_period_end(fact_units, prefer_quarterly=True):
    """
    From SEC's per-unit list of fact instances, pick the most recent point-in-time
    fact (for balance-sheet items: end-of-period values) or the relevant quarterly
    instance. Returns list sorted newest first.
    """
    # SEC facts are dicts with keys: start, end, val, fy, fp, form, accn, filed
    # For instant facts (balance sheet), only `end` is set.
    items = []
    for f in fact_units or []:
        end = f.get("end")
        if not end:
            continue
        items.append(f)
    items.sort(key=lambda x: x.get("end", ""), reverse=True)
    return items


def _get_concept(facts, tag_chain, taxonomy="us-gaap"):
    """
    Walk fallback tags. Returns (units_list, tag_used) for the first tag found,
    where units_list is the list of fact instances for the primary unit (usually USD).
    """
    facts_taxonomy = facts.get("facts", {}).get(taxonomy, {})
    for tag in tag_chain:
        node = facts_taxonomy.get(tag)
        if not node:
            continue
        units = node.get("units", {})
        if not units:
            continue
        # Pick primary unit: prefer USD, then USD/shares not relevant here, then anything
        unit_key = next((k for k in units.keys() if k == "USD"), None)
        if not unit_key:
            unit_key = next(iter(units.keys()), None)
        if unit_key:
            return units[unit_key], tag
    return None, None


def _latest_balance_sheet(facts, tag_chain):
    """Returns (value, period_end, tag_used) for the most recent balance-sheet instant."""
    units, tag = _get_concept(facts, tag_chain)
    if not units:
        return None, None, None
    items = _pick_period_end(units)
    if not items:
        return None, None, None
    f = items[0]
    return f.get("val"), f.get("end"), tag


def _ltm_sum(facts, tag_chain, is_quarterly_filer=True):
    """
    Sum the last twelve months for a flow item (revenue, op income, OCF, etc.).
    Strategy:
      - For 10-K/10-Q filers (quarterly): take 4 most recent non-overlapping
        quarterly facts (start/end span ~90 days each) and sum.
      - For 20-F filers (annual only): take the most recent annual fact.
    Returns (ltm_value, latest_period_end, form_type, tag_used).
    """
    units, tag = _get_concept(facts, tag_chain)
    if not units:
        return None, None, None, None

    # Separate quarterly (~90 days) and annual (~365 days) periods
    quarterly = []
    annual = []
    for f in units:
        start = f.get("start"); end = f.get("end")
        if not start or not end:
            continue
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
            ed = datetime.strptime(end, "%Y-%m-%d").date()
            days = (ed - sd).days
        except:
            continue
        f["_days"] = days
        if 80 <= days <= 100:
            quarterly.append(f)
        elif 350 <= days <= 380:
            annual.append(f)

    # Strategy 1: 4 most recent quarters
    if quarterly:
        quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
        latest_end = quarterly[0].get("end")
        # Take 4 most recent non-overlapping quarters
        picked = [quarterly[0]]
        for q in quarterly[1:]:
            if len(picked) >= 4:
                break
            # No overlap: this quarter's end must be before previous quarter's start
            try:
                prev_start = datetime.strptime(picked[-1].get("start"), "%Y-%m-%d").date()
                this_end = datetime.strptime(q.get("end"), "%Y-%m-%d").date()
                if this_end <= prev_start:
                    picked.append(q)
            except:
                continue
        if len(picked) == 4:
            ltm = sum(f.get("val", 0) for f in picked)
            form = picked[0].get("form", "10-Q")
            return ltm, latest_end, form, tag
        # Fall through to annual if we can't get 4 quarters

    # Strategy 2: latest annual
    if annual:
        annual.sort(key=lambda x: x.get("end", ""), reverse=True)
        f = annual[0]
        return f.get("val"), f.get("end"), f.get("form", "10-K"), tag

    return None, None, None, tag


def _ltm_revenue_yoy(facts, tag_chain):
    """Return YoY percent change in LTM revenue, comparing to 4 quarters earlier."""
    units, _ = _get_concept(facts, tag_chain)
    if not units:
        return None

    quarterly = []
    for f in units:
        start = f.get("start"); end = f.get("end")
        if not start or not end:
            continue
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
            ed = datetime.strptime(end, "%Y-%m-%d").date()
            days = (ed - sd).days
        except:
            continue
        if 80 <= days <= 100:
            quarterly.append(f)
    if len(quarterly) < 8:
        return None
    quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)

    def non_overlapping_4(start_idx):
        picked = [quarterly[start_idx]]
        i = start_idx + 1
        while len(picked) < 4 and i < len(quarterly):
            try:
                prev_start = datetime.strptime(picked[-1].get("start"), "%Y-%m-%d").date()
                this_end = datetime.strptime(quarterly[i].get("end"), "%Y-%m-%d").date()
                if this_end <= prev_start:
                    picked.append(quarterly[i])
            except:
                pass
            i += 1
        return picked if len(picked) == 4 else None

    current = non_overlapping_4(0)
    if not current:
        return None
    # Find the index where the previous 4-quarter block starts
    last_start = current[-1].get("start")
    try:
        last_start_date = datetime.strptime(last_start, "%Y-%m-%d").date()
    except:
        return None
    prev_idx = None
    for i, q in enumerate(quarterly):
        try:
            qe = datetime.strptime(q.get("end"), "%Y-%m-%d").date()
            if qe <= last_start_date:
                prev_idx = i
                break
        except:
            continue
    if prev_idx is None:
        return None
    previous = non_overlapping_4(prev_idx)
    if not previous:
        return None
    curr_sum = sum(q.get("val", 0) for q in current)
    prev_sum = sum(q.get("val", 0) for q in previous)
    if prev_sum == 0:
        return None
    return (curr_sum - prev_sum) / prev_sum * 100


def _extract_metrics(facts, filer_type):
    """
    Given the raw companyfacts JSON, extract all metrics we need.
    Returns dict of values + provenance metadata.
    """
    is_q = (filer_type == "10-K")  # 10-K filers also file 10-Q quarterly

    rev_ltm, rev_end, rev_form, rev_tag = _ltm_sum(facts, TAG_CHAINS["revenue"], is_q)
    opi_ltm, opi_end, opi_form, opi_tag = _ltm_sum(facts, TAG_CHAINS["op_income"], is_q)
    da_ltm, da_end, da_form, da_tag = _ltm_sum(facts, TAG_CHAINS["da"], is_q)
    ocf_ltm, ocf_end, ocf_form, ocf_tag = _ltm_sum(facts, TAG_CHAINS["ocf"], is_q)
    capex_ltm, _, _, capex_tag = _ltm_sum(facts, TAG_CHAINS["capex"], is_q)

    cash, cash_end, cash_tag = _latest_balance_sheet(facts, TAG_CHAINS["cash"])
    lt_debt, lt_end, lt_tag = _latest_balance_sheet(facts, TAG_CHAINS["lt_debt"])
    st_debt, st_end, st_tag = _latest_balance_sheet(facts, TAG_CHAINS["st_debt"])
    if st_debt is None:
        st_debt = 0  # short-term debt commonly absent for clean balance sheets

    rev_yoy = _ltm_revenue_yoy(facts, TAG_CHAINS["revenue"])

    # Construct derived metrics (all values converted to $Bn, rounded 1dp)
    def to_bn(v):
        if v is None:
            return None
        return round(v / 1e9, 1)

    ebitda_ltm = None
    if opi_ltm is not None and da_ltm is not None:
        ebitda_ltm = opi_ltm + da_ltm

    fcf_ltm = None
    if ocf_ltm is not None and capex_ltm is not None:
        # capex in SEC is typically reported as a positive outflow, but some companies sign it negative
        # FCF = OCF - |capex|
        fcf_ltm = ocf_ltm - abs(capex_ltm)

    total_debt = None
    if lt_debt is not None:
        total_debt = lt_debt + (st_debt or 0)

    net_debt = None
    if total_debt is not None and cash is not None:
        net_debt = total_debt - cash

    nd_ebitda = None
    if net_debt is not None and ebitda_ltm and ebitda_ltm > 0:
        nd_ebitda = round(net_debt / ebitda_ltm, 1)

    ebitda_margin = None
    if ebitda_ltm is not None and rev_ltm and rev_ltm > 0:
        ebitda_margin = round(ebitda_ltm / rev_ltm * 100, 1)

    op_margin = None
    if opi_ltm is not None and rev_ltm and rev_ltm > 0:
        op_margin = round(opi_ltm / rev_ltm * 100, 1)

    return {
        "revenue_ltm": to_bn(rev_ltm),
        "ebitda_ltm": to_bn(ebitda_ltm),
        "fcf_ltm": to_bn(fcf_ltm),
        "cash": to_bn(cash),
        "lt_debt": to_bn(lt_debt),
        "st_debt": to_bn(st_debt),
        "total_debt": to_bn(total_debt),
        "net_debt": to_bn(net_debt),
        "nd_ebitda": nd_ebitda,
        "ebitda_margin": ebitda_margin,
        "op_margin": op_margin,
        "revenue_yoy_pct": round(rev_yoy, 1) if rev_yoy is not None else None,
        "_period_end": rev_end or opi_end or cash_end,
        "_filing_form": rev_form or opi_form,
        "_tags_used": {
            "revenue": rev_tag, "op_income": opi_tag, "da": da_tag,
            "ocf": ocf_tag, "capex": capex_tag, "cash": cash_tag,
            "lt_debt": lt_tag, "st_debt": st_tag,
        }
    }


def _validate(metrics, company):
    """Run sanity-check rules. Return list of warnings."""
    warnings = []
    rev = metrics.get("revenue_ltm")
    ebitda = metrics.get("ebitda_ltm")
    cash = metrics.get("cash")
    total_debt = metrics.get("total_debt")
    nd_ebitda = metrics.get("nd_ebitda")
    rev_yoy = metrics.get("revenue_yoy_pct")
    ebitda_margin = metrics.get("ebitda_margin")
    op_margin = metrics.get("op_margin")

    if rev is None:
        warnings.append("Revenue LTM not found in SEC tags")
    if ebitda is None:
        warnings.append("EBITDA could not be constructed (missing op_income or D&A)")
    if cash is None:
        warnings.append("Cash not found in SEC tags")
    if total_debt is None:
        warnings.append("Total debt not found in SEC tags")
    if nd_ebitda is not None and (nd_ebitda > 50 or nd_ebitda < -50):
        warnings.append(f"ND/EBITDA = {nd_ebitda:.1f}x (outside plausible range)")
    if rev_yoy is not None and abs(rev_yoy) > 50:
        warnings.append(f"Revenue YoY = {rev_yoy:.1f}% (unusual; verify)")
    if ebitda_margin is not None and (ebitda_margin > 80 or ebitda_margin < -50):
        warnings.append(f"EBITDA margin = {ebitda_margin:.1f}% (outside plausible range)")
    if cash is not None and cash < 0:
        warnings.append(f"Cash is negative ({cash}) — likely parsing error")
    if total_debt is not None and total_debt < 0:
        warnings.append(f"Total debt is negative ({total_debt}) — likely parsing error")
    return warnings


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
        print(f"WARNING: failed to write cache: {e}")


def _cache_is_fresh(cache):
    """Return True if cache_last_full_refresh is within CACHE_TTL_DAYS."""
    if not cache:
        return False
    last = cache.get("_last_full_refresh")
    if not last:
        return False
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d").date()
        age = (datetime.now(timezone.utc).date() - last_dt).days
        return age < CACHE_TTL_DAYS
    except Exception:
        return False


def fetch_financials(watchlist, cache_path="financials_cache.json", force_refresh=False):
    """
    Main entry point.

    Args:
      watchlist: dict {company_name: {"ticker": ..., "filer_type": ..., "sector": ...}}
      cache_path: where to read/write the cache JSON
      force_refresh: bypass cache freshness check

    Returns:
      financials_dict, warnings_list, metadata_dict
    """
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "names_attempted": 0,
        "names_succeeded": 0,
        "names_failed": [],
        "names_no_sec_filer": [],
        "total_warnings": 0,
    }

    cache = _load_cache(cache_path)
    if cache and _cache_is_fresh(cache) and not force_refresh:
        print(f"SEC EDGAR: cache is fresh ({cache.get('_last_full_refresh')}); using cached data.")
        metadata["from_cache"] = True
        # Strip metadata keys from cache when returning
        out = {k: v for k, v in cache.items() if not k.startswith("_")}
        warnings = []
        for co, m in out.items():
            for w in m.get("_warnings", []):
                warnings.append(f"{co}: {w}")
        metadata["names_succeeded"] = sum(1 for k in out if out[k].get("revenue_ltm") is not None)
        metadata["names_attempted"] = len(out)
        metadata["total_warnings"] = len(warnings)
        return out, warnings, metadata

    # Full refresh
    print("SEC EDGAR: cache stale or force refresh — pulling fresh data...")
    try:
        ticker_cik = _build_ticker_to_cik_map()
        print(f"SEC EDGAR: loaded {len(ticker_cik)} ticker-CIK mappings")
    except Exception as e:
        print(f"SEC EDGAR: ticker map fetch failed: {e}")
        if cache:
            print("SEC EDGAR: falling back to stale cache.")
            metadata["from_cache"] = True
            metadata["names_attempted"] = sum(1 for k in cache if not k.startswith("_"))
            out = {k: v for k, v in cache.items() if not k.startswith("_")}
            return out, ["SEC ticker map fetch failed; using stale cache"], metadata
        return {}, ["SEC ticker map fetch failed and no cache available"], metadata

    results = {}
    warnings_all = []

    for co, info in watchlist.items():
        ticker = info.get("ticker", "").upper()
        filer_type = info.get("filer_type")
        metadata["names_attempted"] += 1

        if filer_type is None:
            metadata["names_no_sec_filer"].append(co)
            results[co] = {"_no_sec_filer": True, "_ticker": ticker, "_warnings": ["Not an SEC filer"]}
            continue

        cik = ticker_cik.get(ticker)
        if not cik:
            metadata["names_failed"].append(f"{co} (no CIK for {ticker})")
            results[co] = {"_warnings": [f"No CIK found for ticker {ticker}"]}
            warnings_all.append(f"{co}: No CIK found for ticker {ticker}")
            continue

        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts = _http_get(url)
            time.sleep(0.12)  # SEC requests no more than 10/sec; we go ~8/sec
            if facts is None:
                metadata["names_failed"].append(f"{co} (no facts at SEC)")
                results[co] = {"_warnings": ["No company facts at SEC"]}
                warnings_all.append(f"{co}: No company facts at SEC")
                continue
            metrics = _extract_metrics(facts, filer_type)
            metrics["_source"] = f"SEC:CIK{cik}"
            metrics["_cik"] = cik
            metrics["_ticker"] = ticker
            metrics["_filer_type"] = filer_type
            metrics["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            validation = _validate(metrics, co)
            metrics["_warnings"] = validation
            for w in validation:
                warnings_all.append(f"{co}: {w}")
            results[co] = metrics
            metadata["names_succeeded"] += 1
        except Exception as e:
            metadata["names_failed"].append(f"{co}: {str(e)[:80]}")
            results[co] = {"_warnings": [f"Fetch error: {str(e)[:120]}"]}
            warnings_all.append(f"{co}: Fetch error: {str(e)[:80]}")

    # Save to cache
    cache_payload = dict(results)
    cache_payload["_last_full_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_payload["_full_refresh_at"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache_path, cache_payload)
    print(f"SEC EDGAR: refresh complete. Succeeded: {metadata['names_succeeded']}/{metadata['names_attempted']}, "
          f"failed: {len(metadata['names_failed'])}, non-SEC: {len(metadata['names_no_sec_filer'])}, "
          f"warnings: {len(warnings_all)}")

    metadata["total_warnings"] = len(warnings_all)
    return results, warnings_all, metadata


def apply_sec_overrides(rows, sec_data):
    """
    Overwrite financial fields in each row with SEC data where available.
    Keep Claude's data as fallback if SEC didn't return values.
    """
    if not sec_data:
        return rows
    overridden = 0
    fields_map = {
        "revenue_ltm": "revenue_ltm",
        "ebitda_margin": "ebitda_margin",
        "fcf_ltm": "fcf_ltm",
        "cash": "cash",
        "total_debt": "total_debt",
        "nd_ebitda": "nd_ebitda",
        "revenue_yoy_pct": "revenue_yoy_pct",
        "op_margin": "op_margin",
    }
    for r in rows:
        co = r.get("company", "")
        m = sec_data.get(co)
        if not m or m.get("_no_sec_filer"):
            continue
        applied_any = False
        for src, dest in fields_map.items():
            val = m.get(src)
            if val is not None:
                # Format consistently: 1dp string for nums
                r[dest] = f"{val:.1f}" if isinstance(val, (int, float)) else str(val)
                applied_any = True
        if applied_any:
            overridden += 1
            r["_financials_source"] = m.get("_source", "SEC")
            r["_period_end"] = m.get("_period_end")
            r["_filing_form"] = m.get("_filing_form")
            r["_fin_warnings"] = m.get("_warnings", [])

    print(f"Applied SEC EDGAR financials to {overridden} companies.")
    return rows
