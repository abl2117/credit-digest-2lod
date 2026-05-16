import anthropic
import json
import os
from datetime import datetime, timedelta
import pytz

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("WARNING: yfinance not installed; falling back to Claude-sourced market data.")

# Local modules
try:
    import sec_edgar
    SEC_EDGAR_AVAILABLE = True
except ImportError:
    SEC_EDGAR_AVAILABLE = False
    print("WARNING: sec_edgar module not found; financials will use Claude data only.")

try:
    import run_log
    RUN_LOG_AVAILABLE = True
except ImportError:
    RUN_LOG_AVAILABLE = False

try:
    import red_flags
    RED_FLAGS_AVAILABLE = True
except ImportError:
    RED_FLAGS_AVAILABLE = False
    print("WARNING: red_flags module not found; Red Flags tab will remain placeholder.")

# Date/time
et = pytz.timezone('America/New_York')
now = datetime.now(et)
datetime_str = now.strftime('%B %d, %Y at %I:%M %p ET')
today = now.date()

# Anthropic client
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# Dashboard URL
DASHBOARD_URL = "https://abl2117.github.io/credit-digest-2lod"

# Load ratings override file if present
RATINGS_OVERRIDE = {}
if os.path.exists('ratings_override.json'):
    try:
        with open('ratings_override.json', 'r', encoding='utf-8') as f:
            RATINGS_OVERRIDE = json.load(f)
        print(f"Loaded ratings_override.json with {sum(1 for k in RATINGS_OVERRIDE if not k.startswith('_'))} manual overrides.")
    except Exception as e:
        print(f"WARNING: ratings_override.json failed to parse: {e}")

# Watchlist mapping for yfinance market data pulls
# Watchlist with US-listed tickers and SEC filer type
# filer_type: "10-K" = US domestic filer with quarterly 10-Qs
#             "20-F" = Foreign private issuer (annual only)
#             None   = Non-SEC filer (limited financial data)
WATCHLIST = {
    "AT&T":                    {"ticker": "T",     "filer_type": "10-K", "sector": "Telecom"},
    "Verizon":                 {"ticker": "VZ",    "filer_type": "10-K", "sector": "Telecom"},
    "Comcast":                 {"ticker": "CMCSA", "filer_type": "10-K", "sector": "Telecom"},
    "Disney":                  {"ticker": "DIS",   "filer_type": "10-K", "sector": "Media"},
    "Warner Bros. Discovery":  {"ticker": "WBD",   "filer_type": "10-K", "sector": "Media"},
    "Netflix":                 {"ticker": "NFLX",  "filer_type": "10-K", "sector": "Media"},
    "Amazon":                  {"ticker": "AMZN",  "filer_type": "10-K", "sector": "Tech"},
    "Alphabet":                {"ticker": "GOOGL", "filer_type": "10-K", "sector": "Tech"},
    "Microsoft":               {"ticker": "MSFT",  "filer_type": "10-K", "sector": "Tech"},
    "Oracle":                  {"ticker": "ORCL",  "filer_type": "10-K", "sector": "Tech"},
    "Salesforce":              {"ticker": "CRM",   "filer_type": "10-K", "sector": "Tech"},
    "IBM":                     {"ticker": "IBM",   "filer_type": "10-K", "sector": "Tech"},
    "HP Inc":                  {"ticker": "HPQ",   "filer_type": "10-K", "sector": "Hardware"},
    "HPE":                     {"ticker": "HPE",   "filer_type": "10-K", "sector": "Hardware"},
    "Dell":                    {"ticker": "DELL",  "filer_type": "10-K", "sector": "Hardware"},
    "Nextracker":              {"ticker": "NXT",   "filer_type": "10-K", "sector": "Hardware"},
    "Sanmina":                 {"ticker": "SANM",  "filer_type": "10-K", "sector": "EMS"},
    "Flex Ltd":                {"ticker": "FLEX",  "filer_type": "10-K", "sector": "EMS"},
    "Jabil":                   {"ticker": "JBL",   "filer_type": "10-K", "sector": "EMS"},
    "Arrow Electronics":       {"ticker": "ARW",   "filer_type": "10-K", "sector": "Distribution"},
    "TD Synnex":               {"ticker": "SNX",   "filer_type": "10-K", "sector": "Distribution"},
    "Ingram Micro":            {"ticker": "INGM",  "filer_type": "10-K", "sector": "Distribution"},
    "Kyndryl":                 {"ticker": "KD",    "filer_type": "10-K", "sector": "IT Services"},
    "Cognizant":               {"ticker": "CTSH",  "filer_type": "10-K", "sector": "IT Services"},
    "Equinix":                 {"ticker": "EQIX",  "filer_type": "10-K", "sector": "Datacenter"},
    "Digital Realty":          {"ticker": "DLR",   "filer_type": "10-K", "sector": "Datacenter"},
    "American Tower":          {"ticker": "AMT",   "filer_type": "10-K", "sector": "Towers"},
    "PayPal":                  {"ticker": "PYPL",  "filer_type": "10-K", "sector": "Payments"},
    "Corpay":                  {"ticker": "CPAY",  "filer_type": "10-K", "sector": "Payments"},
    "Booking Holdings":        {"ticker": "BKNG",  "filer_type": "10-K", "sector": "Travel"},
    "Uber":                    {"ticker": "UBER",  "filer_type": "10-K", "sector": "Travel"},
    "Delta":                   {"ticker": "DAL",   "filer_type": "10-K", "sector": "Travel"},
    "Carnival":                {"ticker": "CCL",   "filer_type": "10-K", "sector": "Travel"},
    "Royal Caribbean":         {"ticker": "RCL",   "filer_type": "10-K", "sector": "Travel"},
    "Norwegian Cruise Line":   {"ticker": "NCLH",  "filer_type": "10-K", "sector": "Travel"},
    "General Motors":          {"ticker": "GM",    "filer_type": "10-K", "sector": "Auto"},
    "Tesla":                   {"ticker": "TSLA",  "filer_type": "10-K", "sector": "Auto"},
    "Ford":                    {"ticker": "F",     "filer_type": "10-K", "sector": "Auto"},
    "Toyota":                  {"ticker": "TM",    "filer_type": "20-F", "sector": "Auto"},
    "Nissan":                  {"ticker": "NSANY", "filer_type": None,   "sector": "Auto"},
    "Hyundai":                 {"ticker": "HYMTF", "filer_type": None,   "sector": "Auto"},
    "Boeing":                  {"ticker": "BA",    "filer_type": "10-K", "sector": "Aerospace"},
    "GE Aerospace":            {"ticker": "GE",    "filer_type": "10-K", "sector": "Aerospace"},
    "Walmart":                 {"ticker": "WMT",   "filer_type": "10-K", "sector": "Retail"},
    "AutoZone":                {"ticker": "AZO",   "filer_type": "10-K", "sector": "Retail"},
    "Genuine Parts":           {"ticker": "GPC",   "filer_type": "10-K", "sector": "Retail"},
    "Coca-Cola":               {"ticker": "KO",    "filer_type": "10-K", "sector": "Beverage"},
    "Anheuser-Busch InBev":    {"ticker": "BUD",   "filer_type": "20-F", "sector": "Beverage"},
    "Philip Morris":           {"ticker": "PM",    "filer_type": "10-K", "sector": "Tobacco"},
    "Altria":                  {"ticker": "MO",    "filer_type": "10-K", "sector": "Tobacco"},
    "Imperial Brands":         {"ticker": "IMBBY", "filer_type": None,   "sector": "Tobacco"},
    "Universal Corporation":   {"ticker": "UVV",   "filer_type": "10-K", "sector": "Tobacco"},
    "Nike":                    {"ticker": "NKE",   "filer_type": "10-K", "sector": "Consumer"},
    "Kimberly-Clark":          {"ticker": "KMB",   "filer_type": "10-K", "sector": "Consumer"},
    "Whirlpool":               {"ticker": "WHR",   "filer_type": "10-K", "sector": "Consumer"},
    "Mondelez":                {"ticker": "MDLZ",  "filer_type": "10-K", "sector": "Consumer"},
    "Ball Corp":               {"ticker": "BALL",  "filer_type": "10-K", "sector": "Packaging"},
    "Crown Holdings":          {"ticker": "CCK",   "filer_type": "10-K", "sector": "Packaging"},
    "International Paper":     {"ticker": "IP",    "filer_type": "10-K", "sector": "Packaging"},
    "Chevron":                 {"ticker": "CVX",   "filer_type": "10-K", "sector": "Energy"},
    "BP":                      {"ticker": "BP",    "filer_type": "20-F", "sector": "Energy"},
    "Exxon":                   {"ticker": "XOM",   "filer_type": "10-K", "sector": "Energy"},
    "NextEra Energy":          {"ticker": "NEE",   "filer_type": "10-K", "sector": "Utilities"},
    "Duke Energy":             {"ticker": "DUK",   "filer_type": "10-K", "sector": "Utilities"},
    "Sempra Energy":           {"ticker": "SRE",   "filer_type": "10-K", "sector": "Utilities"},
    "Caterpillar":             {"ticker": "CAT",   "filer_type": "10-K", "sector": "Industrials"},
    "Deere":                   {"ticker": "DE",    "filer_type": "10-K", "sector": "Industrials"},
    "Danaher":                 {"ticker": "DHR",   "filer_type": "10-K", "sector": "Industrials"},
    "GE Vernova":              {"ticker": "GEV",   "filer_type": "10-K", "sector": "Industrials"},
    "Honeywell":               {"ticker": "HON",   "filer_type": "10-K", "sector": "Industrials"},
    "Otis":                    {"ticker": "OTIS",  "filer_type": "10-K", "sector": "Industrials"},
    "Air Products":            {"ticker": "APD",   "filer_type": "10-K", "sector": "Industrials"},
    "Corteva":                 {"ticker": "CTVA",  "filer_type": "10-K", "sector": "Industrials"},
    "DuPont":                  {"ticker": "DD",    "filer_type": "10-K", "sector": "Industrials"},
}

# Derived for backward compatibility with existing yfinance fetcher
TICKER_MAP = {co: info["ticker"] for co, info in WATCHLIST.items()}


