"""
Red Flags engine for credit surveillance.

Computes the universal 15-flag framework. Currently 11 of 15 are deterministically
evaluated; the remaining 4 are rendered as N/A placeholders with documented
pending status (data sources require qualitative text analysis or pipelines
not yet built).

COMPUTED (11):
  1. Leverage too high       (ND/EBITDA > 5.0x)
  2. Leverage climbing fast  (ND/EBITDA up >1.0x YoY)
  3. Coverage thin           (EBITDA/Interest < 3.0x)
  4. Burning cash            (FCF negative 2 quarters)
  5. Wall of maturities      (>20% of total debt maturing in 24m)
  7. Revenue shrinking       (>5% YoY)
  8. Margin compression      (>300bps YoY)
  9. Stock collapse          (>25% YTD)
 10. Rating pressure         (downgrade/neg outlook 12m)
 11. Bad news in filings     (keyword scan on key_dev)
 12. Liquidity squeeze       (cash / ST debt < 1.0x)

PENDING (4) - rendered as N/A in heat map:
  6. Refi at higher rates    (needs bond coupon data, not in XBRL)
 13. Going concern           (needs auditor opinion text from 10-K)
 14. Insider selling         (needs Form 4 pipeline)
 15. Geographic risk         (needs 10-K risk factors text analysis)

Each flag returns one of:
  "FLAGGED"  - hard threshold breached
  "WATCH"    - approaching threshold (within 20% buffer)
  "CLEAR"    - no concern
  "N/A"      - insufficient data to evaluate, or flag not yet implemented
"""

from datetime import datetime, timedelta

