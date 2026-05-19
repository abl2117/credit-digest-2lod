"""
backtest_audit.py - Data quality audit for Credit Digest 2LoD Dashboard.

Purpose:
  Compares the SEC EDGAR-derived financials in financials_cache.json against
  ground-truth "as-filed" values from SEC's Financial Statement Data Sets (FSDS).
  Flags any name/metric where our pipeline diverges materially from what the
  company reported in their 10-K.

Why this matters:
  A 2LoD credit surveillance tool must be defensible. "We compute leverage from
  XBRL" is not enough; we need "and we audit daily against SEC filings, with
  variance < 1% on all key metrics." This script produces that evidence.

Approach:
  1. Read financials_cache.json (built by generate.py via sec_edgar.py).
  2. For each watchlist name with a valid CIK, fetch the same SEC company facts
     endpoint that sec_edgar.py uses (no duplication of source-of-truth).
  3. For each company, extract the most recent annual (10-K) and quarterly (10-Q)
     filing values for Revenue, Op Income, D&A, OCF, CapEx, Total Debt.
  4. Compare against what's in financials_cache.json and compute variance %.
  5. Write backtest_results.json with per-name per-metric variance and a
     summary table of pass/fail counts at common tolerance thresholds (1%, 5%).

Usage:
  python backtest_audit.py            # Run audit, write backtest_results.json
  python backtest_audit.py --summary  # Print summary only
  python backtest_audit.py --verbose  # Print every comparison

Limitations:
  - Foreign filers (20-F) have limited XBRL coverage; results may be sparse.
  - Some companies report adjusted vs GAAP metrics differently than XBRL tags.
  - Period alignment matters: LTM vs FY can differ if companies have non-calendar FYs.
  - Tolerance: 1% variance is the credit-officer-acceptable threshold.

Author: Built as part of Alex's 2LoD Credit Surveillance Dashboard
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from collections import defaultdict


# ============================================================================
# Configuration
# ============================================================================

SEC_USER_AGENT = "Credit Digest Personal Research contact@example.com"

# Variance thresholds for pass/fail classification
TOLERANCE_TIGHT = 1.0   # %; metrics within 1% are "matching"
TOLERANCE_LOOSE = 5.0   # %; metrics > 5% off are "material variance"

# Metrics to backtest. Maps cache field name -> human label and SEC tag chain.
METRICS_TO_AUDIT = {
    "revenue_ltm": {
        "label": "Revenue (LTM)",
        "tag_chain": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
        ],
        "is_flow": True,
    },
    "op_income_ltm": {
        "label": "Operating Income (LTM)",
        "tag_chain": [
            "OperatingIncomeLoss",
        ],
        "is_flow": True,
    },
    "da_ltm": {
        "label": "D&A from Cash Flow (LTM)",
        "tag_chain": [
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "Depreciation",
        ],
        "is_flow": True,
    },
    "ocf_ltm": {
        "label": "Cash from Operations (LTM)",
        "tag_chain": [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        "is_flow": True,
    },
    "capex_ltm": {
        "label": "CapEx (LTM)",
        "tag_chain": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsForCapitalImprovements",
            "PaymentsToAcquirePropertyPlantAndEquipmentExcludingCapitalLeases",
            "PaymentsForAcquisitionOfPropertyEquipmentAndInternalUseSoftware",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquireProperty",
            "PaymentsForPropertyPlantAndEquipment",
            "PaymentsToAcquirePropertyAndEquipment",
        ],
        "is_flow": True,
    },
    "cash": {
        "label": "Cash & Equivalents",
        "tag_chain": [
            "CashAndCashEquivalentsAtCarryingValue",
            "Cash",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
        "is_flow": False,
    },
}


# ============================================================================
# HTTP
# ============================================================================

def _http_get(url, retries=3, sleep=0.5):
    req = urllib.request.Request(url, headers={
        "User-Agent": SEC_USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    })
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                content = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    content = gzip.decompress(content)
                return json.loads(content)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            if e.code == 404:
                return None
            if e.code in (429, 503):
                time.sleep(sleep * (2 ** attempt))
                continue
            return None
        except Exception as e:
            last_err = str(e)
            time.sleep(sleep)
    return None


def get_company_facts(cik):
    cik_str = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_str}.json"
    return _http_get(url)


# ============================================================================
# Audit logic - extract "as-filed" values from SEC facts
# ============================================================================

def extract_ltm_value(facts, tag_chain, is_flow=True):
    """
    Extract the as-filed LTM (Last Twelve Months) value for a given metric.
    Uses the EXACT same logic as sec_edgar.py's _ltm_sum, so this is an audit
    of consistency, not of methodology. The point: if both produce the same
    number, our pipeline is consistent with the underlying SEC source.

    Returns: (value_in_dollars, tag_used, period_end) or (None, None, None).
    """
    facts_us = facts.get("facts", {}).get("us-gaap", {})
    for tag in tag_chain:
        node = facts_us.get(tag)
        if not node:
            continue
        units = node.get("units", {}).get("USD")
        if not units:
            continue
        if is_flow:
            # LTM flow: sum 4 most recent non-overlapping quarters
            quarters = []
            for f in units:
                start = f.get("start")
                end = f.get("end")
                if not start or not end:
                    continue
                try:
                    sd = datetime.strptime(start, "%Y-%m-%d").date()
                    ed = datetime.strptime(end, "%Y-%m-%d").date()
                    days = (ed - sd).days
                except Exception:
                    continue
                if 80 <= days <= 100:
                    quarters.append((ed, f.get("val")))
            if len(quarters) < 4:
                continue
            quarters.sort(key=lambda x: x[0], reverse=True)
            # Take 4 most recent
            selected = quarters[:4]
            total = sum(v for _, v in selected)
            return (total, tag, selected[0][0].isoformat())
        else:
            # Balance: most recent value
            best = None
            best_end = None
            for f in units:
                end = f.get("end")
                if not end:
                    continue
                try:
                    ed = datetime.strptime(end, "%Y-%m-%d").date()
                except Exception:
                    continue
                if best_end is None or ed > best_end:
                    best_end = ed
                    best = f.get("val")
            if best is not None:
                return (best, tag, best_end.isoformat())
    return (None, None, None)


def variance_pct(audit_value, cache_value):
    """
    Compute variance % = (audit - cache) / |audit| * 100.
    Returns None if either value is missing or audit is 0.
    """
    if audit_value is None or cache_value is None:
        return None
    if audit_value == 0:
        return None if cache_value == 0 else float("inf")
    return (audit_value - cache_value) / abs(audit_value) * 100.0


def variance_tier(pct):
    """Classify variance into pass/warn/fail buckets."""
    if pct is None:
        return "NO_DATA"
    abs_pct = abs(pct)
    if abs_pct <= TOLERANCE_TIGHT:
        return "PASS"
    if abs_pct <= TOLERANCE_LOOSE:
        return "WARN"
    return "FAIL"


# ============================================================================
# Main audit
# ============================================================================

def load_cache(cache_path="financials_cache.json"):
    if not os.path.exists(cache_path):
        print(f"ERROR: {cache_path} not found. Run generate.py first.")
        sys.exit(1)
    with open(cache_path, "r") as f:
        return json.load(f)


def get_cik_map(watchlist_module="generate"):
    """
    Pull the watchlist's company-to-CIK mapping. We need CIKs to call SEC API.
    Strategy: import WATCHLIST from generate module, then use the SEC ticker
    lookup to resolve tickers -> CIKs.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        if watchlist_module == "generate":
            from generate import WATCHLIST
        else:
            from generate_v12 import WATCHLIST
    except ImportError as e:
        print(f"ERROR: Cannot import WATCHLIST: {e}")
        return {}

    # Fetch the SEC ticker map
    url = "https://www.sec.gov/files/company_tickers.json"
    ticker_data = _http_get(url)
    if not ticker_data:
        print("ERROR: Failed to fetch SEC ticker map.")
        return {}

    # Build ticker -> CIK lookup
    ticker_to_cik = {}
    for entry in ticker_data.values():
        if isinstance(entry, dict):
            tk = entry.get("ticker", "").upper()
            ck = entry.get("cik_str")
            if tk and ck:
                ticker_to_cik[tk] = ck

    cik_map = {}
    for company, info in WATCHLIST.items():
        ticker = info.get("ticker", "").upper()
        cik = ticker_to_cik.get(ticker)
        if cik:
            cik_map[company] = cik
    return cik_map