def fetch_market_data():
    """
    Pull current price, 1D/1M/YTD %, 52W high/low for all tickers from yfinance.
    Returns dict keyed by company name with market data fields.
    Failures per ticker are logged but don't break the run; failed tickers
    fall back to Claude's data.
    """
    if not YFINANCE_AVAILABLE:
        return {}

    print(f"Fetching market data from yfinance for {len(TICKER_MAP)} tickers...")
    result = {}
    success = 0
    failed = []

    # Pull all tickers' 1-year history in one batch
    tickers_str = " ".join(TICKER_MAP.values())
    try:
        hist = yf.download(tickers_str, period="1y", interval="1d",
                           group_by="ticker", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as e:
        print(f"WARNING: yfinance batch download failed: {e}")
        return {}

    today = now.date()
    year_start = datetime(today.year, 1, 1).date()

    for company, ticker in TICKER_MAP.items():
        try:
            if ticker in hist.columns.get_level_values(0):
                df = hist[ticker].dropna()
            else:
                df = hist.dropna()
            if df.empty or 'Close' not in df.columns:
                failed.append(ticker)
                continue

            closes = df['Close']
            current = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else current

            # 1-month: 21 trading days ago
            one_m_idx = max(0, len(closes) - 22)
            month_ago = float(closes.iloc[one_m_idx])

            # YTD: first close at or after Jan 1 of current year
            ytd_closes = closes[closes.index.date >= year_start]
            ytd_start = float(ytd_closes.iloc[0]) if len(ytd_closes) > 0 else current

            # 52-week high/low from the 1y history we already pulled
            wk52_high = float(closes.max())
            wk52_low = float(closes.min())

            def pct(now, then):
                if then == 0:
                    return "n/a"
                p = (now - then) / then * 100
                sign = "+" if p >= 0 else "-"
                return f"{sign}{abs(p):.1f}"

            result[company] = {
                "price": f"{current:.2f}",
                "stock_1d": pct(current, prev),
                "stock_1m": pct(current, month_ago),
                "stock_ytd": pct(current, ytd_start),
                "week52_high": f"{wk52_high:.2f}",
                "week52_low": f"{wk52_low:.2f}",
            }
            # Try to pull market cap from yfinance fast_info (cheap, reliable)
            try:
                fi = yf.Ticker(ticker).fast_info
                mcap_raw = getattr(fi, 'market_cap', None)
                if mcap_raw and mcap_raw > 0:
                    # Convert to $Bn with 1 decimal
                    result[company]["mkt_cap"] = f"{mcap_raw/1e9:.1f}"
            except Exception:
                pass  # mkt_cap stays as whatever Claude returned
            success += 1
        except Exception as e:
            failed.append(f"{ticker} ({str(e)[:60]})")

    print(f"yfinance: {success}/{len(TICKER_MAP)} tickers succeeded.")
    if failed:
        print(f"yfinance failures: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    return result


def apply_market_overrides(rows, market_data):
    """Overwrite stock fields with yfinance data where available."""
    if not market_data:
        return rows
    applied = 0
    mcap_applied = 0
    for r in rows:
        co = r.get('company', '')
        if co in market_data:
            md = market_data[co]
            r['price'] = md['price']
            r['stock_1d'] = md['stock_1d']
            r['stock_1m'] = md['stock_1m']
            r['stock_ytd'] = md['stock_ytd']
            r['week52_high'] = md['week52_high']
            r['week52_low'] = md['week52_low']
            if 'mkt_cap' in md:
                r['mkt_cap'] = md['mkt_cap']
                mcap_applied += 1
            applied += 1
    print(f"Applied yfinance market data to {applied} companies (mkt_cap: {mcap_applied}).")
    return rows


def compute_status_from_data(rows):
    """
    Override Claude's status assignment with a deterministic rule-based status
    derived from the underlying data. Returns count of overrides made.

    Rules (first match wins):
      RED if:
        - concern_score >= 70
        - action in [Review, Escalate, Reduce, Sell]
        - 2+ agency outlooks Negative (or RUR)
        - YTD stock drop > 30%
        - leverage > 5x AND FCF LTM negative
      AMBER if:
        - concern_score >= 30
        - action == Watch
        - 1 negative outlook
        - leverage > 5x
        - FCF LTM negative
        - YTD stock drop > 20%
        - 1M stock drop > 15%
      Else GREEN.
    """
    def to_float(v):
        try:
            return float(str(v).replace(',','').replace('+','').replace('%','').strip())
        except:
            return None

    def is_neg_outlook(o):
        return str(o or '').strip().lower() in ('negative', 'rur')

    overrides = 0
    overrides_detail = []
    for r in rows:
        original = (r.get('status') or 'green').lower()

        # Gather signals
        concern = to_float(r.get('concern_score')) or 0
        action = (r.get('action') or '').strip().lower()
        neg_count = sum(1 for f in ('moodys_outlook','sp_outlook','fitch_outlook')
                        if is_neg_outlook(r.get(f)))
        ytd = to_float(r.get('stock_ytd'))
        m1 = to_float(r.get('stock_1m'))
        leverage = to_float(r.get('nd_ebitda'))
        fcf = to_float(r.get('fcf_ltm'))

        red_triggers = []
        amber_triggers = []

        # RED triggers
        if concern >= 70:
            red_triggers.append(f"concern_score={concern:.0f}")
        if action in ('review', 'escalate', 'reduce', 'sell'):
            red_triggers.append(f"action={action}")
        if neg_count >= 2:
            red_triggers.append(f"{neg_count} negative outlooks")
        if ytd is not None and ytd < -30:
            red_triggers.append(f"YTD {ytd:.0f}%")
        if leverage is not None and leverage > 5 and fcf is not None and fcf < 0:
            red_triggers.append(f"leverage {leverage:.1f}x & FCF neg")

        if red_triggers:
            computed = 'red'
        else:
            # AMBER triggers
            if concern >= 30:
                amber_triggers.append(f"concern={concern:.0f}")
            if action == 'watch':
                amber_triggers.append("action=watch")
            if neg_count == 1:
                amber_triggers.append("1 negative outlook")
            if leverage is not None and leverage > 5:
                amber_triggers.append(f"leverage {leverage:.1f}x")
            if fcf is not None and fcf < 0:
                amber_triggers.append("FCF negative")
            if ytd is not None and ytd < -20:
                amber_triggers.append(f"YTD {ytd:.0f}%")
            if m1 is not None and m1 < -15:
                amber_triggers.append(f"1M {m1:.0f}%")

            computed = 'amber' if amber_triggers else 'green'

        if computed != original:
            overrides += 1
            triggers_str = ", ".join(red_triggers or amber_triggers) or "no triggers fired"
            overrides_detail.append(f"  {r.get('company','')}: {original} -> {computed} ({triggers_str})")

        r['status'] = computed
        r['_status_source'] = 'computed'

    print(f"Status recomputed from data: {overrides} of {len(rows)} rows changed.")
    if overrides_detail:
        for d in overrides_detail[:15]:
            print(d)
        if len(overrides_detail) > 15:
            print(f"  ... and {len(overrides_detail)-15} more")
    return rows



def fetch_commodities_fx():
    """
    Pull WTI, Brent, Gold, EUR/USD, Nasdaq, Dow from yfinance.
    Returns dict with current value and 1-day percent change for each.
    """
    if not YFINANCE_AVAILABLE:
        return {}

    tickers = {
        "wti":     "CL=F",
        "brent":   "BZ=F",
        "gold":    "GC=F",
        "eurusd":  "EURUSD=X",
        "nasdaq":  "^IXIC",
        "dow":     "^DJI",
    }
    print(f"Fetching commodities, FX, and indices from yfinance...")
    try:
        hist = yf.download(" ".join(tickers.values()), period="5d", interval="1d",
                           group_by="ticker", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as e:
        print(f"WARNING: commodities/FX/indices fetch failed: {e}")
        return {}

    result = {}
    for key, ticker in tickers.items():
        try:
            if ticker in hist.columns.get_level_values(0):
                df = hist[ticker].dropna()
            else:
                df = hist.dropna()
            if df.empty or 'Close' not in df.columns:
                continue
            closes = df['Close']
            current = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else current
            if prev == 0:
                pct = "n/a"
            else:
                p = (current - prev) / prev * 100
                sign = "+" if p >= 0 else "-"
                pct = f"{sign}{abs(p):.1f}"
            if key == "eurusd":
                result[key] = {"value": f"{current:.4f}", "change": pct}
            elif key in ("nasdaq", "dow"):
                # Indices: integer with comma
                result[key] = {"value": f"{int(current):,}", "change": pct}
            else:
                result[key] = {"value": f"{current:.2f}", "change": pct}
        except Exception as e:
            print(f"  {ticker} ({key}): {str(e)[:80]}")

    print(f"Commodities/FX/indices: {len(result)}/{len(tickers)} succeeded.")
    return result


# Prompts
PROMPT_A = f"""Today is {datetime_str}. You are generating structured data for a morning credit intelligence dashboard for publicly listed US and global corporates.

Watchlist - BATCH A (38 names):
Telecom: AT&T, Verizon, Comcast
Media: Disney, Warner Bros. Discovery, Netflix
Tech: Amazon, Alphabet, Microsoft, Oracle, Salesforce, IBM
Hardware: HP Inc, HPE, Dell, Nextracker
EMS: Sanmina, Flex Ltd, Jabil
Distribution: Arrow Electronics, TD Synnex, Ingram Micro
IT Services: Kyndryl, Cognizant
Datacenter: Equinix, Digital Realty
Towers: American Tower
Payments: PayPal, Corpay
Travel: Booking Holdings, Uber, Delta, Carnival, Royal Caribbean, Norwegian Cruise Line

For each company gather the data below using these source priorities:

FINANCIAL METRICS (Market Cap, Net Debt/EBITDA, EBITDA Margin, FCF LTM, Cash, Total Debt):
DO NOT search for financial data. Return "n/a" for these fields. They are pulled from SEC EDGAR programmatically after your response and your estimates are not used. Skip these completely to save search budget.

STOCK DATA (1-day, 1-month, YTD percentage changes, 52-week high, 52-week low):
DO NOT search for stock prices. Return "n/a" for these fields. They are pulled from yfinance programmatically after your response and your estimates are not used. Skip these completely to save search budget.

NEXT EARNINGS DATE:
Source from earningswhispers.com, yahoo.com/finance, or the company's IR page.

NEWS (last 24 to 48 hours):
Source from reuters.com, bloomberg.com, wsj.com, ft.com, agency press releases, or sec.gov 8-K filings.

CREDIT RATINGS — CRITICAL ACCURACY RULES:
For each agency (Moody's, S&P, Fitch) for EACH company, you MUST perform multiple targeted searches. Required search sequence per agency per company:
1. First search: "[Company] [Agency] rating action 2026"
2. Second search if needed: "[Company] [Agency] credit rating 2025"
3. Third search if needed: "[Company] credit rating [Agency] downgrade upgrade outlook"

Source priority (use in this order):
1. Agency press releases (moodys.com, spglobal.com, fitchratings.com) — most authoritative
2. Reuters, Bloomberg, Investing.com, Yahoo Finance rating action articles
3. Company 10-K, prospectus, or IR page disclosures

CRITICAL ACCURACY REQUIREMENTS:
- Always return the date of the MOST RECENT rating action found (YYYY-MM-DD format)
- Compare dates across sources — use the source with the most recent date
- If two sources disagree on rating, use the one with the most recent date
- Distinguish issuer/corporate family rating from issue-specific (bond-level) ratings — use the ISSUER rating
- For Moody's: use issuer rating or Corporate Family Rating (CFR), NOT senior unsecured if different
- Do NOT confuse outlook with rating — outlook is Stable/Positive/Negative/RUR, separate from the letter grade
- A rating action includes: upgrade, downgrade, affirmation, outlook change, or watch placement
- For each rating, the date should reflect the most recent rating action (including outlook revisions or affirmations), not the date of original rating assignment

Use web search to source values. For well-known public companies, use your best available knowledge if a specific value is not directly returned by search. Only return "n/a" if the value is genuinely unknowable.

CONCERN SCORE — compute for every row as an integer 0-100:
Start at 0 and add points as follows:
- +25 if status is red
- +10 if status is amber
- +15 if nd_ebitda > 5.0
- +10 if stock_ytd starts with "-" and absolute value > 20
- +10 if stock_1m starts with "-" and absolute value > 10
- +10 if next earnings date is within 14 calendar days of today
- +10 if key_dev mentions downgrade, default, covenant breach, or restructuring
- +10 if fcf_ltm is negative
- +10 if ebitda_margin < 10
- +10 if any rating outlook is Negative or RUR (across Moody's, S&P, Fitch)
- Cap the total at 100.

OUTPUT FORMAT: Your ENTIRE response must be ONLY a single JSON object. Start with {{ as the very first character. End with }} as the very last character. ABSOLUTELY NO preamble, explanation, acknowledgment, markdown formatting, or code fences. NO text like "Here is" or "I will provide". The response must be directly parseable by json.loads().

{{"rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "moodys_rating": "Baa2", "moodys_outlook": "Stable", "moodys_date": "2025-10-15", "sp_rating": "BBB", "sp_outlook": "Stable", "sp_date": "2025-09-22", "fitch_rating": "BBB", "fitch_outlook": "Stable", "fitch_date": "2025-08-10", "concern_score": 35, "key_dev": "No material news.", "action": "Monitor"}}]}}

Rules:
- All 38 names must appear in rows.
- All dollar figures in $Bn. Round to one decimal.
- Net Debt/EBITDA: number only, no "x".
- EBITDA Margin: number only, no % sign.
- Stock percentages: string with + or - prefix, no % symbol.
- week52_high and week52_low: USD price, no $ sign, two decimals.
- concern_score: integer 0-100.
- Ratings: agency-native format (Moody's: Aaa/Aa1/.../C; S&P and Fitch: AAA/AA+/.../D). "n/a" if not rated.
- Outlook: Stable, Positive, Negative, RUR, or n/a.
- Rating date: YYYY-MM-DD format, date of most recent action.
- action: use one of "Monitor" (green), "Watch" (amber), "Review" (red, manageable), "Escalate" (red, urgent). Pick based on severity, not just status.
- key_dev for GREEN: exactly "No material news."
- key_dev for AMBER/RED: 1-2 sentences, under 200 characters.
- Public information only."""

PROMPT_B = f"""Today is {datetime_str}. You are generating structured data for a morning credit intelligence dashboard for publicly listed US and global corporates.

Watchlist - BATCH B (37 names):
Auto: General Motors, Tesla, Ford, Toyota, Nissan, Hyundai
Aerospace: Boeing, GE Aerospace
Retail: Walmart, AutoZone, Genuine Parts
Beverage: Coca-Cola, Anheuser-Busch InBev
Tobacco: Philip Morris, Altria, Imperial Brands, Universal Corporation
Consumer: Nike, Kimberly-Clark, Whirlpool, Mondelez
Packaging: Ball Corp, Crown Holdings, International Paper
Energy: Chevron, BP, Exxon
Utilities: NextEra Energy, Duke Energy, Sempra Energy
Industrials: Caterpillar, Deere, Danaher, GE Vernova, Honeywell, Otis, Air Products, Corteva, DuPont

For each company gather the data below using these source priorities:

FINANCIAL METRICS (Market Cap, Net Debt/EBITDA, EBITDA Margin, FCF LTM, Cash, Total Debt):
DO NOT search for financial data. Return "n/a" for these fields. They are pulled from SEC EDGAR programmatically after your response and your estimates are not used. Skip these completely to save search budget.

STOCK DATA (1-day, 1-month, YTD percentage changes, 52-week high, 52-week low):
DO NOT search for stock prices. Return "n/a" for these fields. They are pulled from yfinance programmatically after your response and your estimates are not used. Skip these completely to save search budget.

NEXT EARNINGS DATE:
Source from earningswhispers.com, yahoo.com/finance, or the company's IR page.

NEWS (last 24 to 48 hours):
Source from reuters.com, bloomberg.com, wsj.com, ft.com, agency press releases, or sec.gov 8-K filings.

CREDIT RATINGS — CRITICAL ACCURACY RULES:
For each agency (Moody's, S&P, Fitch) for EACH company, you MUST perform multiple targeted searches. Required search sequence per agency per company:
1. First search: "[Company] [Agency] rating action 2026"
2. Second search if needed: "[Company] [Agency] credit rating 2025"
3. Third search if needed: "[Company] credit rating [Agency] downgrade upgrade outlook"

Source priority (use in this order):
1. Agency press releases (moodys.com, spglobal.com, fitchratings.com) — most authoritative
2. Reuters, Bloomberg, Investing.com, Yahoo Finance rating action articles
3. Company 10-K, prospectus, or IR page disclosures

CRITICAL ACCURACY REQUIREMENTS:
- Always return the date of the MOST RECENT rating action found (YYYY-MM-DD format)
- Compare dates across sources — use the source with the most recent date
- If two sources disagree on rating, use the one with the most recent date
- Distinguish issuer/corporate family rating from issue-specific (bond-level) ratings — use the ISSUER rating
- For Moody's: use issuer rating or Corporate Family Rating (CFR), NOT senior unsecured if different
- Do NOT confuse outlook with rating — outlook is Stable/Positive/Negative/RUR, separate from the letter grade
- A rating action includes: upgrade, downgrade, affirmation, outlook change, or watch placement
- For each rating, the date should reflect the most recent rating action (including outlook revisions or affirmations), not the date of original rating assignment

MACRO INDICATORS (source once):
Source from wsj.com, bloomberg.com, or fred.stlouisfed.org.
- US HY OAS spread (ICE BofA index, in basis points)
- US IG OAS spread (ICE BofA index, in basis points)
- 10-year US Treasury yield (%)
- 2-year US Treasury yield (%)
- VIX index level
- S&P 500 level and 1-day percentage change

Use web search to source values. For well-known public companies, use your best available knowledge if a specific value is not directly returned by search. Only return "n/a" if the value is genuinely unknowable.

CONCERN SCORE — compute for every row as an integer 0-100:
Start at 0 and add points as follows:
- +25 if status is red
- +10 if status is amber
- +15 if nd_ebitda > 5.0
- +10 if stock_ytd starts with "-" and absolute value > 20
- +10 if stock_1m starts with "-" and absolute value > 10
- +10 if next earnings date is within 14 calendar days of today
- +10 if key_dev mentions downgrade, default, covenant breach, or restructuring
- +10 if fcf_ltm is negative
- +10 if ebitda_margin < 10
- +10 if any rating outlook is Negative or RUR (across Moody's, S&P, Fitch)
- Cap the total at 100.

OUTPUT FORMAT: Your ENTIRE response must be ONLY a single JSON object. Start with {{ as the very first character. End with }} as the very last character. ABSOLUTELY NO preamble, explanation, acknowledgment, markdown formatting, or code fences. NO text like "Here is" or "I will provide". The response must be directly parseable by json.loads().

{{"macro": {{"hy_oas": "350", "ig_oas": "95", "treasury_10y": "4.42", "treasury_2y": "4.85", "vix": "18.2", "sp500": "5234", "sp500_1d": "+0.8"}}, "rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "moodys_rating": "Baa2", "moodys_outlook": "Stable", "moodys_date": "2025-10-15", "sp_rating": "BBB", "sp_outlook": "Stable", "sp_date": "2025-09-22", "fitch_rating": "BBB", "fitch_outlook": "Stable", "fitch_date": "2025-08-10", "concern_score": 35, "key_dev": "No material news.", "action": "Monitor"}}], "top3": [{{"name": "Company A", "note": "Short reason"}}]}}

Rules:
- All 37 names must appear in rows.
- All dollar figures in $Bn. Round to one decimal.
- Net Debt/EBITDA: number only, no "x".
- EBITDA Margin: number only, no % sign.
- Stock percentages: string with + or - prefix, no % symbol.
- week52_high and week52_low: USD price, no $ sign, two decimals.
- concern_score: integer 0-100.
- Ratings: agency-native format. "n/a" if not rated.
- Outlook: Stable, Positive, Negative, RUR, or n/a.
- Rating date: YYYY-MM-DD format.
- action: use one of "Monitor" (green), "Watch" (amber), "Review" (red, manageable), "Escalate" (red, urgent). Pick based on severity, not just status.
- key_dev for GREEN: exactly "No material news."
- key_dev for AMBER/RED: 1-2 sentences, under 200 characters.
- top3: 3 names from across BOTH batches most requiring attention today.
- macro values: hy_oas and ig_oas as integer strings. treasury yields and vix one decimal. sp500 integer string no comma. sp500_1d with + or - prefix.
- Public information only."""


def call_claude(prompt, batch_name):
    print(f"Calling Claude for {batch_name}...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 25}],
        messages=[{"role": "user", "content": prompt}]
    )
    for block in reversed(response.content):
        if hasattr(block, 'text'):
            return block.text.strip()
    return ""


def parse_json(raw, label):
    if not raw:
        return None, f"JSON parse error in {label}: empty response"

    cleaned = raw.strip()

    # Strip markdown code fences if present
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        cleaned = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        cleaned = cleaned.strip()

    # Try direct parse first
    try:
        return json.loads(cleaned), None
    except Exception:
        pass

    # Find the outermost JSON object by locating first '{' and matching last '}'
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end+1]
        try:
            return json.loads(candidate), None
        except Exception as e:
            preview = cleaned[:300].replace('\n',' ')
            return None, f"JSON parse error in {label}: {str(e)[:150]} | First 300 chars: {preview}"

    preview = cleaned[:300].replace('\n',' ')
    return None, f"JSON parse error in {label}: no JSON object found | First 300 chars: {preview}"


def apply_overrides(rows):
    overridden = 0
    rating_fields = ['moodys_rating','moodys_outlook','moodys_date','sp_rating','sp_outlook','sp_date','fitch_rating','fitch_outlook','fitch_date']
    for r in rows:
        co = r.get('company','')
        if co in RATINGS_OVERRIDE:
            ov = RATINGS_OVERRIDE[co]
            for f in rating_fields:
                if f in ov:
                    r[f] = ov[f]
            overridden += 1
    if overridden:
        print(f"Applied manual overrides to {overridden} companies.")
    return rows


def is_stale(date_str):
    if not date_str or date_str == 'n/a':
        return False
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        return (today - d).days > 365
    except:
        return False


def outlook_color(outlook):
    o = (outlook or '').strip().lower()
    if o == 'negative' or o == 'rur':
        return '#ff6b6b'
    if o == 'positive':
        return '#4ec38a'
    if o == 'stable':
        return '#7a8a9a'
    return '#3a4a5a'


def stock_cell(v):
    v = str(v or 'n/a').strip()
    if v.startswith('+'):
        return f'<td class="num-cell stock-up">{v}%</td>'
    elif v.startswith('-'):
        return f'<td class="num-cell stock-down">{v}%</td>'
    return f'<td class="num-cell stock-flat">{v if v else "n/a"}</td>'


def num_cell(v, suffix=''):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    return f'<td class="num-cell">{v}{suffix}</td>'


def score_cell(v):
    try:
        score = int(v)
    except:
        return '<td class="num-cell stock-flat">n/a</td>'
    color = '#ff6b6b' if score >= 70 else ('#f0b429' if score >= 40 else '#4ec38a')
    bar = f'<div class="score-bar"><div style="background:{color};width:{min(score,100)}%"></div></div>'
    return f'<td class="num-cell" style="color:{color};font-weight:700">{score}{bar}</td>'


def ratings_cell(r):
    agencies = [
        ('moodys_rating','moodys_outlook','moodys_date','M'),
        ('sp_rating','sp_outlook','sp_date','S'),
        ('fitch_rating','fitch_outlook','fitch_date','F'),
    ]
    lines = []
    for rf, of, df, label in agencies:
        rating = r.get(rf,'n/a') or 'n/a'
        outlook = r.get(of,'n/a') or 'n/a'
        date = r.get(df,'n/a') or 'n/a'
        stale = is_stale(date)
        color = outlook_color(outlook)
        stale_mark = ' <span class="stale-flag" title="Rating action over 12 months old">&#9888;</span>' if stale else ''
        outlook_short = outlook[:3] if outlook != 'n/a' else ''
        title_attr = f"{label} {rating} {outlook} - last action {date}"
        lines.append(
            f'<div class="rating-line" title="{title_attr}">'
            f'<span class="agency-tag">{label}</span>'
            f'<span class="rating-val">{rating}</span>'
            f'<span class="outlook-val" style="color:{color}">{outlook_short}</span>'
            f'<span class="rating-date">{date if date != "n/a" else ""}</span>'
            f'{stale_mark}'
            f'</div>'
        )
    return f'<td class="ratings-cell">{"".join(lines)}</td>'


def ratings_cell_compact(r):
    """Compact ratings cell for redesigned Overview tab — agency / rating / outlook only."""
    agencies = [
        ('moodys_rating','moodys_outlook','M'),
        ('sp_rating','sp_outlook','S'),
        ('fitch_rating','fitch_outlook','F'),
    ]
    lines = []
    for rf, of, label in agencies:
        rating = r.get(rf,'n/a') or 'n/a'
        outlook = r.get(of,'n/a') or 'n/a'
        outlook_short = outlook[:3].upper() if outlook != 'n/a' else '—'
        color = outlook_color(outlook)
        lines.append(
            f'<div class="rating-row-compact">'
            f'<span class="agency-tag">{label}</span>'
            f'<span class="rating-val">{rating}</span>'
            f'<span class="outlook-tag" style="color:{color}">{outlook_short}</span>'
            f'</div>'
        )
    return f'<td class="ratings-cell">{"".join(lines)}</td>'


def last_action_cell(r):
    """Show the most recent rating action date across all three agencies, with which agency."""
    candidates = [
        ('moodys_date', 'Moody\'s'),
        ('sp_date', 'S&P'),
        ('fitch_date', 'Fitch'),
    ]
    valid = []
    for field, name in candidates:
        d = r.get(field, 'n/a') or 'n/a'
        if d != 'n/a':
            try:
                parsed = datetime.strptime(d, '%Y-%m-%d').date()
                valid.append((parsed, name, d))
            except:
                pass
    if not valid:
        return '<td class="action-date-cell"><div class="action-date-na">No date</div></td>'
    valid.sort(reverse=True)
    most_recent, agency, raw_date = valid[0]
    try:
        display = most_recent.strftime('%b %d, %Y')
    except:
        display = raw_date
    stale = is_stale(raw_date)
    stale_mark = ' <span class="stale-flag" title="Over 12 months old">&#9888;</span>' if stale else ''
    return (
        f'<td class="action-date-cell">'
        f'<div class="action-date-main">{display}{stale_mark}</div>'
        f'<div class="action-date-sub">{agency}</div>'
        f'</td>'
    )


def concern_cell_redesigned(r, status):
    """
    Flag count cell - uses red_flags engine output if available, falls back to concern_score.
    Visual: numeric count, progress bar, tier label.
    """
    flag_count = r.get('_flag_count')
    watch_count = r.get('_watch_count', 0)
    total_flags = 9  # 9 universal flags currently implemented

    if flag_count is not None:
        # Use flag count
        try:
            from red_flags import flag_count_tier
            tier = flag_count_tier(flag_count, watch_count)
        except ImportError:
            tier = 'Comfortable'
        # Color based on count
        if flag_count >= 5:
            color = '#ff6b6b'  # red
        elif flag_count >= 3:
            color = '#ff6b6b'
        elif flag_count >= 1 or watch_count >= 3:
            color = '#f0b429'  # amber
        else:
            color = '#4ec38a'  # green
        # Progress bar shows total signal (flagged * 2 + watch, normalized to ~9)
        signal_strength = min(100, (flag_count * 2 + watch_count) / (total_flags * 2) * 100)
        watch_suffix = f' <span class="watch-suffix">+{watch_count}~</span>' if watch_count > 0 else ''
        return (
            f'<td class="concern-cell">'
            f'<div class="concern-num" style="color:{color}">{flag_count}<span class="concern-denom">/{total_flags}</span>{watch_suffix}</div>'
            f'<div class="concern-bar"><div style="background:{color};width:{signal_strength:.0f}%"></div></div>'
            f'<div class="concern-tier">{tier}</div>'
            f'</td>'
        )

    # Fallback: original concern score
    try:
        score = int(r.get('concern_score', 0))
    except:
        score = 0
    color = '#ff6b6b' if score >= 70 else ('#f0b429' if score >= 40 else '#4ec38a')
    if score >= 80:
        tier = 'Escalate'
    elif score >= 60:
        tier = 'Review'
    elif score >= 40:
        tier = 'Watch'
    else:
        tier = 'Comfortable'
    return (
        f'<td class="concern-cell">'
        f'<div class="concern-num" style="color:{color}">{score}<span class="concern-denom">/100</span></div>'
        f'<div class="concern-bar"><div style="background:{color};width:{min(score,100)}%"></div></div>'
        f'<div class="concern-tier">{tier}</div>'
        f'</td>'
    )


def status_cell_redesigned(status):
    """Larger status badge with background tint."""
    return f'<td><span class="status-badge {status}">{status.upper()}</span></td>'


def company_cell_redesigned(r):
    """Company name + sector underneath."""
    return (
        f'<td class="co-cell-stack">'
        f'<div class="co-name">{r.get("company","")}</div>'
        f'<div class="co-sector">{r.get("sector","").upper()}</div>'
        f'</td>'
    )


def action_cell_redesigned(r):
    """Action badge with the new Monitor/Watch/Review/Escalate labels."""
    action = r.get('action', 'Monitor')
    action_l = action.lower()
    if action_l in ('escalate', 'sell'):
        cls = 'red'
        text = 'Escalate'
    elif action_l in ('review', 'reduce'):
        cls = 'red'
        text = 'Review'
    elif action_l in ('watch',):
        cls = 'amber'
        text = 'Watch'
    else:
        cls = 'green'
        text = 'Monitor'
    return f'<td><span class="action-redesigned {cls}">{text}</span></td>'


def price_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    return f'<td class="num-cell price-cell">${v}</td>'


def money_cell(v, decimals=1):
    """Format a $Bn value with $ prefix and comma thousands separator."""
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        num = float(v)
        # Format with commas, fixed decimals; place minus sign before $
        if num < 0:
            formatted = f"-${abs(num):,.{decimals}f}"
        else:
            formatted = f"${num:,.{decimals}f}"
        return f'<td class="num-cell">{formatted}</td>'
    except (ValueError, TypeError):
        return f'<td class="num-cell">{v}</td>'


def redflag_cell(state):
    """Render a single flag cell: FLAGGED/WATCH/CLEAR/N/A."""
    if state == "FLAGGED":
        return '<td class="rf-cell rf-flagged" title="FLAGGED">&#9888;</td>'
    if state == "WATCH":
        return '<td class="rf-cell rf-watch" title="WATCH">~</td>'
    if state == "CLEAR":
        return '<td class="rf-cell rf-clear" title="CLEAR">&#10003;</td>'
    return '<td class="rf-cell rf-na" title="N/A">&mdash;</td>'


def build_redflag_rows(rows):
    """
    Build heatmap rows. Each row: company name + 9 flag columns + summary count.
    Flag order matches FLAG_DEFINITIONS order from red_flags module.
    Sorted by flag_count descending, then watch_count descending.
    """
    if not rows:
        return []

    # Get flag IDs in display order
    try:
        from red_flags import FLAG_DEFINITIONS
        flag_ids = [f["id"] for f in FLAG_DEFINITIONS]
    except ImportError:
        flag_ids = []

    # Sort rows: most-flagged first
    sorted_rows = sorted(
        [r for r in rows if r.get("_flags")],
        key=lambda r: (-(r.get("_flag_count") or 0), -(r.get("_watch_count") or 0), r.get("company", "").lower())
    )

    rf_rows = []
    for r in sorted_rows:
        flags = r.get("_flags", {})
        flag_count = r.get("_flag_count", 0)
        watch_count = r.get("_watch_count", 0)
        status = (r.get("status") or "green").lower()

        # Build tooltip with all reasons
        flag_cells = ""
        for fid in flag_ids:
            result = flags.get(fid, {})
            state = result.get("state", "N/A")
            reason = result.get("reason", "")
            # Override the title with the actual reason
            cell = redflag_cell(state)
            # Inject reason into title attribute
            cell = cell.replace(f'title="{state}"', f'title="{fid}: {reason}"', 1)
            flag_cells += cell

        # Summary count cell
        if flag_count >= 5:
            count_color = "#ff6b6b"
        elif flag_count >= 1:
            count_color = "#f0b429" if flag_count < 3 else "#ff6b6b"
        elif watch_count >= 3:
            count_color = "#f0b429"
        else:
            count_color = "#4ec38a"

        rf_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + flag_cells
            + f'<td class="rf-summary" style="color:{count_color}"><strong>{flag_count}</strong>'
            + (f'<span class="rf-watch-suffix">+{watch_count}~</span>' if watch_count > 0 else '')
            + '</td>'
            + '</tr>'
        )
    return rf_rows


def build_html(all_rows, macro, top3, datetime_str, commodities=None):
    commodities = commodities or {}
    overview_rows, market_rows, fin_rows = [], [], []
    g_count = a_count = r_count = 0
    for r in all_rows:
        status = r.get('status','green').lower()
        if status == 'green': g_count += 1
        elif status == 'amber': a_count += 1
        elif status == 'red': r_count += 1

        # OVERVIEW row — redesigned
        overview_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            + company_cell_redesigned(r)
            + status_cell_redesigned(status)
            + concern_cell_redesigned(r, status)
            + ratings_cell_compact(r)
            + last_action_cell(r)
            + f'<td class="key-dev-redesigned" title="{r.get("key_dev","").replace(chr(34),"&quot;")}">{r.get("key_dev","")}</td>'
            + action_cell_redesigned(r)
            + '</tr>'
        )

        # Compute Enterprise Value = Mkt Cap + Total Debt - Cash (all in $Bn)
        def _to_f(v):
            try:
                return float(str(v).replace(',','').replace('+','').replace('$','').strip())
            except:
                return None
        mc = _to_f(r.get('mkt_cap'))
        td = _to_f(r.get('total_debt'))
        cs = _to_f(r.get('cash'))
        if mc is not None and td is not None and cs is not None:
            ev_val = mc + td - cs
            ev_str = f"{ev_val:.1f}"
        else:
            ev_str = "n/a"

        # MARKET row — Mkt Cap and EV inserted after Sector, before Status
        market_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            + money_cell(r.get('mkt_cap'))
            + money_cell(ev_str)
            + f'<td class="status {status}">{status.upper()}</td>'
            + price_cell(r.get('price'))
            + stock_cell(r.get('stock_1d'))
            + stock_cell(r.get('stock_1m'))
            + stock_cell(r.get('stock_ytd'))
            + num_cell(r.get('week52_high'))
            + num_cell(r.get('week52_low'))
            + f'<td>{r.get("earnings","TBD")}</td>'
            + '</tr>'
        )

        # FINANCIALS row — Revenue + YoY added, Mkt Cap removed (moved to Market Data tab)
        # Source indicator and warning icon
        fin_source = r.get('_financials_source', '')
        fin_warnings = r.get('_fin_warnings') or []
        filing_form = r.get('_filing_form', '')
        period_end = r.get('_period_end', '')
        if fin_source.startswith('SEC'):
            form_label = filing_form if filing_form else ""
            period_label = period_end if period_end else "unknown"
            source_marker = f'<span class="src-tag sec" title="Source: SEC EDGAR {form_label} as of {period_label}">SEC</span>'
        else:
            source_marker = '<span class="src-tag claude" title="Source: Claude web search (less reliable than SEC EDGAR)">EST</span>'
        warning_marker = ''
        if fin_warnings:
            warning_marker = f' <span class="data-warn" title="{"; ".join(fin_warnings)[:200]}">&#9888;</span>'

        fin_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")} {source_marker}{warning_marker}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + money_cell(r.get('revenue_ltm'))
            + num_cell(r.get('revenue_yoy_pct'), '%')
            + num_cell(r.get('nd_ebitda'))
            + num_cell(r.get('ebitda_margin'),'%')
            + num_cell(r.get('op_margin'),'%')
            + money_cell(r.get('fcf_ltm'))
            + money_cell(r.get('cash'))
            + money_cell(r.get('total_debt'))
            + '</tr>'
        )

    top3_html = ''.join(
        f'<li><strong>{i.get("name","")}</strong>: {i.get("note","")}</li>'
        for i in top3
    )

    # Build red flag heatmap rows
    redflag_rows_list = build_redflag_rows(all_rows)

    # Build red flag column headers from flag definitions
    try:
        from red_flags import FLAG_DEFINITIONS
        rf_headers = "".join(
            f'<th data-type="text" title="{f["name"]}: {f["threshold"]}"><div class="rf-hdr-num">{f["number"]}</div><div class="rf-hdr-label">{f["name"]}</div></th>'
            for f in FLAG_DEFINITIONS
        )
    except ImportError:
        rf_headers = ""

    hy_oas = macro.get('hy_oas','n/a'); ig_oas = macro.get('ig_oas','n/a')
    t10y = macro.get('treasury_10y','n/a'); t2y = macro.get('treasury_2y','n/a')
    vix = macro.get('vix','n/a'); sp500 = macro.get('sp500','n/a')
    sp500_1d = macro.get('sp500_1d',''); sp500_up = str(sp500_1d).startswith('+')

    # Format S&P 500 with comma thousands and $ prefix
    sp500_display = sp500
    try:
        sp500_int = int(str(sp500).replace(',','').replace('$','').strip())
        sp500_display = f"${sp500_int:,}"
    except:
        sp500_display = str(sp500)

    def macro_item(label, value, change=None, up=None):
        change_html = ''
        if change:
            cls = 'macro-up' if up else 'macro-down'
            arrow = '&#9650;' if up else '&#9660;'
            change_html = f'<span class="{cls}">{arrow} {change}</span>'
        return f'<div class="macro-item"><span class="macro-label">{label}</span><span class="macro-value">{value}</span>{change_html}</div>'

    def commodity_item(label, key, prefix='$', suffix=''):
        c = commodities.get(key)
        if not c:
            return macro_item(label, 'n/a')
        chg = c.get('change', '')
        up = chg.startswith('+') if chg else None
        return macro_item(label, f'{prefix}{c["value"]}{suffix}', chg, up)

    macro_html = (
        '<div class="macro-strip">'
        + macro_item('HY OAS', f'{hy_oas} bps')
        + macro_item('IG OAS', f'{ig_oas} bps')
        + macro_item('10Y UST', f'{t10y}%')
        + macro_item('2Y UST', f'{t2y}%')
        + macro_item('VIX', vix)
        + macro_item('S&amp;P 500', sp500_display, sp500_1d, sp500_up)
        + commodity_item('Nasdaq', 'nasdaq', prefix='')
        + commodity_item('Dow', 'dow', prefix='')
        + commodity_item('WTI', 'wti')
        + commodity_item('Brent', 'brent')
        + commodity_item('Gold', 'gold')
        + commodity_item('EUR/USD', 'eurusd', prefix='')
        + f'<div class="macro-item macro-note">Live macro as of {datetime_str}</div>'
        + '</div>'
    )

    css = """
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"IBM Plex Sans",-apple-system,sans-serif;background:#0a0e14;color:#e6edf3;font-size:13px}
header{background:linear-gradient(135deg,#6b0000 0%,#8B0000 60%,#a00000 100%);color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;border-bottom:2px solid #ff000033}
.title{font-size:22px;font-weight:700;letter-spacing:2px;font-family:"IBM Plex Mono",monospace}
.subtitle{font-size:11px;margin-top:3px;opacity:.75;letter-spacing:1px;text-transform:uppercase}
.right-block{text-align:right}
.pills{display:flex;gap:8px;justify-content:flex-end}
.pill{padding:5px 14px;border-radius:3px;font-weight:700;font-size:11px;color:#fff;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}
.pill.red{background:#cc0000}.pill.amber{background:#e6a700}.pill.green{background:#2e7d32}
.last-refresh{font-size:10px;margin-top:6px;opacity:.7;font-family:"IBM Plex Mono",monospace}
.macro-strip{background:#0d1520;border-bottom:1px solid #1e3a5f;padding:10px 28px;display:flex;gap:0;flex-wrap:wrap;align-items:center}
.macro-item{padding:4px 20px;border-right:1px solid #1e3a5f;display:flex;flex-direction:column;align-items:center;gap:2px}
.macro-item:last-child{border-right:none;margin-left:auto}
.macro-label{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#4a6080;font-family:"IBM Plex Mono",monospace}
.macro-value{font-size:13px;font-weight:600;color:#a0c4e8;font-family:"IBM Plex Mono",monospace}
.macro-up{font-size:10px;color:#4ec38a;font-weight:600}
.macro-down{font-size:10px;color:#ff6b6b;font-weight:600}
.macro-note{font-size:10px;color:#3a4a5a;align-items:flex-end;border-right:none}
.tabs{background:#0d1117;padding:0 28px;display:flex;gap:0;border-bottom:1px solid #1e2a3a}
.tab{padding:11px 18px;font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#4a6080;cursor:pointer;border:none;border-bottom:2px solid transparent;background:none;transition:all .15s}
.tab:hover{color:#a0b4c8}
.tab.active{color:#fff;border-bottom-color:#8B0000;background:#0a0e14}
.controls{padding:12px 28px;background:#0d1117;border-bottom:1px solid #1e2a3a;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.controls button{padding:6px 14px;border:1px solid #1e2a3a;background:#0d1520;color:#a0b4c8;cursor:pointer;font-weight:600;border-radius:3px;font-size:11px;letter-spacing:.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;transition:all .15s}
.controls button:hover{background:#1e2a3a;color:#e6edf3}
.controls button.active{background:#8B0000;color:#fff;border-color:#8B0000}
.controls input,.controls select{padding:6px 12px;border:1px solid #1e2a3a;border-radius:3px;font-size:12px;background:#0d1520;color:#e6edf3}
.controls input{width:200px}
.pane{display:none}.pane.active{display:block}
table{width:100%;border-collapse:collapse;background:#0a0e14;table-layout:fixed}
thead th{background:#0d1117;color:#4a6080;padding:10px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;cursor:pointer;user-select:none;position:sticky;top:0;font-family:"IBM Plex Mono",monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
thead th:hover{background:#0d1520;color:#a0b4c8}
tbody td{padding:9px 10px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle;overflow:hidden}
tbody tr:hover{background:#0d1520}
.co-cell{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.status{font-weight:700;font-size:11px;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}
.status.red{color:#ff6b6b}.status.amber{color:#f0b429}.status.green{color:#4ec38a}
.sector-tag{background:#0d1520;border:1px solid #1e2a3a;color:#7090a8;font-size:10px;padding:2px 7px;border-radius:2px;letter-spacing:.5px;white-space:nowrap}
.stock-up{color:#4ec38a;font-weight:700;font-family:"IBM Plex Mono",monospace}
.stock-down{color:#ff6b6b;font-weight:700;font-family:"IBM Plex Mono",monospace}
.stock-flat{color:#3a4a5a;font-family:"IBM Plex Mono",monospace}
.num-cell{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace;font-size:12px}
.score-bar{background:#21262d;border-radius:3px;height:4px;margin-top:3px;width:60px;display:inline-block;overflow:hidden}
.score-bar div{height:100%;border-radius:3px}
.key-dev{color:#a0b4c8;font-size:11px;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.action-cell{white-space:nowrap}
.action-badge{font-size:10px;padding:3px 10px;border-radius:2px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace}
.action-badge.red{background:#3a0000;color:#ff6b6b;border:1px solid #8B0000}
.action-badge.amber{background:#2a1a00;color:#f0b429;border:1px solid #8b6200}
.action-badge.green{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
.ratings-cell{padding:6px 8px;font-family:"IBM Plex Mono",monospace;font-size:10px;line-height:1.35}
.rating-line{display:flex;align-items:center;gap:6px;white-space:nowrap}
.agency-tag{display:inline-block;width:11px;color:#4a6080;font-weight:600}
.rating-val{color:#e6edf3;font-weight:600;min-width:36px}
.outlook-val{font-weight:600;min-width:24px;font-size:9px}
.rating-date{color:#3a4a5a;font-size:9px;margin-left:auto}
.stale-flag{color:#f0b429;font-size:11px;margin-left:2px;cursor:help}

/* Redesigned Overview tab styles */
.overview-table tbody td{padding:12px 14px;vertical-align:middle}
/* Center everything except Company (col 1) and Key Development (col 6) on Overview */
.overview-table tbody td:not(:nth-child(1)):not(:nth-child(6)),
.overview-table thead th:not(:nth-child(1)):not(:nth-child(6)){text-align:center}
/* Market Data tab — center everything except Company (col 1) */
#pane-market tbody td:not(:nth-child(1)),
#pane-market thead th:not(:nth-child(1)){text-align:center}
/* Financials tab — center everything except Company (col 1) */
#pane-financials tbody td:not(:nth-child(1)),
#pane-financials thead th:not(:nth-child(1)){text-align:center}
/* Inside-cell helpers need to inherit center on these tables */
#pane-market .num-cell,
#pane-financials .num-cell{text-align:center}
.co-cell-stack{font-family:"IBM Plex Sans",sans-serif}
.co-name{font-weight:600;font-size:13px;color:#e6edf3;line-height:1.2}
.co-sector{font-family:"IBM Plex Mono",monospace;font-size:9px;color:#7090a8;margin-top:3px;letter-spacing:.5px}
.status-badge{font-weight:700;font-size:13px;letter-spacing:1px;font-family:"IBM Plex Mono",monospace;padding:5px 12px;border-radius:3px;display:inline-block;text-align:center}
.status-badge.red{color:#ff6b6b;background:rgba(255,107,107,.12)}
.status-badge.amber{color:#f0b429;background:rgba(240,180,41,.12)}
.status-badge.green{color:#4ec38a;background:rgba(78,195,138,.12)}
.concern-cell{padding:10px 12px;font-family:"IBM Plex Mono",monospace}
.concern-num{font-weight:700;font-size:18px;line-height:1}
.concern-denom{font-size:11px;color:#3a4a5a;font-weight:400;margin-left:2px}
.concern-bar{background:#21262d;border-radius:2px;height:4px;margin:6px auto 0;width:80px;overflow:hidden}
.concern-bar div{height:100%;border-radius:2px}
.concern-tier{font-size:9px;color:#7090a8;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.watch-suffix{font-size:10px;color:#f0b429;font-weight:600;margin-left:4px;font-family:"IBM Plex Mono",monospace}

/* Red Flags heatmap */
.rf-legend{padding:14px 28px;background:#0d1117;border-bottom:1px solid #1e2a3a;display:flex;flex-wrap:wrap;gap:24px;align-items:center;font-size:11px;color:#a0b4c8}
.rf-legend-item{display:flex;align-items:center;gap:6px;font-family:"IBM Plex Mono",monospace}
.rf-legend-item .rf-cell{position:static;display:inline-flex;width:22px;height:22px;padding:0;border-radius:3px;font-size:12px}
.rf-legend-note{margin-left:auto;font-size:10px;color:#7090a8;font-style:italic;font-family:"IBM Plex Sans",sans-serif}
.rf-table{width:100%;border-collapse:collapse;background:#0a0e14;table-layout:fixed}
.rf-table th{background:#0d1117;color:#4a6080;padding:8px 6px;font-size:9px;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;font-family:"IBM Plex Mono",monospace;font-weight:600;vertical-align:bottom;text-align:center}
.rf-table thead th:first-child{text-align:left;width:14%;padding-left:14px}
.rf-table thead th:nth-child(2){width:9%}
.rf-table thead th:nth-child(3){width:7%}
.rf-table thead th:last-child{width:7%}
.rf-hdr-num{font-size:13px;color:#a0b4c8;font-weight:700;margin-bottom:4px}
.rf-hdr-label{font-size:8px;color:#4a6080;line-height:1.2;white-space:normal}
.rf-table td{padding:8px 6px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle;text-align:center}
.rf-table td:first-child{text-align:left;padding-left:14px;font-weight:600;color:#e6edf3;font-size:13px}
.rf-cell{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:3px;font-family:"IBM Plex Mono",monospace;font-weight:700;cursor:help;font-size:13px}
.rf-flagged{background:rgba(255,107,107,.15);color:#ff6b6b;border:1px solid rgba(255,107,107,.4)}
.rf-watch{background:rgba(240,180,41,.12);color:#f0b429;border:1px solid rgba(240,180,41,.35)}
.rf-clear{background:rgba(78,195,138,.08);color:#4ec38a;border:1px solid rgba(78,195,138,.25)}
.rf-na{background:#0d1520;color:#3a4a5a;border:1px solid #1e2a3a}
.rf-summary{font-family:"IBM Plex Mono",monospace;font-size:14px;font-weight:700}
.rf-summary strong{font-size:16px}
.rf-watch-suffix{font-size:10px;color:#f0b429;margin-left:3px;font-weight:600}
.rating-row-compact{display:flex;align-items:center;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:11px;line-height:1.6}
.outlook-tag{font-weight:700;font-size:9px;width:32px;display:inline-block}
.action-date-cell{font-family:"IBM Plex Mono",monospace;padding:10px 12px}
.action-date-main{font-size:11px;color:#a0b4c8;font-weight:500;line-height:1.3}
.action-date-sub{font-size:9px;color:#4a6080;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}
.action-date-na{font-size:10px;color:#3a4a5a;font-style:italic}
.key-dev-redesigned{color:#a0b4c8;font-size:12px;line-height:1.5;padding:10px 14px}
.action-redesigned{padding:6px 14px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;display:inline-block;white-space:nowrap}
.action-redesigned.red{background:#3a0000;color:#ff6b6b;border:1px solid #8B0000}
.action-redesigned.amber{background:#2a1a00;color:#f0b429;border:1px solid #8b6200}
.action-redesigned.green{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
.price-cell{font-weight:700;color:#a0c4e8}
.src-tag{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.5px;padding:1px 4px;border-radius:2px;margin-left:6px;vertical-align:middle;cursor:help}
.src-tag.sec{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
.src-tag.claude{background:#0d1520;color:#7090a8;border:1px solid #1e2a3a}
.data-warn{color:#f0b429;font-size:12px;cursor:help;margin-left:2px}

.placeholder-pane{padding:80px 28px;text-align:center;color:#4a6080;font-family:"IBM Plex Mono",monospace;font-size:13px;letter-spacing:1px}
.placeholder-pane .ph-title{font-size:16px;color:#a0b4c8;margin-bottom:10px;letter-spacing:2px}
.methodology-content{padding:28px 32px;color:#a0b4c8;font-size:13px;line-height:1.6;max-width:920px}
.methodology-content h2{font-family:"IBM Plex Mono",monospace;font-size:13px;color:#8B0000;text-transform:uppercase;letter-spacing:1.5px;margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #1e2a3a;font-weight:700}
.methodology-content h2:first-child{margin-top:0}
.methodology-content p{margin:8px 0 12px;color:#a0b4c8}
.methodology-content ul{margin:8px 0 16px;padding-left:22px}
.methodology-content li{padding:4px 0;color:#a0b4c8}
.methodology-content code{font-family:"IBM Plex Mono",monospace;background:#0d1520;padding:1px 6px;border-radius:2px;font-size:11px;color:#a0c4e8}
.methodology-content .meth-note{font-size:11px;color:#7090a8;font-weight:400;text-transform:none;letter-spacing:0}
.methodology-table{border-collapse:collapse;margin:8px 0 18px;width:auto;min-width:50%}
.methodology-table th{background:#0d1117;color:#4a6080;padding:8px 14px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;font-weight:600;border-bottom:1px solid #1e2a3a}
.methodology-table td{padding:8px 14px;border-bottom:1px solid #0d1520;font-size:12px;color:#a0b4c8;vertical-align:middle}
.methodology-table td:first-child{font-family:"IBM Plex Mono",monospace}
footer{background:linear-gradient(135deg,#6b0000,#8B0000);color:#fff;padding:20px 28px;border-top:2px solid #ff000033}
footer h3{margin-bottom:12px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;opacity:.8}
footer ol{padding-left:20px}
footer li{padding:5px 0;font-size:13px;line-height:1.5}
footer li strong{color:#ffaaaa}
"""

    js = """
(function(){
  var panes={overview:document.getElementById('pane-overview'),market:document.getElementById('pane-market'),financials:document.getElementById('pane-financials'),redflags:document.getElementById('pane-redflags'),methodology:document.getElementById('pane-methodology')};
  var tabs=document.querySelectorAll('.tab');
  tabs.forEach(function(t){t.addEventListener('click',function(){
    tabs.forEach(function(x){x.classList.remove('active');});
    Object.values(panes).forEach(function(p){if(p)p.classList.remove('active');});
    t.classList.add('active');
    var pane=panes[t.dataset.tab];if(pane)pane.classList.add('active');
  });});

  var btns=document.querySelectorAll('.controls button[data-filter]');
  var search=document.getElementById('searchBox');
  var sel=document.getElementById('sectorFilter');
  var af='all';

  function applyAll(){
    var q=(search.value||'').toLowerCase();
    var sv=sel.value;
    var g=0,a=0,r=0;
    document.querySelectorAll('.pane tbody tr').forEach(function(row){
      var st=(row.dataset.status||'').toLowerCase();
      var co=(row.dataset.company||'');
      var sc=(row.dataset.sector||'');
      var pf=af==='all'||st===af;
      var ps=!q||co.indexOf(q)>-1;
      var psc=sv==='all'||sc===sv;
      var sh=pf&&ps&&psc;
      row.style.display=sh?'':'none';
    });
    document.querySelectorAll('#pane-overview tbody tr').forEach(function(row){
      if(row.style.display!=='none'){
        var st=(row.dataset.status||'').toLowerCase();
        if(st==='green')g++;else if(st==='amber')a++;else if(st==='red')r++;
      }
    });
    document.getElementById('greenCount').textContent='GREEN '+g;
    document.getElementById('amberCount').textContent='AMBER '+a;
    document.getElementById('redCount').textContent='RED '+r;
  }

  btns.forEach(function(b){b.addEventListener('click',function(){
    btns.forEach(function(x){x.classList.remove('active');});
    b.classList.add('active');af=b.dataset.filter;applyAll();
  });});
  search.addEventListener('input',applyAll);
  sel.addEventListener('change',applyAll);

  var secs=new Set();
  document.querySelectorAll('#pane-overview tbody tr').forEach(function(r){
    var x=(r.dataset.sector||'').trim();if(x)secs.add(x);
  });
  Array.from(secs).sort().forEach(function(x){
    var o=document.createElement('option');o.value=x;o.textContent=x;sel.appendChild(o);
  });

  document.querySelectorAll('.pane table').forEach(function(tbl){
    var ths=tbl.querySelectorAll('thead th');
    var sc=-1,sd=1;
    ths.forEach(function(th,idx){th.addEventListener('click',function(){
      var t=th.dataset.type||'text';
      if(sc===idx)sd=-sd;else{sc=idx;sd=1;}
      var tb=tbl.querySelector('tbody');
      var rows=Array.from(tb.querySelectorAll('tr'));
      rows.sort(function(a,b){
        var av=a.cells[idx].textContent.trim();var bv=b.cells[idx].textContent.trim();
        if(t==='num'){av=parseFloat(av.replace(/[^0-9.\\-]/g,''))||0;bv=parseFloat(bv.replace(/[^0-9.\\-]/g,''))||0;return (av-bv)*sd;}
        if(t==='date'){av=new Date(av).getTime()||0;bv=new Date(bv).getTime()||0;return (av-bv)*sd;}
        return av.localeCompare(bv)*sd;
      });
      tb.innerHTML='';rows.forEach(function(r){tb.appendChild(r);});
    });});
  });

  applyAll();
})();
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Credit Digest</title>
<style>{css}</style>
</head>
<body>
<header>
  <div>
    <div class="title">MORNING CREDIT DIGEST</div>
    <div class="subtitle">2LOD Credit Surveillance &nbsp;&bull;&nbsp; US Corporate Watchlist &nbsp;&bull;&nbsp; 75 Names</div>
  </div>
  <div class="right-block">
    <div class="pills">
      <span class="pill green" id="greenCount">GREEN {g_count}</span>
      <span class="pill amber" id="amberCount">AMBER {a_count}</span>
      <span class="pill red" id="redCount">RED {r_count}</span>
    </div>
    <div class="last-refresh">Updated: {datetime_str}</div>
  </div>
</header>
{macro_html}
<div class="tabs">
  <button class="tab active" data-tab="overview">Overview</button>
  <button class="tab" data-tab="market">Market Data</button>
  <button class="tab" data-tab="financials">Financials</button>
  <button class="tab" data-tab="redflags">Red Flags</button>
  <button class="tab" data-tab="methodology">Methodology</button>
</div>
<div class="controls">
  <button class="active" data-filter="all">All</button>
  <button data-filter="red">Red</button>
  <button data-filter="amber">Amber</button>
  <button data-filter="green">Green</button>
  <input type="text" id="searchBox" placeholder="Search company...">
  <select id="sectorFilter"><option value="all">All Sectors</option></select>
</div>

<div class="pane active" id="pane-overview">
<table class="overview-table">
<colgroup>
<col style="width:14%"><col style="width:7%"><col style="width:9%"><col style="width:14%"><col style="width:11%"><col style="width:36%"><col style="width:9%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Status</th>
  <th data-type="num">Flags</th>
  <th data-type="text">Ratings (M/S/F)</th>
  <th data-type="date">Last Action</th>
  <th data-type="text">Key Development</th>
  <th data-type="text">Action</th>
</tr></thead>
<tbody>{"".join(overview_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-market">
<table>
<colgroup>
<col style="width:13%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:6%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:8%"><col style="width:8%"><col style="width:12%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="num">Mkt Cap $Bn</th>
  <th data-type="num">EV $Bn</th>
  <th data-type="text">Status</th>
  <th data-type="num">Price $</th>
  <th data-type="num">1D %</th>
  <th data-type="num">1M %</th>
  <th data-type="num">YTD %</th>
  <th data-type="num">52W High</th>
  <th data-type="num">52W Low</th>
  <th data-type="date">Next Earnings</th>
</tr></thead>
<tbody>{"".join(market_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-financials">
<table>
<colgroup>
<col style="width:15%"><col style="width:10%"><col style="width:7%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:8%"><col style="width:8%"><col style="width:9%"><col style="width:8%"><col style="width:10%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="text">Status</th>
  <th data-type="num">Revenue LTM $Bn</th>
  <th data-type="num">Rev YoY %</th>
  <th data-type="num">ND/EBITDA</th>
  <th data-type="num">EBITDA Mgn %</th>
  <th data-type="num">Op Mgn %</th>
  <th data-type="num">FCF LTM $Bn</th>
  <th data-type="num">Cash $Bn</th>
  <th data-type="num">Tot Debt $Bn</th>
</tr></thead>
<tbody>{"".join(fin_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-redflags">
<div class="rf-legend">
  <div class="rf-legend-item"><span class="rf-cell rf-flagged">&#9888;</span> Flagged (threshold breached)</div>
  <div class="rf-legend-item"><span class="rf-cell rf-watch">~</span> Watch (approaching threshold)</div>
  <div class="rf-legend-item"><span class="rf-cell rf-clear">&#10003;</span> Clear</div>
  <div class="rf-legend-item"><span class="rf-cell rf-na">&mdash;</span> N/A (insufficient data)</div>
  <div class="rf-legend-note">Hover any cell for the trigger reason. See Methodology tab for full flag definitions.</div>
</div>
<table class="rf-table">
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="text">Status</th>
  {rf_headers}
  <th data-type="num">Total</th>
</tr></thead>
<tbody>{"".join(redflag_rows_list)}</tbody>
</table>
</div>

<div class="pane" id="pane-methodology">
<div class="methodology-content">

  <h2>Status Definitions</h2>
  <p>Status is <strong>computed deterministically</strong> from the underlying data after each run &mdash; it is not Claude&apos;s judgment.</p>
  <table class="methodology-table">
    <tr><td><span class="status-badge red">RED</span></td><td>Triggered if any of: concern score &ge; 70, action is Review/Escalate, 2+ negative agency outlooks, YTD stock drop &gt; 30%, or leverage &gt; 5x AND FCF negative.</td></tr>
    <tr><td><span class="status-badge amber">AMBER</span></td><td>Triggered if any of: concern score &ge; 30, action is Watch, 1 negative outlook, leverage &gt; 5x, FCF negative, YTD drop &gt; 20%, or 1M drop &gt; 15%.</td></tr>
    <tr><td><span class="status-badge green">GREEN</span></td><td>None of the above triggers fired. Routine monitoring.</td></tr>
  </table>

  <h2>Action Tiers</h2>
  <table class="methodology-table">
    <tr><td><span class="action-redesigned green">Monitor</span></td><td>Standard surveillance, no action required.</td></tr>
    <tr><td><span class="action-redesigned amber">Watch</span></td><td>Increased scrutiny, near-term review possible.</td></tr>
    <tr><td><span class="action-redesigned red">Review</span></td><td>Formal credit review warranted.</td></tr>
    <tr><td><span class="action-redesigned red">Escalate</span></td><td>Committee discussion / 2LOD challenge required.</td></tr>
  </table>

  <h2>Flag Count (Overview Tab)</h2>
  <p>The <strong>Flags</strong> column on the Overview tab shows the count of FLAGGED triggers from the 9 universal red flags evaluated per company. The progress bar weights flagged (2x) plus watch (1x) signals against a maximum of 18.</p>
  <p>Format: <code>X/9 (+Y~)</code> where X = flagged count and Y = watch count.</p>
  <p>See the Red Flags tab for the full per-company heatmap and the section below for flag definitions and thresholds.</p>
  <p><em>Note: an older "Concern Score" (sum-of-triggers 0&ndash;100) has been retired in favor of the flag-based system since the flags map directly to credit analytical thresholds rather than relying on weighted heuristics.</em></p>

  <h2>Ratings &amp; Outlook</h2>
  <ul>
    <li>M / S / F = Moody&apos;s / S&amp;P / Fitch</li>
    <li>Outlook colors: <span style="color:#4ec38a;font-weight:700">green</span> = Positive, <span style="color:#7a8a9a;font-weight:700">gray</span> = Stable, <span style="color:#ff6b6b;font-weight:700">red</span> = Negative or RUR</li>
    <li><span style="color:#f0b429">&#9888;</span> icon = rating action over 12 months old (stale)</li>
    <li>Source: agency press releases &amp; news synthesis via Claude web search, plus manual override file (<code>ratings_override.json</code>) for high-touch names</li>
  </ul>

  <h2>Market Data</h2>
  <ul>
    <li>Source: Yahoo Finance via <code>yfinance</code> library</li>
    <li>Current price: latest available close</li>
    <li>Market Cap: pulled from yfinance (price &times; shares outstanding); refreshes daily</li>
    <li>Enterprise Value (EV) = Market Cap + Total Debt &minus; Cash. Calculated row by row using yfinance market cap plus Claude-sourced debt/cash (Phase 2 will move debt/cash to SEC EDGAR).</li>
    <li>1D / 1M / YTD: calculated from closing prices</li>
    <li>52W high / low: trailing 52-week trading range</li>
    <li>Refresh: daily</li>
  </ul>

  <h2>Macro Indicators</h2>
  <ul>
    <li>HY OAS / IG OAS: ICE BofA US Corporate index option-adjusted spreads</li>
    <li>10Y / 2Y UST: US Treasury closing yields</li>
    <li>VIX: CBOE Volatility Index</li>
    <li>S&amp;P 500: index level &amp; 1-day change</li>
    <li>Nasdaq: Nasdaq Composite index (^IXIC) &amp; 1-day change</li>
    <li>Dow: Dow Jones Industrial Average (^DJI) &amp; 1-day change</li>
    <li>WTI / Brent: front-month crude oil futures (CL=F, BZ=F)</li>
    <li>Gold: front-month gold futures (GC=F)</li>
    <li>EUR/USD: spot FX</li>
    <li>Sources: spreads, yields, VIX, S&amp;P 500 level via Claude web search; equity indices (Nasdaq, Dow), commodities &amp; FX via yfinance</li>
  </ul>

  <h2>Financials</h2>
  <ul>
    <li><strong>Source:</strong> SEC EDGAR XBRL data, pulled directly from <code>data.sec.gov</code>. No paid feeds, no Claude estimates for the metrics below (for US 10-K filers and 20-F annual filers).</li>
    <li><strong>Refresh:</strong> Weekly &mdash; cache is refreshed if older than 6 days. Manual refresh via workflow input.</li>
    <li><strong>LTM construction:</strong> Sum of the 4 most recent non-overlapping quarterly facts. For 20-F annual filers, the latest annual figure is used (labeled).</li>
    <li><strong>Net Debt</strong> = Long-Term Debt + Short-Term Debt &minus; Cash &amp; Equivalents</li>
    <li><strong>EBITDA</strong> = Operating Income + Depreciation &amp; Amortization (GAAP construction, no company-reported adjustments)</li>
    <li><strong>FCF</strong> = Operating Cash Flow &minus; CapEx</li>
    <li><strong>ND/EBITDA</strong> = Net Debt / LTM EBITDA</li>
    <li><strong>Revenue YoY %</strong> = LTM Revenue vs. trailing 4-quarter sum from a year earlier</li>
    <li>All dollar figures in $Bn</li>
    <li>Each row carries a source tag: <span class="src-tag sec">SEC</span> = direct SEC EDGAR data, <span class="src-tag claude">EST</span> = Claude estimate (used for non-SEC filers)</li>
    <li>A <span style="color:#f0b429">&#9888;</span> icon on a row indicates data quality warnings &mdash; hover to see the specific issue (e.g., "Cash not found", "Revenue YoY = -55% verify")</li>
    <li>Market Cap moved to the Market Data tab (it&apos;s a price-derived market metric, not a filing-derived financial)</li>
  </ul>

  <h2>SEC EDGAR Data Quality</h2>
  <ul>
    <li><strong>Authoritative:</strong> XBRL-tagged GAAP data from actual filings. Same numbers as in the 10-K/10-Q.</li>
    <li><strong>Tag fallback chains:</strong> Companies tag concepts slightly differently. We try the primary tag (e.g., <code>Revenues</code>), then fall back to alternatives (e.g., <code>RevenueFromContractWithCustomerExcludingAssessedTax</code>) if missing.</li>
    <li><strong>Validation:</strong> Implausible values (cash &gt; assets, ND/EBITDA outside &plusmn;50x, etc.) trigger warnings shown as &#9888; on the row.</li>
    <li><strong>20-F filers</strong> (Toyota, BP, AB InBev): annual data only; quarterly fields show the most recent annual figure.</li>
    <li><strong>Non-SEC filers</strong> (Nissan, Hyundai, Imperial Brands): no SEC data available; financials fall back to Claude web-search estimates.</li>
    <li><strong>Cache file:</strong> <code>financials_cache.json</code> in the repo &mdash; auditable record of what data was used.</li>
  </ul>

  <h2>Red Flags Framework</h2>
  <p>9 of 12 universal flags are computed each run from SEC EDGAR, yfinance, and ratings data. Each flag returns one of: <span class="rf-cell rf-flagged" style="position:static;display:inline-flex;width:18px;height:18px;font-size:10px">&#9888;</span> FLAGGED, <span class="rf-cell rf-watch" style="position:static;display:inline-flex;width:18px;height:18px;font-size:10px">~</span> WATCH, <span class="rf-cell rf-clear" style="position:static;display:inline-flex;width:18px;height:18px;font-size:10px">&#10003;</span> CLEAR, or <span class="rf-cell rf-na" style="position:static;display:inline-flex;width:18px;height:18px;font-size:10px">&mdash;</span> N/A.</p>
  <table class="methodology-table">
    <tr><th>Flag</th><th>Threshold</th><th>Watch</th><th>Data Source</th></tr>
    <tr><td>1. Leverage Too High</td><td>ND/EBITDA &gt; 5.0x</td><td>&gt; 4.0x</td><td>SEC EDGAR</td></tr>
    <tr><td>2. Leverage Climbing</td><td>ND/EBITDA +1.0x YoY</td><td>+0.5x</td><td>SEC EDGAR quarterly history</td></tr>
    <tr><td>3. Coverage Thin</td><td>EBITDA/Interest &lt; 3.0x</td><td>&lt; 4.5x</td><td>SEC EDGAR</td></tr>
    <tr><td>4. Burning Cash</td><td>FCF negative 2 quarters</td><td>1 quarter</td><td>SEC EDGAR quarterly history</td></tr>
    <tr><td>7. Revenue Shrinking</td><td>Rev YoY &lt; -5%</td><td>&lt; -2%</td><td>SEC EDGAR</td></tr>
    <tr><td>8. Margin Compression</td><td>EBITDA margin -300bps YoY</td><td>-150bps</td><td>SEC EDGAR quarterly history</td></tr>
    <tr><td>9. Stock Collapse</td><td>YTD &lt; -25%</td><td>&lt; -15%</td><td>yfinance</td></tr>
    <tr><td>10. Rating Pressure</td><td>2+ Negative outlooks</td><td>1 negative</td><td>Ratings + override file</td></tr>
    <tr><td>11. Bad News in Filings</td><td>Trigger phrases in key dev</td><td>Watch phrases</td><td>Claude key dev synthesis</td></tr>
  </table>
  <p><strong>Pending flags</strong> (require data not in XBRL companyfacts):</p>
  <ul>
    <li>Flag 5. Wall of Maturities &mdash; needs debt maturity schedule (10-K narrative parsing)</li>
    <li>Flag 6. Refi at Higher Rates &mdash; needs coupon data on outstanding debt</li>
    <li>Flag 12. Liquidity Squeeze &mdash; needs revolver availability disclosure</li>
  </ul>
  <p><strong>Tier mapping (Overview tab Flags column):</strong></p>
  <table class="methodology-table">
    <tr><td>0 flagged, 0-2 watch</td><td>Comfortable</td></tr>
    <tr><td>0 flagged, 3+ watch</td><td>Watch</td></tr>
    <tr><td>1-2 flagged</td><td>Watch</td></tr>
    <tr><td>3-4 flagged</td><td>Review</td></tr>
    <tr><td>5+ flagged</td><td>Escalate</td></tr>
  </table>
  <p><strong>Bad news keyword scanner (Flag 11)</strong> looks for these phrases in the Key Development field:</p>
  <ul>
    <li><strong>FLAGGED triggers:</strong> covenant breach, covenant violation, default, missed payment, restructuring, chapter 11, chapter 7, bankruptcy, going concern</li>
    <li><strong>WATCH triggers:</strong> downgrade, lawsuit, litigation, investigation, fraud, sec inquiry, guidance cut, guidance withdrawn, material weakness, restatement, layoffs, going private, strategic review</li>
  </ul>

  <h2>Refresh Cadence</h2>
  <ul>
    <li>Dashboard runs daily at 8:00 AM ET on weekdays</li>
    <li><strong>Daily refresh:</strong> Market data, commodities/FX, equity indices (yfinance); ratings, news, top 3 (Claude); status compute</li>
    <li><strong>Weekly refresh:</strong> SEC EDGAR financials (cache TTL = 6 days; refreshes on first run after expiry)</li>
    <li>Manual override file (<code>ratings_override.json</code>) applies after auto-pull</li>
  </ul>

  <h2>Audit Trail</h2>
  <ul>
    <li><strong><code>runs.json</code></strong> in the repo: rolling log of the last 60 runs, capturing data sources called, success/failure counts, validation warnings, output stats, and timing. Auto-trimmed.</li>
    <li><strong><code>financials_cache.json</code></strong> in the repo: snapshot of the SEC data used for the current run. Inspectable.</li>
    <li><strong>Row-level provenance:</strong> each financial cell carries a source tag (<span class="src-tag sec">SEC</span> or <span class="src-tag claude">EST</span>) and a warning marker (<span style="color:#f0b429">&#9888;</span>) where validation rules fired.</li>
    <li><strong>Validation rules:</strong> impossible values (cash &gt; assets, ND/EBITDA &gt; 50x, EBITDA margin &gt; 80%, etc.) trigger row warnings. Hover to see the specific rule that fired.</li>
  </ul>

  <h2>Data Limitations</h2>
  <ul>
    <li>20-F filers (Toyota, BP, Anheuser-Busch InBev) report annually rather than quarterly &mdash; financial data may be 6&ndash;12 months old</li>
    <li>Non-SEC filers (Nissan, Hyundai, Imperial Brands) have limited financial data; market data still available via yfinance</li>
    <li>News &amp; key dev: best-effort synthesis from public sources; may miss developments outside the search window</li>
    <li>This dashboard is a personal scanning tool, not a regulated system of record. Always verify against authoritative sources before relying on data for committee work.</li>
  </ul>

</div>
</div>

<footer>
  <h3>&#9650; Top 3 Names Requiring Attention</h3>
  <ol>{top3_html}</ol>
</footer>
<script>{js}</script>
</body>
</html>"""


