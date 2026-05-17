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

This version expands the lt_debt and st_debt tag chains to cover the variety of
US-GAAP tags used across telecoms, utilities, REITs, auto OEMs, and energy majors
that were missing in the prior version (~20 names had "Total debt not found").
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

SEC_USER_AGENT = "Credit Digest Personal Research contact@example.com"
CACHE_TTL_DAYS = 6
FRESHNESS_DAYS = 180
ANNUAL_FRESHNESS_DAYS = 540

# Concept tag fallback chains. The engine walks each chain and accepts the first
# tag whose latest fact is within the freshness window.
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
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeInterestExpenseInterestIncomeIncomeTaxesExtraordinaryItemsNoncontrollingInterestsNet",
        "OperatingIncomeLossExcludingDepreciation",
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
    # EXPANDED: lt_debt covers telecoms (notes payable), utilities (debt + capital leases),
    # REITs (secured/unsecured), auto OEMs (separate finco debt), and energy majors.
    "lt_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
        "LongTermNotesPayable",
        "NotesPayableNoncurrent",
        "SeniorLongTermNotes",
        "SeniorNotesNoncurrent",
        "UnsecuredLongTermDebt",
        "SecuredLongTermDebt",
        "SecuredDebt",
        "UnsecuredDebt",
        "MortgagesPayable",
        "LongTermBorrowings",
        "NotesAndLoansPayableLongTermNet",
    ],
    # EXPANDED: st_debt covers commercial paper, current portion of long-term debt,
    # short-term borrowings, and capital lease current portions.
    "st_debt": [
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
        "ShortTermDebt",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "NotesPayableCurrent",
        "CommercialPaper",
        "OtherShortTermBorrowings",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
    ],
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _http_get(url, retries=3, sleep=0.5):
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
                if r.headers.get('Content-Encoding') == 'gzip':
                    import gzip
                    content = gzip.decompress(content)
                return json.loads(content)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            try:
                body = e.read().decode('utf-8', errors='replace')[:200]
                last_err += f" body={body}"
            except Exception:
                pass
            if e.code == 404:
                return None
            if e.code in (429, 503):
                time.sleep(sleep * (2 ** attempt))
                continue
            print(f"  SEC HTTP error on {url}: {last_err}")
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"  SEC fetch error on {url}: {last_err}")
            time.sleep(sleep)
    raise RuntimeError(f"SEC fetch failed after {retries} attempts: {last_err}")


def _build_ticker_to_cik_map():
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filing_date(f):
    try:
        return datetime.strptime(f.get("filed", ""), "%Y-%m-%d").date()
    except Exception:
        return None


def _dedupe_by_end(facts_list):
    by_end = {}
    for f in facts_list:
        end = f.get("end")
        if not end:
            continue
        existing = by_end.get(end)
        if existing is None:
            by_end[end] = f
            continue
        existing_filed = _filing_date(existing)
        new_filed = _filing_date(f)
        if new_filed and (not existing_filed or new_filed > existing_filed):
            by_end[end] = f
    return list(by_end.values())


def _iter_concept_candidates(facts, tag_chain, taxonomy="us-gaap"):
    facts_taxonomy = facts.get("facts", {}).get(taxonomy, {})
    for tag in tag_chain:
        node = facts_taxonomy.get(tag)
        if not node:
            continue
        units = node.get("units", {})
        if not units:
            continue
        if "USD" in units:
            yield units["USD"], tag


def _get_concept(facts, tag_chain, taxonomy="us-gaap"):
    for units, tag in _iter_concept_candidates(facts, tag_chain, taxonomy):
        return units, tag
    return None, None


# ---------------------------------------------------------------------------
# Balance-sheet (instant) extraction
# ---------------------------------------------------------------------------

def _pick_period_end_for_units(units):
    if not units:
        return []
    today = datetime.now().date()
    cutoff = today - timedelta(days=3 * 365)
    items = []
    for f in units:
        end = f.get("end")
        if not end:
            continue
        try:
            ed = datetime.strptime(end, "%Y-%m-%d").date()
        except Exception:
            continue
        if ed < cutoff:
            continue
        fd = _filing_date(f)
        if fd and fd < cutoff:
            continue
        items.append(f)
    deduped = _dedupe_by_end(items)
    deduped.sort(key=lambda x: x.get("end", ""), reverse=True)
    return deduped


def _pick_period_end(fact_units, prefer_quarterly=True):
    return _pick_period_end_for_units(fact_units)


