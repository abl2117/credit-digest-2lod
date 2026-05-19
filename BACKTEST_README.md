# Backtest Audit - Data Quality Validation

## What it does

Compares the SEC EDGAR-derived financials in `financials_cache.json` against
"as-filed" values reconstructed from the same SEC XBRL source, but using
an independent extraction path. Flags any name/metric where our pipeline
diverges materially from what SEC reports.

This is the institutional discipline that backs up the claim: **"Our
dashboard data matches SEC filings to within 1%."**

## How to use

### Manual run (recommended for first audit)

In your repo, after the daily workflow has built `financials_cache.json`:

```bash
# Install dependencies (none needed - pure stdlib)
python backtest_audit.py
```

This runs through all 81 companies, audits ~6 metrics each, and writes
`backtest_results.json` with variance per name/metric. Takes ~3-4 minutes
(rate-limited to SEC's 10 req/sec policy).

### Options

```bash
python backtest_audit.py              # Standard: writes results, prints summary
python backtest_audit.py --verbose    # Show every comparison as it runs
python backtest_audit.py --summary    # Print last summary without re-running
```

## What gets compared

Six core metrics per company:
- Revenue (LTM)
- Operating Income (LTM)
- D&A from Cash Flow Statement (LTM)
- Cash from Operations (LTM)
- CapEx (LTM)
- Cash & Equivalents

These cover the building blocks of EBITDA (= Op Income + D&A) and FCF
(= CFO - CapEx), plus the balance-sheet anchor (Cash).

## Interpretation

### Tier classification

| Tier | Threshold | Meaning |
|------|-----------|---------|
| PASS | within 1.0% | Acceptable for credit analysis |
| WARN | 1.0% - 5.0% | Worth reviewing; may indicate methodology difference |
| FAIL | greater than 5.0% | Material variance; investigate tag chain or definition |
| NO_DATA | one side missing | SEC has data we don't pull, or vice versa |

### Common causes of variance

1. **FAIL** with audit value much higher than cache:
   - Our tag chain may be missing a more specific variant
   - Example: Amazon CapEx may need `PaymentsToAcquirePropertyPlantAndEquipmentExcludingCapitalLeases`

2. **WARN** with small but consistent variance:
   - Different tag chains can pick up slightly different scope
     (e.g., D&A vs DD&A including depletion vs not)
   - Acceptable if methodology is documented

3. **NO_DATA**:
   - Foreign filers (20-F) with sparse XBRL coverage
   - Some companies don't tag certain metrics
   - Mostly expected for: Toyota, Nissan, Imperial Brands, AB InBev, BP

## Output structure

`backtest_results.json`:

```json
{
  "audit_completed_at": "2026-05-19T11:45:00Z",
  "total_comparisons": 426,
  "tier_breakdown": {
    "PASS": 380, "WARN": 28, "FAIL": 12, "NO_DATA": 6
  },
  "per_metric_breakdown": {
    "revenue_ltm": {"PASS": 75, "WARN": 5, "FAIL": 1, "NO_DATA": 0},
    ...
  },
  "results": [
    {
      "company": "AT&T",
      "metric": "revenue_ltm",
      "audit_value_bn": 123.7,
      "cache_value_bn": 123.7,
      "variance_pct": 0.0,
      "tier": "PASS",
      "tag_used": "Revenues",
      "period_end": "2026-03-31"
    },
    ...
  ]
}
```

## Next steps after first audit

1. **Review top FAIL cases** in the summary. For each:
   - What tag did the audit script use?
   - What tag did sec_edgar.py use? (check `financials_cache.json` `_tags_used` field)
   - Are they expected to differ? If yes, document it. If no, fix sec_edgar.py.

2. **Review WARN tier** for any patterns:
   - Same company, all metrics warning -> likely fiscal year alignment issue
   - Same metric across many companies -> likely tag chain issue in sec_edgar.py

3. **Track over time**:
   - Run the audit weekly (Friday alongside the full Claude refresh)
   - Watch for new FAIL cases that emerge after sec_edgar.py changes

## Future integration (next session)

- Add "Data Quality" section to Methodology tab showing latest audit summary
- Auto-run audit weekly as part of GitHub Actions workflow
- Show per-name data quality indicator next to each company in Financials tab

## Cost

- Pure SEC API calls (free, no Anthropic charges)
- Rate-limited to 10 req/sec to comply with SEC's fair-use policy
- ~3-4 minutes for full 81-name watchlist
