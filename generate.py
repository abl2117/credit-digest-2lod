import anthropic
import json
import os
from datetime import datetime, timedelta
import pytz

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
Source from stockanalysis.com, macrotrends.net, or the company's most recent 10-Q on sec.gov. Use LTM (trailing twelve months) where applicable.

STOCK DATA (1-day, 1-month, YTD percentage changes, 52-week high, 52-week low):
Source from yahoo.com/finance, google.com/finance, or stockanalysis.com.

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

{{"rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "moodys_rating": "Baa2", "moodys_outlook": "Stable", "moodys_date": "2025-10-15", "sp_rating": "BBB", "sp_outlook": "Stable", "sp_date": "2025-09-22", "fitch_rating": "BBB", "fitch_outlook": "Stable", "fitch_date": "2025-08-10", "concern_score": 35, "key_dev": "No material news.", "action": "Hold"}}]}}

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
Source from stockanalysis.com, macrotrends.net, or the company's most recent 10-Q on sec.gov. Use LTM (trailing twelve months) where applicable.

STOCK DATA (1-day, 1-month, YTD percentage changes, 52-week high, 52-week low):
Source from yahoo.com/finance, google.com/finance, or stockanalysis.com.

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

{{"macro": {{"hy_oas": "350", "ig_oas": "95", "treasury_10y": "4.42", "treasury_2y": "4.85", "vix": "18.2", "sp500": "5234", "sp500_1d": "+0.8"}}, "rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "moodys_rating": "Baa2", "moodys_outlook": "Stable", "moodys_date": "2025-10-15", "sp_rating": "BBB", "sp_outlook": "Stable", "sp_date": "2025-09-22", "fitch_rating": "BBB", "fitch_outlook": "Stable", "fitch_date": "2025-08-10", "concern_score": 35, "key_dev": "No material news.", "action": "Hold"}}], "top3": [{{"name": "Company A", "note": "Short reason"}}]}}

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
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 50}],
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


def build_html(all_rows, macro, top3, datetime_str):
    overview_rows, market_rows, fin_rows = [], [], []
    g_count = a_count = r_count = 0
    for r in all_rows:
        status = r.get('status','green').lower()
        if status == 'green': g_count += 1
        elif status == 'amber': a_count += 1
        elif status == 'red': r_count += 1

        # OVERVIEW row
        overview_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + ratings_cell(r)
            + score_cell(r.get('concern_score','n/a'))
            + f'<td class="key-dev" title="{r.get("key_dev","").replace(chr(34),"&quot;")}">{r.get("key_dev","")}</td>'
            + f'<td class="action-cell"><span class="action-badge {status}">{r.get("action","Hold")}</span></td>'
            + '</tr>'
        )

        # MARKET row
        market_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + stock_cell(r.get('stock_1d'))
            + stock_cell(r.get('stock_1m'))
            + stock_cell(r.get('stock_ytd'))
            + num_cell(r.get('week52_high'))
            + num_cell(r.get('week52_low'))
            + f'<td>{r.get("earnings","TBD")}</td>'
            + '</tr>'
        )

        # FINANCIALS row
        fin_rows.append(
            f'<tr data-status="{status}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + num_cell(r.get('mkt_cap'))
            + num_cell(r.get('nd_ebitda'))
            + num_cell(r.get('ebitda_margin'),'%')
            + num_cell(r.get('fcf_ltm'))
            + num_cell(r.get('cash'))
            + num_cell(r.get('total_debt'))
            + '</tr>'
        )

    top3_html = ''.join(
        f'<li><strong>{i.get("name","")}</strong>: {i.get("note","")}</li>'
        for i in top3
    )

    hy_oas = macro.get('hy_oas','n/a'); ig_oas = macro.get('ig_oas','n/a')
    t10y = macro.get('treasury_10y','n/a'); t2y = macro.get('treasury_2y','n/a')
    vix = macro.get('vix','n/a'); sp500 = macro.get('sp500','n/a')
    sp500_1d = macro.get('sp500_1d',''); sp500_up = str(sp500_1d).startswith('+')

    def macro_item(label, value, change=None, up=None):
        change_html = ''
        if change:
            cls = 'macro-up' if up else 'macro-down'
            arrow = '&#9650;' if up else '&#9660;'
            change_html = f'<span class="{cls}">{arrow} {change}</span>'
        return f'<div class="macro-item"><span class="macro-label">{label}</span><span class="macro-value">{value}</span>{change_html}</div>'

    macro_html = (
        '<div class="macro-strip">'
        + macro_item('HY OAS', f'{hy_oas} bps')
        + macro_item('IG OAS', f'{ig_oas} bps')
        + macro_item('10Y UST', f'{t10y}%')
        + macro_item('2Y UST', f'{t2y}%')
        + macro_item('VIX', vix)
        + macro_item('S&amp;P 500', sp500, sp500_1d, sp500_up)
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
.placeholder-pane{padding:80px 28px;text-align:center;color:#4a6080;font-family:"IBM Plex Mono",monospace;font-size:13px;letter-spacing:1px}
.placeholder-pane .ph-title{font-size:16px;color:#a0b4c8;margin-bottom:10px;letter-spacing:2px}
footer{background:linear-gradient(135deg,#6b0000,#8B0000);color:#fff;padding:20px 28px;border-top:2px solid #ff000033}
footer h3{margin-bottom:12px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;opacity:.8}
footer ol{padding-left:20px}
footer li{padding:5px 0;font-size:13px;line-height:1.5}
footer li strong{color:#ffaaaa}
"""

    js = """
(function(){
  var panes={overview:document.getElementById('pane-overview'),market:document.getElementById('pane-market'),financials:document.getElementById('pane-financials'),redflags:document.getElementById('pane-redflags')};
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
<table>
<colgroup>
<col style="width:14%"><col style="width:10%"><col style="width:7%"><col style="width:24%"><col style="width:9%"><col style="width:28%"><col style="width:8%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="text">Status</th>
  <th data-type="text">Ratings (M/S/F)</th>
  <th data-type="num">Concern</th>
  <th data-type="text">Key Development</th>
  <th data-type="text">Action</th>
</tr></thead>
<tbody>{"".join(overview_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-market">
<table>
<colgroup>
<col style="width:16%"><col style="width:11%"><col style="width:8%"><col style="width:9%"><col style="width:9%"><col style="width:9%"><col style="width:11%"><col style="width:11%"><col style="width:16%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="text">Status</th>
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
<col style="width:16%"><col style="width:11%"><col style="width:8%"><col style="width:10%"><col style="width:11%"><col style="width:11%"><col style="width:11%"><col style="width:10%"><col style="width:12%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th>
  <th data-type="text">Sector</th>
  <th data-type="text">Status</th>
  <th data-type="num">Mkt Cap $Bn</th>
  <th data-type="num">ND/EBITDA</th>
  <th data-type="num">EBITDA Mgn %</th>
  <th data-type="num">FCF LTM $Bn</th>
  <th data-type="num">Cash $Bn</th>
  <th data-type="num">Tot Debt $Bn</th>
</tr></thead>
<tbody>{"".join(fin_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-redflags">
<div class="placeholder-pane">
  <div class="ph-title">RED FLAGS FRAMEWORK</div>
  <div>15-flag framework integration pending</div>
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

    print(f"Batch A: {len(rows_a)} rows, Batch B: {len(rows_b)} rows, Total: {len(all_rows)}")

    html = build_html(all_rows, macro, top3, datetime_str)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("index.html written successfully.")


if __name__ == '__main__':
    main()