# Flag metadata. The "implemented" field tells generate.py whether to render
# computed results or a tooltip-explained N/A placeholder.
FLAG_DEFINITIONS = [
    {
        "id": "leverage_high",
        "number": 1,
        "name": "Leverage Too High",
        "threshold": "ND/EBITDA > 5.0x",
        "watch_threshold": "ND/EBITDA > 4.0x",
        "description": "Net Debt to LTM EBITDA exceeds 5.0x is a hard threshold; 4.0-5.0x is a watch level.",
        "implemented": True,
    },
    {
        "id": "leverage_climbing",
        "number": 2,
        "name": "Leverage Climbing",
        "threshold": "ND/EBITDA +1.0x YoY",
        "watch_threshold": "ND/EBITDA +0.5x YoY",
        "description": "YoY increase in leverage of more than 1.0 turn signals deteriorating capital structure.",
        "implemented": True,
    },
    {
        "id": "coverage_thin",
        "number": 3,
        "name": "Coverage Thin",
        "threshold": "EBITDA/Interest < 3.0x",
        "watch_threshold": "EBITDA/Interest < 4.5x",
        "description": "Interest coverage below 3.0x signals stress; 3.0-4.5x is a watch level.",
        "implemented": True,
    },
    {
        "id": "burning_cash",
        "number": 4,
        "name": "Burning Cash",
        "threshold": "FCF negative 2 quarters",
        "watch_threshold": "FCF negative 1 quarter",
        "description": "Two consecutive quarters of negative free cash flow is a hard signal.",
        "implemented": True,
    },
    {
        "id": "wall_of_maturities",
        "number": 5,
        "name": "Wall of Maturities",
        "threshold": ">20% of total debt due in 24m",
        "watch_threshold": ">10% of total debt due in 24m",
        "description": "Significant near-term debt maturities create refinancing risk if capital markets close.",
        "implemented": True,
    },
    {
        "id": "refi_higher_rates",
        "number": 6,
        "name": "Refi at Higher Rates",
        "threshold": "Avg coupon to refi at >150bps above current",
        "watch_threshold": "Avg coupon to refi at >75bps above current",
        "description": "Pending - requires bond-level coupon data not available in SEC XBRL. Defer to dedicated bond analytics source.",
        "implemented": False,
    },
    {
        "id": "revenue_shrinking",
        "number": 7,
        "name": "Revenue Shrinking",
        "threshold": "Revenue YoY < -5%",
        "watch_threshold": "Revenue YoY < -2%",
        "description": "Negative LTM revenue growth signals demand or pricing problems.",
        "implemented": True,
    },
    {
        "id": "margin_compression",
        "number": 8,
        "name": "Margin Compression",
        "threshold": "EBITDA margin -300bps YoY",
        "watch_threshold": "EBITDA margin -150bps YoY",
        "description": "Significant margin compression suggests cost pressure or competitive erosion.",
        "implemented": True,
    },
    {
        "id": "stock_collapse",
        "number": 9,
        "name": "Stock Collapse",
        "threshold": "YTD return < -25%",
        "watch_threshold": "YTD return < -15%",
        "description": "Equity market signal of deteriorating credit prospects (YTD used as proxy for 3M).",
        "implemented": True,
    },
    {
        "id": "rating_pressure",
        "number": 10,
        "name": "Rating Pressure",
        "threshold": "2+ Negative outlooks OR recent downgrade",
        "watch_threshold": "1 Negative outlook",
        "description": "Agency signals: outlook changes and rating actions precede formal downgrades.",
        "implemented": True,
    },
    {
        "id": "bad_news",
        "number": 11,
        "name": "Bad News in Filings",
        "threshold": "Key dev mentions covenant/default/restructuring",
        "watch_threshold": "Key dev mentions downgrade/lawsuit/investigation",
        "description": "Material adverse developments from Claude's news synthesis.",
        "implemented": True,
    },
    {
        "id": "liquidity_squeeze",
        "number": 12,
        "name": "Liquidity Squeeze",
        "threshold": "Cash / ST Debt < 1.0x",
        "watch_threshold": "Cash / ST Debt < 1.5x",
        "description": "Cash and equivalents below short-term debt obligations signals near-term liquidity stress.",
        "implemented": True,
    },
    {
        "id": "going_concern",
        "number": 13,
        "name": "Going Concern",
        "threshold": "Auditor going concern qualification",
        "watch_threshold": "Substantial doubt language in MD&A",
        "description": "Pending - requires parsing 10-K auditor opinion text. Defer to manual override file for known cases.",
        "implemented": False,
    },
    {
        "id": "insider_selling",
        "number": 14,
        "name": "Insider Selling",
        "threshold": "Large insider sales 90d (>$10MM or >5% of shares)",
        "watch_threshold": "Material insider sales 90d (>$5MM)",
        "description": "Pending - requires Form 4 filing pipeline. Defer to dedicated insider transaction source.",
        "implemented": False,
    },
    {
        "id": "geographic_risk",
        "number": 15,
        "name": "Geographic Risk",
        "threshold": "Material unhedged exposure to sanctioned/conflict region",
        "watch_threshold": "Concentrated single-country revenue (>25%)",
        "description": "Pending - requires parsing 10-K risk factors text. Defer to manual review or qualitative override.",
        "implemented": False,
    },
]


# Trigger keywords for flag 11 (Bad News)
HARD_KEYWORDS = [
    "covenant breach", "covenant violation", "covenant default",
    "default", "missed payment", "missed coupon",
    "restructuring", "chapter 11", "chapter 7", "bankruptcy",
    "going concern",
]
WATCH_KEYWORDS = [
    "downgrade", "downgraded",
    "lawsuit", "litigation", "investigation", "fraud", "sec inquiry",
    "guidance cut", "guidance reduced", "guidance withdrawn",
    "material weakness", "restatement",
    "layoff", "layoffs", "workforce reduction",
    "going private", "strategic review",
]