def main():
    run_start = datetime.now(pytz.utc)

    raw_a = call_claude(PROMPT_A, "Batch A")
    raw_b = call_claude(PROMPT_B, "Batch B")

    data_a, err_a = parse_json(raw_a, "Batch A")
    data_b, err_b = parse_json(raw_b, "Batch B")

    if err_a: print(f"WARNING: {err_a}")
    if err_b: print(f"WARNING: {err_b}")

    rows_a = data_a.get('rows', []) if data_a else []
    rows_b = data_b.get('rows', []) if data_b else []
    all_rows = rows_a + rows_b
    macro = (data_b or {}).get('macro', {}) or (data_a or {}).get('macro', {})
    top3 = (data_b or {}).get('top3', []) or (data_a or {}).get('top3', [])

    # Apply manual overrides for ratings
    all_rows = apply_overrides(all_rows)

    # Pull authoritative financials from SEC EDGAR (cached weekly)
    sec_metadata = {"from_cache": False, "names_succeeded": 0, "names_attempted": 0}
    sec_warnings = []
    sec_data = {}
    if SEC_EDGAR_AVAILABLE:
        sec_data, sec_warnings, sec_metadata = sec_edgar.fetch_financials(WATCHLIST)
        all_rows = sec_edgar.apply_sec_overrides(all_rows, sec_data)

    # Pull authoritative market data from yfinance and override Claude's stock fields
    market_data = fetch_market_data()
    all_rows = apply_market_overrides(all_rows, market_data)

    # Pull commodities, FX, and equity indices from yfinance
    commodities = fetch_commodities_fx()

    # Recompute status deterministically from the data (overrides Claude's call)
    all_rows = compute_status_from_data(all_rows)

    # Evaluate the 9 universal red flags
    flag_summary = None
    if RED_FLAGS_AVAILABLE:
        all_rows, flag_summary = red_flags.evaluate_flags(all_rows, sec_data)
        flagged_co = sum(1 for r in all_rows if r.get('_flag_count', 0) >= 1)
        print(f"Red Flags: {flag_summary['total_flagged_triggers']} total flagged triggers across {flagged_co} companies")

    print(f"Batch A: {len(rows_a)} rows, Batch B: {len(rows_b)} rows, Total: {len(all_rows)}")

    html = build_html(all_rows, macro, top3, datetime_str, commodities)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("index.html written successfully.")

    # Write run log
    if RUN_LOG_AVAILABLE:
        run_end = datetime.now(pytz.utc)
        red_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='red')
        amber_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='amber')
        green_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='green')
        log_entry = {
            "run_id": now.strftime("%Y-%m-%d-%H%M"),
            "run_started": run_start.isoformat(),
            "run_completed": run_end.isoformat(),
            "duration_seconds": int((run_end - run_start).total_seconds()),
            "data_sources": {
                "anthropic_claude": {
                    "model": "claude-sonnet-4-6",
                    "calls": 2,
                    "batches_succeeded": (1 if data_a else 0) + (1 if data_b else 0),
                },
                "sec_edgar": {
                    "from_cache": sec_metadata.get("from_cache", False),
                    "names_attempted": sec_metadata.get("names_attempted", 0),
                    "names_succeeded": sec_metadata.get("names_succeeded", 0),
                    "names_failed": sec_metadata.get("names_failed", []),
                    "names_no_sec_filer": sec_metadata.get("names_no_sec_filer", []),
                    "total_warnings": sec_metadata.get("total_warnings", 0),
                },
                "yfinance": {
                    "market_data_companies": len(market_data) if market_data else 0,
                    "commodities_indices": len(commodities) if commodities else 0,
                },
            },
            "overrides_applied": {
                "ratings_override": sum(1 for k in RATINGS_OVERRIDE if not k.startswith('_')),
            },
            "validation_warnings": sec_warnings[:50],  # cap at 50 to keep log compact
            "output": {
                "total_rows": len(all_rows),
                "red_count": red_count,
                "amber_count": amber_count,
                "green_count": green_count,
                "html_bytes": len(html),
            },
        }
        run_log.append_run_log(log_entry, path="runs.json", keep_last=60)


if __name__ == '__main__':
    main()
