"""
Red Flags engine for credit surveillance.

Computes 9 of the 12 universal flags from available data:
  1. Leverage too high       (ND/EBITDA > 5.0x)
  2. Leverage climbing fast  (ND/EBITDA up >1.0x YoY)
  3. Coverage thin           (EBITDA/Interest < 3.0x)
  4. Burning cash            (FCF negative 2 quarters)
  7. Revenue shrinking       (>5% YoY)
  8. Margin compression      (>300bps YoY)
  9. Stock collapse          (>25% in 3 months)
 10. Rating pressure         (downgrade/neg outlook 12m)
 11. Bad news in filings     (keyword scan on key_dev)

Skipped (need data not in XBRL companyfacts):
  5. Wall of maturities (needs debt schedule)
  6. Refi at higher rates   (needs coupon data)
 12. Liquidity squeeze      (needs revolver availability)

Each flag returns one of:
  "FLAGGED"  - hard threshold breached
  "WATCH"    - approaching threshold (within 20% buffer)
  "CLEAR"    - no concern
  "N/A"      - insufficient data to evaluate
"""

from datetime import datetime, timedelta

# Flag metadata - definitions, thresholds, what powers each flag
FLAG_DEFINITIONS = [
    {
        "id": "leverage_high",
        "number": 1,
        "name": "Leverage Too High",
        "threshold": "ND/EBITDA > 5.0x",
        "watch_threshold": "ND/EBITDA > 4.0x",
        "description": "Net Debt to LTM EBITDA exceeds 5.0x is a hard threshold; 4.0-5.0x is a watch level.",
    },
    {
        "id": "leverage_climbing",
        "number": 2,
        "name": "Leverage Climbing",
        "threshold": "ND/EBITDA +1.0x YoY",
        "watch_threshold": "ND/EBITDA +0.5x YoY",
        "description": "YoY increase in leverage of more than 1.0 turn signals deteriorating capital structure.",
    },
    {
        "id": "coverage_thin",
        "number": 3,
        "name": "Coverage Thin",
        "threshold": "EBITDA/Interest < 3.0x",
        "watch_threshold": "EBITDA/Interest < 4.5x",
        "description": "Interest coverage below 3.0x signals stress; 3.0-4.5x is a watch level.",
    },
    {
        "id": "burning_cash",
        "number": 4,
        "name": "Burning Cash",
        "threshold": "FCF negative 2 quarters",
        "watch_threshold": "FCF negative 1 quarter",
        "description": "Two consecutive quarters of negative free cash flow is a hard signal.",
    },
    {
        "id": "revenue_shrinking",
        "number": 7,
        "name": "Revenue Shrinking",
        "threshold": "Revenue YoY < -5%",
        "watch_threshold": "Revenue YoY < -2%",
        "description": "Negative LTM revenue growth signals demand or pricing problems.",
    },
    {
        "id": "margin_compression",
        "number": 8,
        "name": "Margin Compression",
        "threshold": "EBITDA margin -300bps YoY",
        "watch_threshold": "EBITDA margin -150bps YoY",
        "description": "Significant margin compression suggests cost pressure or competitive erosion.",
    },
    {
        "id": "stock_collapse",
        "number": 9,
        "name": "Stock Collapse",
        "threshold": "YTD return < -25%",
        "watch_threshold": "YTD return < -15%",
        "description": "Equity market signal of deteriorating credit prospects (YTD used as proxy for 3M).",
    },
    {
        "id": "rating_pressure",
        "number": 10,
        "name": "Rating Pressure",
        "threshold": "2+ Negative outlooks OR recent downgrade",
        "watch_threshold": "1 Negative outlook",
        "description": "Agency signals: outlook changes and rating actions precede formal downgrades.",
    },
    {
        "id": "bad_news",
        "number": 11,
        "name": "Bad News in Filings",
        "threshold": "Key dev mentions covenant/default/restructuring",
        "watch_threshold": "Key dev mentions downgrade/lawsuit/investigation",
        "description": "Material adverse developments from Claude's news synthesis.",
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

    # Need: current ND/EBITDA and ND/EBITDA from ~4 quarters ago
    current_nd = _to_float(row.get("nd_ebitda"))

    # Compute prior-year ND/EBITDA
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

    # Prior balance sheet from 4 quarters ago (index 4 in newest-first list)
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
        return "FLAGGED", f"Leverage +{delta:.1f}x YoY ({prior_leverage:.1f}x → {current_nd:.1f}x)"
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
        # Fall back to current FCF only
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
        # Fall back to LTM
        fcf = _to_float(row.get("fcf_ltm"))
        if fcf is None:
            return "N/A", "Insufficient FCF history"
        if fcf < 0:
            return "WATCH", f"FCF LTM negative ({fcf:.1f}); no quarterly detail"
        return "CLEAR", f"FCF LTM = {fcf:.1f}; no quarterly detail"

    # Match periods to compute quarterly FCF
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
    return "CLEAR", f"FCF positive recent quarters"


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
    delta_bps = (current_margin - prior_margin) * 100  # percentage points to bps

    if delta_bps < -300:
        return "FLAGGED", f"EBITDA margin {prior_margin:.1f}% → {current_margin:.1f}% ({delta_bps:+.0f}bps)"
    if delta_bps < -150:
        return "WATCH", f"EBITDA margin {prior_margin:.1f}% → {current_margin:.1f}% ({delta_bps:+.0f}bps)"
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

    # Check for recent downgrades by date proximity (12-month window)
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


# Dispatch table: flag id -> evaluator function
EVALUATORS = {
    "leverage_high": _evaluate_leverage_high,
    "leverage_climbing": _evaluate_leverage_climbing,
    "coverage_thin": _evaluate_coverage_thin,
    "burning_cash": _evaluate_burning_cash,
    "revenue_shrinking": _evaluate_revenue_shrinking,
    "margin_compression": _evaluate_margin_compression,
    "stock_collapse": _evaluate_stock_collapse,
    "rating_pressure": _evaluate_rating_pressure,
    "bad_news": _evaluate_bad_news,
}


def evaluate_flags(rows, sec_data=None):
    """
    For each row in `rows`, compute all 9 flags and attach to the row.
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
    Map flag count to tier label (similar to concern score tier).
      0 hard flags: Comfortable
      1-2 hard: Watch
      3-4 hard: Review
      5+ hard: Escalate
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