def _to_float(v):
    """Coerce values that may be strings, floats, or None into floats."""
    if v is None:
        return None
    try:
        s = str(v).strip().replace(',', '').replace('$', '').replace('%', '').replace('+', '')
        if not s or s.lower() in ('n/a', 'na', 'none'):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _ltm_from_history(history_list, prior=False):
    """
    Given a list of quarterly facts (newest first), compute current LTM (sum of 4 most recent
    non-overlapping). If prior=True, compute the LTM from 4 quarters earlier (for YoY comparison).
    Returns ($ value) or None.
    """
    if not history_list or len(history_list) < 4:
        return None
    start_idx = 0 if not prior else 4
    end_idx = start_idx + 4
    if end_idx > len(history_list):
        return None
    quarters = history_list[start_idx:end_idx]
    return sum(q.get("value", 0) for q in quarters if q.get("value") is not None)


def _evaluate_leverage_high(row, sec):
    nd_ebitda = _to_float(row.get("nd_ebitda"))
    if nd_ebitda is None:
        return "N/A", "ND/EBITDA not available"
    if nd_ebitda > 5.0:
        return "FLAGGED", f"ND/EBITDA = {nd_ebitda:.1f}x (>5.0x)"
    if nd_ebitda > 4.0:
        return "WATCH", f"ND/EBITDA = {nd_ebitda:.1f}x (>4.0x watch)"
    return "CLEAR", f"ND/EBITDA = {nd_ebitda:.1f}x"


def _evaluate_leverage_climbing(row, sec):
    """Needs prior-year leverage from history."""
    if not sec:
        return "N/A", "No SEC history available"
    history = sec.get("_history", {})
    balance_history = sec.get("_balance_history", {})

    current_nd = _to_float(row.get("nd_ebitda"))

    opi_hist = history.get("op_income", [])
    da_hist = history.get("da", [])
    lt_debt_hist = balance_history.get("lt_debt", [])
    cash_hist = balance_history.get("cash", [])

    prior_opi_ltm = _ltm_from_history(opi_hist, prior=True)
    prior_da_ltm = _ltm_from_history(da_hist, prior=True)
    if prior_opi_ltm is None or prior_da_ltm is None:
        return "N/A", "Insufficient history"
    prior_ebitda = prior_opi_ltm + prior_da_ltm
    if prior_ebitda <= 0:
        return "N/A", "Prior EBITDA non-positive"

    if len(lt_debt_hist) < 5 or len(cash_hist) < 5:
        return "N/A", "Insufficient balance sheet history"
    prior_lt_debt = lt_debt_hist[4].get("value", 0)
    prior_cash = cash_hist[4].get("value", 0)
    prior_net_debt = prior_lt_debt - prior_cash
    prior_leverage = prior_net_debt / prior_ebitda

    if current_nd is None:
        return "N/A", "Current leverage not available"
    delta = current_nd - prior_leverage
    if delta > 1.0:
        return "FLAGGED", f"Leverage +{delta:.1f}x YoY ({prior_leverage:.1f}x to {current_nd:.1f}x)"
    if delta > 0.5:
        return "WATCH", f"Leverage +{delta:.1f}x YoY (watch)"
    if delta > 0:
        return "CLEAR", f"Leverage +{delta:.1f}x YoY"
    return "CLEAR", f"Leverage {delta:+.1f}x YoY (declining)"


def _evaluate_coverage_thin(row, sec):
    coverage = _to_float(row.get("interest_coverage"))
    if coverage is None:
        return "N/A", "Interest coverage not available"
    if coverage < 3.0:
        return "FLAGGED", f"EBITDA/Interest = {coverage:.1f}x (<3.0x)"
    if coverage < 4.5:
        return "WATCH", f"EBITDA/Interest = {coverage:.1f}x (watch)"
    return "CLEAR", f"EBITDA/Interest = {coverage:.1f}x"