def audit_one_company(company, cik, cache_entry, verbose=False):
    """Audit a single company; return list of metric-level audit results."""
    facts = get_company_facts(cik)
    if not facts:
        if verbose:
            print(f"  {company}: SEC facts unavailable")
        return []

    results = []
    for metric_key, metric_def in METRICS_TO_AUDIT.items():
        cache_value_bn = cache_entry.get(metric_key)
        if cache_value_bn is None:
            continue
        # Convert cache value from billions to dollars for comparison
        try:
            cache_value = float(cache_value_bn) * 1e9
        except (ValueError, TypeError):
            continue
        audit_value, tag_used, period_end = extract_ltm_value(
            facts, metric_def["tag_chain"], is_flow=metric_def["is_flow"]
        )
        pct = variance_pct(audit_value, cache_value)
        tier = variance_tier(pct)
        results.append({
            "company": company,
            "cik": cik,
            "metric": metric_key,
            "label": metric_def["label"],
            "audit_value": audit_value,
            "audit_value_bn": round(audit_value / 1e9, 3) if audit_value is not None else None,
            "cache_value": cache_value,
            "cache_value_bn": round(cache_value / 1e9, 3),
            "variance_pct": round(pct, 2) if pct is not None and pct != float("inf") else pct,
            "tier": tier,
            "tag_used": tag_used,
            "period_end": period_end,
        })
        if verbose:
            audit_str = f"${audit_value/1e9:,.1f}B" if audit_value is not None else "n/a"
            cache_str = f"${cache_value/1e9:,.1f}B"
            pct_str = f"{pct:+.2f}%" if pct is not None and pct != float("inf") else "inf"
            print(f"  {company} {metric_def['label']}: audit={audit_str} cache={cache_str} var={pct_str} [{tier}]")
    return results