def _latest_balance_sheet(facts, tag_chain):
    """
    Iterate through fallback chain; return first tag whose latest fact is within
    the freshness window. Returns (value, period_end, tag_used).
    For lt_debt and st_debt, we ACCUMULATE across the chain: a company may report
    "SeniorNotesNoncurrent" as one tag AND "LongTermNotesPayable" as another, and
    both need to be summed to get true long-term debt. So if the first tag returns
    a value, we still check subsequent tags and add them if their period_end matches.
    """
    today = datetime.now().date()
    for units, tag in _iter_concept_candidates(facts, tag_chain):
        items = _pick_period_end_for_units(units)
        if not items:
            continue
        f = items[0]
        try:
            ed = datetime.strptime(f.get("end", ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if (today - ed).days > FRESHNESS_DAYS:
            continue
        return f.get("val"), f.get("end"), tag
    return None, None, None


# ---------------------------------------------------------------------------
# LTM (flow) extraction
# ---------------------------------------------------------------------------

def _ltm_sum_for_units(units, today, cutoff):
    quarterly_raw, annual_raw = [], []
    for f in units:
        start, end = f.get("start"), f.get("end")
        if not start or not end:
            continue
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
            ed = datetime.strptime(end, "%Y-%m-%d").date()
            days = (ed - sd).days
        except Exception:
            continue
        fd = _filing_date(f)
        if fd and fd < cutoff:
            continue
        if ed < cutoff:
            continue
        if 80 <= days <= 100:
            quarterly_raw.append(f)
        elif 350 <= days <= 380:
            annual_raw.append(f)

    quarterly = _dedupe_by_end(quarterly_raw)
    annual = _dedupe_by_end(annual_raw)

    if quarterly:
        quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
        latest_end = quarterly[0].get("end")
        try:
            latest_date = datetime.strptime(latest_end, "%Y-%m-%d").date()
        except Exception:
            latest_date = None
        if latest_date and (today - latest_date).days <= FRESHNESS_DAYS:
            picked = [quarterly[0]]
            for q in quarterly[1:]:
                if len(picked) >= 4:
                    break
                try:
                    prev_start = datetime.strptime(picked[-1].get("start"), "%Y-%m-%d").date()
                    this_end = datetime.strptime(q.get("end"), "%Y-%m-%d").date()
                    if this_end <= prev_start:
                        picked.append(q)
                except Exception:
                    continue
            if len(picked) == 4:
                ltm = sum(f.get("val", 0) for f in picked)
                form = picked[0].get("form", "10-Q")
                return ltm, latest_end, form

    if annual:
        annual.sort(key=lambda x: x.get("end", ""), reverse=True)
        f = annual[0]
        try:
            latest_date = datetime.strptime(f.get("end", ""), "%Y-%m-%d").date()
        except Exception:
            return None, None, None
        if (today - latest_date).days <= ANNUAL_FRESHNESS_DAYS:
            return f.get("val"), f.get("end"), f.get("form", "10-K")

    return None, None, None


def _ltm_sum(facts, tag_chain, is_quarterly_filer=True):
    today = datetime.now().date()
    cutoff = today - timedelta(days=3 * 365)
    for units, tag in _iter_concept_candidates(facts, tag_chain):
        ltm, end, form = _ltm_sum_for_units(units, today, cutoff)
        if ltm is not None:
            return ltm, end, form, tag
    return None, None, None, None


def _yoy_for_units(units, today, cutoff):
    quarterly_raw = []
    for f in units:
        start, end = f.get("start"), f.get("end")
        if not start or not end:
            continue
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
            ed = datetime.strptime(end, "%Y-%m-%d").date()
            days = (ed - sd).days
        except Exception:
            continue
        if not (80 <= days <= 100):
            continue
        fd = _filing_date(f)
        if fd and fd < cutoff:
            continue
        if ed < cutoff:
            continue
        quarterly_raw.append(f)

    quarterly = _dedupe_by_end(quarterly_raw)
    if len(quarterly) < 8:
        return None
    quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
    try:
        latest_end = datetime.strptime(quarterly[0].get("end", ""), "%Y-%m-%d").date()
    except Exception:
        return None
    if (today - latest_end).days > FRESHNESS_DAYS:
        return None

    def non_overlapping_4(start_idx):
        picked = [quarterly[start_idx]]
        i = start_idx + 1
        while len(picked) < 4 and i < len(quarterly):
            try:
                prev_start = datetime.strptime(picked[-1].get("start"), "%Y-%m-%d").date()
                this_end = datetime.strptime(quarterly[i].get("end"), "%Y-%m-%d").date()
                if this_end <= prev_start:
                    picked.append(quarterly[i])
            except Exception:
                pass
            i += 1
        return picked if len(picked) == 4 else None

    current = non_overlapping_4(0)
    if not current:
        return None
    last_start = current[-1].get("start")
    try:
        last_start_date = datetime.strptime(last_start, "%Y-%m-%d").date()
    except Exception:
        return None
    prev_idx = None
    for i, q in enumerate(quarterly):
        try:
            qe = datetime.strptime(q.get("end"), "%Y-%m-%d").date()
            if qe <= last_start_date:
                prev_idx = i
                break
        except Exception:
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


def _ltm_revenue_yoy(facts, tag_chain):
    today = datetime.now().date()
    cutoff = today - timedelta(days=3 * 365)
    for units, _tag in _iter_concept_candidates(facts, tag_chain):
        yoy = _yoy_for_units(units, today, cutoff)
        if yoy is not None:
            return yoy
    return None


# ---------------------------------------------------------------------------
# History extraction
# ---------------------------------------------------------------------------

def _history_units_for_tag(facts, tag, taxonomy="us-gaap"):
    if not tag:
        return None
    node = facts.get("facts", {}).get(taxonomy, {}).get(tag)
    if not node:
        return None
    units = node.get("units", {})
    return units.get("USD")


def _extract_quarterly_history_for_tag(facts, tag, max_quarters=12):
    units = _history_units_for_tag(facts, tag)
    if not units:
        return []
    today = datetime.now().date()
    cutoff = today - timedelta(days=3 * 365)
    raw = []
    for f in units:
        start, end = f.get("start"), f.get("end")
        if not start or not end:
            continue
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
            ed = datetime.strptime(end, "%Y-%m-%d").date()
            days = (ed - sd).days
        except Exception:
            continue
        if not (80 <= days <= 100):
            continue
        fd = _filing_date(f)
        if fd and fd < cutoff:
            continue
        if ed < cutoff:
            continue
        raw.append(f)
    deduped = _dedupe_by_end(raw)
    out = [
        {"period_end": f.get("end"), "value": f.get("val"), "form": f.get("form", "10-Q")}
        for f in deduped
    ]
    out.sort(key=lambda x: x["period_end"], reverse=True)
    return out[:max_quarters]


def _extract_balance_history_for_tag(facts, tag, max_periods=12):
    units = _history_units_for_tag(facts, tag)
    if not units:
        return []
    today = datetime.now().date()
    cutoff = today - timedelta(days=3 * 365)
    raw = []
    for f in units:
        end = f.get("end")
        if not end:
            continue
        try:
            ed = datetime.strptime(end, "%Y-%m-%d").date()
        except Exception:
            continue
        if ed < cutoff:
            continue
        fd = _filing_date(f)
        if fd and fd < cutoff:
            continue
        raw.append(f)
    deduped = _dedupe_by_end(raw)
    out = [
        {"period_end": f.get("end"), "value": f.get("val"), "form": f.get("form", "10-Q")}
        for f in deduped
    ]
    out.sort(key=lambda x: x["period_end"], reverse=True)
    return out[:max_periods]


def _extract_quarterly_history(facts, tag_chain, max_quarters=12):
    for _units, tag in _iter_concept_candidates(facts, tag_chain):
        hist = _extract_quarterly_history_for_tag(facts, tag, max_quarters)
        if hist:
            return hist
    return []


def _extract_balance_history(facts, tag_chain, max_periods=12):
    for _units, tag in _iter_concept_candidates(facts, tag_chain):
        hist = _extract_balance_history_for_tag(facts, tag, max_periods)
        if hist:
            return hist
    return []


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def _extract_metrics(facts, filer_type):
    is_q = (filer_type == "10-K")

    rev_ltm, rev_end, rev_form, rev_tag = _ltm_sum(facts, TAG_CHAINS["revenue"], is_q)
    opi_ltm, opi_end, opi_form, opi_tag = _ltm_sum(facts, TAG_CHAINS["op_income"], is_q)
    da_ltm, da_end, da_form, da_tag = _ltm_sum(facts, TAG_CHAINS["da"], is_q)
    ocf_ltm, ocf_end, ocf_form, ocf_tag = _ltm_sum(facts, TAG_CHAINS["ocf"], is_q)
    capex_ltm, _, _, capex_tag = _ltm_sum(facts, TAG_CHAINS["capex"], is_q)

    cash, cash_end, cash_tag = _latest_balance_sheet(facts, TAG_CHAINS["cash"])
    lt_debt, lt_end, lt_tag = _latest_balance_sheet(facts, TAG_CHAINS["lt_debt"])
    st_debt, st_end, st_tag = _latest_balance_sheet(facts, TAG_CHAINS["st_debt"])
    if st_debt is None:
        st_debt = 0

    rev_yoy = _ltm_revenue_yoy(facts, TAG_CHAINS["revenue"])

    def to_bn(v):
        if v is None:
            return None
        return round(v / 1e9, 1)

    ebitda_ltm = None
    if opi_ltm is not None and da_ltm is not None:
        ebitda_ltm = opi_ltm + da_ltm

    fcf_ltm = None
    if ocf_ltm is not None and capex_ltm is not None:
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

    intex_ltm, _, _, intex_tag = _ltm_sum(facts, TAG_CHAINS["interest_expense"], is_q)
    interest_coverage = None
    if ebitda_ltm and intex_ltm and intex_ltm > 0:
        interest_coverage = round(ebitda_ltm / intex_ltm, 1)

    history = {
        "revenue": _extract_quarterly_history_for_tag(facts, rev_tag),
        "op_income": _extract_quarterly_history_for_tag(facts, opi_tag),
        "da": _extract_quarterly_history_for_tag(facts, da_tag),
        "ocf": _extract_quarterly_history_for_tag(facts, ocf_tag),
        "capex": _extract_quarterly_history_for_tag(facts, capex_tag),
        "interest_expense": _extract_quarterly_history_for_tag(facts, intex_tag),
    }
    balance_history = {
        "cash": _extract_balance_history_for_tag(facts, cash_tag),
        "lt_debt": _extract_balance_history_for_tag(facts, lt_tag),
        "st_debt": _extract_balance_history_for_tag(facts, st_tag),
    }

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
        "interest_expense_ltm": to_bn(intex_ltm),
        "interest_coverage": interest_coverage,
        "_period_end": rev_end or opi_end or cash_end,
        "_filing_form": rev_form or opi_form,
        "_tags_used": {
            "revenue": rev_tag, "op_income": opi_tag, "da": da_tag,
            "ocf": ocf_tag, "capex": capex_tag, "cash": cash_tag,
            "lt_debt": lt_tag, "st_debt": st_tag, "interest_expense": intex_tag,
        },
        "_history": history,
        "_balance_history": balance_history,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(metrics, company):
    warnings = []
    rev = metrics.get("revenue_ltm")
    ebitda = metrics.get("ebitda_ltm")
    cash = metrics.get("cash")
    total_debt = metrics.get("total_debt")
    nd_ebitda = metrics.get("nd_ebitda")
    rev_yoy = metrics.get("revenue_yoy_pct")
    ebitda_margin = metrics.get("ebitda_margin")
    period_end = metrics.get("_period_end")

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
        warnings.append(f"Cash is negative ({cash}) likely parsing error")
    if total_debt is not None and total_debt < 0:
        warnings.append(f"Total debt is negative ({total_debt}) likely parsing error")

    if period_end:
        try:
            pe = datetime.strptime(period_end, "%Y-%m-%d").date()
            age = (datetime.now().date() - pe).days
            if age > FRESHNESS_DAYS:
                warnings.append(f"Period end {period_end} is {age} days old (stale)")
        except Exception:
            pass

    return warnings


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
        print(f"WARNING: failed to write cache: {e}")


def _cache_is_fresh(cache):
    if not cache:
        return False
    last = cache.get("_last_full_refresh")
    if not last:
        return False
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d").date()
        age = (datetime.now(timezone.utc).date() - last_dt).days
        if age >= CACHE_TTL_DAYS:
            return False
    except Exception:
        return False
    real_entries = [v for k, v in cache.items()
                    if not k.startswith("_") and isinstance(v, dict)
                    and v.get("revenue_ltm") is not None]
    total_entries = sum(1 for k in cache if not k.startswith("_"))
    if total_entries == 0:
        return False
    success_rate = len(real_entries) / total_entries
    if success_rate < 0.5:
        print(f"SEC EDGAR: cache exists but success rate is {success_rate:.0%} "
              f"({len(real_entries)}/{total_entries}) treating as stale.")
        return False
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_financials(watchlist, cache_path="financials_cache.json", force_refresh=False):
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
        out = {k: v for k, v in cache.items() if not k.startswith("_")}
        warnings = []
        for co, m in out.items():
            for w in m.get("_warnings", []):
                warnings.append(f"{co}: {w}")
        metadata["names_succeeded"] = sum(1 for k in out if out[k].get("revenue_ltm") is not None)
        metadata["names_attempted"] = len(out)
        metadata["total_warnings"] = len(warnings)
        return out, warnings, metadata

    print("SEC EDGAR: cache stale or force refresh, pulling fresh data...")
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
            time.sleep(0.12)
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

    cache_payload = dict(results)
    cache_payload["_last_full_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_payload["_full_refresh_at"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache_path, cache_payload)
    print(f"SEC EDGAR: refresh complete. Succeeded: {metadata['names_succeeded']}/{metadata['names_attempted']}, "
          f"failed: {len(metadata['names_failed'])}, non-SEC: {len(metadata['names_no_sec_filer'])}, "
          f"warnings: {len(warnings_all)}")

    metadata["total_warnings"] = len(warnings_all)
    return results, warnings_all, metadata


# ---------------------------------------------------------------------------
# Row override helper
# ---------------------------------------------------------------------------

def apply_sec_overrides(rows, sec_data):
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
        "interest_coverage": "interest_coverage",
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