def _evaluate_burning_cash(row, sec):
    """Check last 2 quarters of FCF (OCF - CapEx) from SEC history."""
    if not sec:
        fcf = _to_float(row.get("fcf_ltm"))
        if fcf is None:
            return "N/A", "FCF not available"
        if fcf < 0:
            return "WATCH", f"FCF LTM negative ({fcf:.1f})"
        return "CLEAR", f"FCF LTM = {fcf:.1f}"

    history = sec.get("_history", {})
    ocf_hist = history.get("ocf", [])
    capex_hist = history.get("capex", [])

    if len(ocf_hist) < 2 or len(capex_hist) < 2:
        fcf = _to_float(row.get("fcf_ltm"))
        if fcf is None:
            return "N/A", "Insufficient FCF history"
        if fcf < 0:
            return "WATCH", f"FCF LTM negative ({fcf:.1f}); no quarterly detail"
        return "CLEAR", f"FCF LTM = {fcf:.1f}; no quarterly detail"

    def fcf_for_quarter(idx):
        if idx >= len(ocf_hist) or idx >= len(capex_hist):
            return None
        ocf = ocf_hist[idx].get("value")
        capex = capex_hist[idx].get("value")
        if ocf is None or capex is None:
            return None
        return ocf - abs(capex)

    q0 = fcf_for_quarter(0)
    q1 = fcf_for_quarter(1)

    if q0 is None or q1 is None:
        return "N/A", "Could not compute quarterly FCF"

    if q0 < 0 and q1 < 0:
        return "FLAGGED", f"FCF negative 2 quarters: Q0={q0/1e9:.1f}Bn, Q-1={q1/1e9:.1f}Bn"
    if q0 < 0 or q1 < 0:
        return "WATCH", f"FCF negative 1 quarter: Q0={q0/1e9:.1f}Bn, Q-1={q1/1e9:.1f}Bn"
    return "CLEAR", "FCF positive recent quarters"


def _evaluate_wall_of_maturities(row, sec):
    """
    Flag 5: Wall of Maturities.
    Threshold: ST debt as % of total debt indicates near-term maturity wall.
    This is a proxy - true maturity schedule requires bond-level data. We use the
    ratio of short-term debt (which includes current portion of LTD) to total debt
    as the closest available structured signal.

    Rationale: Current portion of LTD reflects principal due within 12 months. If
    that's a large share of the capital structure, refinancing risk is elevated.
    """
    st_debt = _to_float(row.get("st_debt"))
    total_debt = _to_float(row.get("total_debt"))

    if total_debt is None or total_debt <= 0:
        return "N/A", "Total debt not available"
    if st_debt is None:
        # Treat as zero current portion (clean capital structure)
        return "CLEAR", "No near-term maturities reported"

    pct = st_debt / total_debt * 100
    if pct > 20.0:
        return "FLAGGED", f"{pct:.0f}% of debt is current portion (${st_debt:.1f}Bn of ${total_debt:.1f}Bn)"
    if pct > 10.0:
        return "WATCH", f"{pct:.0f}% of debt is current portion (watch)"
    return "CLEAR", f"{pct:.0f}% of debt is current portion"


def _evaluate_revenue_shrinking(row, sec):
    rev_yoy = _to_float(row.get("revenue_yoy_pct"))
    if rev_yoy is None:
        return "N/A", "Revenue YoY not available"
    if rev_yoy < -5.0:
        return "FLAGGED", f"Revenue YoY = {rev_yoy:.1f}% (<-5%)"
    if rev_yoy < -2.0:
        return "WATCH", f"Revenue YoY = {rev_yoy:.1f}% (watch)"
    return "CLEAR", f"Revenue YoY = {rev_yoy:.1f}%"