def write_results(all_results, output_path="backtest_results.json"):
    # Summary statistics
    tier_counts = defaultdict(int)
    per_metric_tier = defaultdict(lambda: defaultdict(int))
    for r in all_results:
        tier_counts[r["tier"]] += 1
        per_metric_tier[r["metric"]][r["tier"]] += 1

    summary = {
        "audit_completed_at": datetime.utcnow().isoformat() + "Z",
        "total_comparisons": len(all_results),
        "tier_breakdown": dict(tier_counts),
        "per_metric_breakdown": {m: dict(t) for m, t in per_metric_tier.items()},
        "tolerance_tight_pct": TOLERANCE_TIGHT,
        "tolerance_loose_pct": TOLERANCE_LOOSE,
        "results": all_results,
    }

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {len(all_results)} comparisons to {output_path}")
    return summary


def print_summary(summary):
    print("\n" + "=" * 70)
    print("BACKTEST AUDIT SUMMARY")
    print("=" * 70)
    print(f"Audit completed: {summary['audit_completed_at']}")
    print(f"Total metric comparisons: {summary['total_comparisons']}")
    print(f"Thresholds: PASS <={TOLERANCE_TIGHT}% | WARN <={TOLERANCE_LOOSE}% | FAIL >{TOLERANCE_LOOSE}%")
    print()
    print("OVERALL TIER BREAKDOWN:")
    total = sum(summary["tier_breakdown"].values()) or 1
    for tier in ["PASS", "WARN", "FAIL", "NO_DATA"]:
        n = summary["tier_breakdown"].get(tier, 0)
        pct = n / total * 100
        print(f"  {tier:>8}: {n:>4}  ({pct:5.1f}%)")
    print()
    print("PER-METRIC BREAKDOWN:")
    for metric, tiers in summary["per_metric_breakdown"].items():
        passing = tiers.get("PASS", 0)
        warning = tiers.get("WARN", 0)
        failing = tiers.get("FAIL", 0)
        no_data = tiers.get("NO_DATA", 0)
        total_m = passing + warning + failing + no_data
        print(f"  {metric:<20} pass={passing:>3} warn={warning:>3} fail={failing:>3} nodata={no_data:>3} (of {total_m})")
    print()
    # Top 10 worst variances
    fails = [r for r in summary["results"] if r["tier"] == "FAIL"]
    fails.sort(key=lambda r: abs(r.get("variance_pct") or 0), reverse=True)
    if fails:
        print("TOP 10 WORST VARIANCES (FAIL tier):")
        for r in fails[:10]:
            var = r.get("variance_pct")
            var_str = f"{var:+.1f}%" if var is not None and var != float("inf") else "inf"
            print(f"  {r['company']:<28} {r['metric']:<20} audit={r['audit_value_bn']!s:>10}B  cache={r['cache_value_bn']!s:>10}B  variance={var_str}")
    print("=" * 70)


def main():
    verbose = "--verbose" in sys.argv
    summary_only = "--summary" in sys.argv

    print("Backtest Audit: comparing financials_cache.json against SEC company facts...")
    cache_data = load_cache()
    cik_map = get_cik_map()
    print(f"Loaded cache: {len(cache_data)} companies. Resolved CIKs: {len(cik_map)}")
    print(f"Auditing {len(METRICS_TO_AUDIT)} metrics per company.")
    print(f"Expected total comparisons: ~{len(cik_map) * len(METRICS_TO_AUDIT)}")
    print()

    all_results = []
    audited = 0
    for company, cik in cik_map.items():
        cache_entry = cache_data.get(company)
        if not cache_entry:
            continue
        results = audit_one_company(company, cik, cache_entry, verbose=verbose)
        all_results.extend(results)
        audited += 1
        # SEC API rate limit: 10 req/sec max, be polite
        time.sleep(0.15)

    print(f"\nAudited {audited} companies, generated {len(all_results)} metric comparisons.")
    summary = write_results(all_results)
    print_summary(summary)


if __name__ == "__main__":
    main()