def _evaluate_margin_compression(row, sec):
    """Compare current EBITDA margin to prior-year EBITDA margin."""
    if not sec:
        return "N/A", "No SEC history available"
    history = sec.get("_history", {})
    rev_hist = history.get("revenue", [])
    opi_hist = history.get("op_income", [])
    da_hist = history.get("da", [])

    current_rev_ltm = _ltm_from_history(rev_hist, prior=False)
    current_opi_ltm = _ltm_from_history(opi_hist, prior=False)
    current_da_ltm = _ltm_from_history(da_hist, prior=False)
    prior_rev_ltm = _ltm_from_history(rev_hist, prior=True)
    prior_opi_ltm = _ltm_from_history(opi_hist, prior=True)
    prior_da_ltm = _ltm_from_history(da_hist, prior=True)

    if None in (current_rev_ltm, current_opi_ltm, current_da_ltm,
                prior_rev_ltm, prior_opi_ltm, prior_da_ltm):
        return "N/A", "Insufficient history"
    if current_rev_ltm <= 0 or prior_rev_ltm <= 0:
        return "N/A", "Non-positive revenue"

    current_margin = (current_opi_ltm + current_da_ltm) / current_rev_ltm * 100
    prior_margin = (prior_opi_ltm + prior_da_ltm) / prior_rev_ltm * 100
    delta_bps = (current_margin - prior_margin) * 100

    if delta_bps < -300:
        return "FLAGGED", f"EBITDA margin {prior_margin:.1f}% to {current_margin:.1f}% ({delta_bps:+.0f}bps)"
    if delta_bps < -150:
        return "WATCH", f"EBITDA margin {prior_margin:.1f}% to {current_margin:.1f}% ({delta_bps:+.0f}bps)"
    return "CLEAR", f"EBITDA margin stable ({delta_bps:+.0f}bps YoY)"


def _evaluate_stock_collapse(row, sec):
    ytd = _to_float(row.get("stock_ytd"))
    if ytd is None:
        return "N/A", "YTD return not available"
    if ytd < -25.0:
        return "FLAGGED", f"YTD = {ytd:.1f}% (<-25%)"
    if ytd < -15.0:
        return "WATCH", f"YTD = {ytd:.1f}% (watch)"
    return "CLEAR", f"YTD = {ytd:.1f}%"


def _evaluate_rating_pressure(row, sec):
    """Count negative outlooks across agencies. Detect recent action dates within 12m."""
    neg_outlooks = 0
    for f in ("moodys_outlook", "sp_outlook", "fitch_outlook"):
        v = str(row.get(f, "") or "").strip().lower()
        if v in ("negative", "rur"):
            neg_outlooks += 1

    recent_action = False
    today = datetime.now().date()
    for f in ("moodys_date", "sp_date", "fitch_date"):
        d = row.get(f)
        if not d or d == "n/a":
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            if (today - dt).days < 365:
                recent_action = True
                break
        except (ValueError, TypeError):
            continue

    if neg_outlooks >= 2:
        return "FLAGGED", f"{neg_outlooks} negative outlooks across agencies"
    if neg_outlooks == 1 and recent_action:
        return "FLAGGED", "Negative outlook + recent rating action"
    if neg_outlooks == 1:
        return "WATCH", "1 negative outlook"
    if recent_action:
        return "WATCH", "Recent rating action within 12 months"
    return "CLEAR", "Stable ratings"


def _evaluate_bad_news(row, sec):
    """Keyword scan on key_dev."""
    key_dev = str(row.get("key_dev", "") or "").lower()
    if not key_dev or key_dev in ("no material news.", "no material news"):
        return "CLEAR", "No material news"

    hard_hits = [kw for kw in HARD_KEYWORDS if kw in key_dev]
    if hard_hits:
        return "FLAGGED", f"Trigger phrases: {', '.join(hard_hits)}"
    watch_hits = [kw for kw in WATCH_KEYWORDS if kw in key_dev]
    if watch_hits:
        return "WATCH", f"Watch phrases: {', '.join(watch_hits)}"
    return "CLEAR", "No trigger phrases"


def _evaluate_liquidity_squeeze(row, sec):
    """
    Flag 12: Liquidity Squeeze.
    Threshold: Cash / Short-Term Debt < 1.0x = FLAGGED, < 1.5x = WATCH.
    Standard credit-agency liquidity ratio measuring near-term solvency cushion.
    """
    cash = _to_float(row.get("cash"))
    st_debt = _to_float(row.get("st_debt"))

    if cash is None:
        return "N/A", "Cash not available"
    if st_debt is None or st_debt == 0:
        # No short-term debt - liquidity not stressed by this metric
        return "CLEAR", "No short-term debt outstanding"

    ratio = cash / st_debt
    if ratio < 1.0:
        return "FLAGGED", f"Cash/ST Debt = {ratio:.2f}x (${cash:.1f}Bn / ${st_debt:.1f}Bn)"
    if ratio < 1.5:
        return "WATCH", f"Cash/ST Debt = {ratio:.2f}x (watch)"
    return "CLEAR", f"Cash/ST Debt = {ratio:.2f}x"


def _evaluate_pending(row, sec):
    """Default evaluator for flags not yet implemented (returns N/A with pending note)."""
    return "N/A", "Pending - data source not yet wired"


# Dispatch table: flag id -> evaluator function
EVALUATORS = {
    "leverage_high": _evaluate_leverage_high,
    "leverage_climbing": _evaluate_leverage_climbing,
    "coverage_thin": _evaluate_coverage_thin,
    "burning_cash": _evaluate_burning_cash,
    "wall_of_maturities": _evaluate_wall_of_maturities,
    "refi_higher_rates": _evaluate_pending,
    "revenue_shrinking": _evaluate_revenue_shrinking,
    "margin_compression": _evaluate_margin_compression,
    "stock_collapse": _evaluate_stock_collapse,
    "rating_pressure": _evaluate_rating_pressure,
    "bad_news": _evaluate_bad_news,
    "liquidity_squeeze": _evaluate_liquidity_squeeze,
    "going_concern": _evaluate_pending,
    "insider_selling": _evaluate_pending,
    "geographic_risk": _evaluate_pending,
}


def evaluate_flags(rows, sec_data=None):
    """
    For each row in `rows`, compute all 15 flags and attach to the row.
    Each row gets:
      r['_flags']: dict of flag_id -> {"state": "FLAGGED"/"WATCH"/"CLEAR"/"N/A", "reason": "..."}
      r['_flag_count']: int number of flags FLAGGED
      r['_watch_count']: int number of flags WATCH
    Returns (rows, summary_stats).
    """
    sec_data = sec_data or {}
    total_flagged = 0
    total_watch = 0
    by_flag = {f["id"]: {"flagged": 0, "watch": 0, "clear": 0, "na": 0} for f in FLAG_DEFINITIONS}

    for r in rows:
        co = r.get("company", "")
        sec_for_co = sec_data.get(co, {}) if isinstance(sec_data, dict) else {}
        flags = {}
        flag_count = 0
        watch_count = 0
        for flag_def in FLAG_DEFINITIONS:
            fid = flag_def["id"]
            evaluator = EVALUATORS.get(fid)
            if not evaluator:
                continue
            try:
                state, reason = evaluator(r, sec_for_co)
            except Exception as e:
                state, reason = "N/A", f"Error: {str(e)[:80]}"
            flags[fid] = {"state": state, "reason": reason}
            if state == "FLAGGED":
                flag_count += 1
                total_flagged += 1
                by_flag[fid]["flagged"] += 1
            elif state == "WATCH":
                watch_count += 1
                total_watch += 1
                by_flag[fid]["watch"] += 1
            elif state == "CLEAR":
                by_flag[fid]["clear"] += 1
            else:
                by_flag[fid]["na"] += 1
        r["_flags"] = flags
        r["_flag_count"] = flag_count
        r["_watch_count"] = watch_count

    summary = {
        "total_rows": len(rows),
        "total_flagged_triggers": total_flagged,
        "total_watch_triggers": total_watch,
        "by_flag": by_flag,
    }
    return rows, summary


def flag_count_tier(flag_count, watch_count=0):
    """
    Map flag count to tier label.
      0 hard flags: Comfortable
      1-2 hard: Watch
      3-4 hard: Review
      5+ hard: Escalate
    Note: tier thresholds scale with the 11 currently-implemented flags. If we
    later implement Flags 6/13/14/15 the tier boundaries may need adjustment.
    """
    if flag_count >= 5:
        return "Escalate"
    if flag_count >= 3:
        return "Review"
    if flag_count >= 1:
        return "Watch"
    if watch_count >= 3:
        return "Watch"
    return "Comfortable"
