import anthropic
import json
import re
import os
from datetime import datetime
import pytz

# ── Date/time ──────────────────────────────────────────────────────────────────
et = pytz.timezone('America/New_York')
now = datetime.now(et)
datetime_str = now.strftime('%B %d, %Y at %I:%M %p ET')

# ── Anthropic client ───────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# ── Prompts ────────────────────────────────────────────────────────────────────
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
Source from yahoo.com/finance, google.com/finance, or stockanalysis.com. Use yesterday's close for 1-day if market is closed.

NEXT EARNINGS DATE:
Source from earningswhispers.com, yahoo.com/finance, or the company's IR page.

NEWS (last 24 to 48 hours):
Source from reuters.com, bloomberg.com, wsj.com, ft.com, agency press releases (moodys.com, spglobal.com, fitchratings.com), or sec.gov 8-K filings.

Use web search to source values. For well-known public companies, use your best available knowledge if a specific value is not directly returned by search. Only return "n/a" if the value is genuinely unknowable or the data is unavailable for that company. Financial metrics that are not found via search should be estimated from the most recent publicly available figures rather than defaulting to n/a.

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
- Cap the total at 100.

OUTPUT FORMAT: Return ONLY a valid JSON object. No markdown. No code fences. No text before or after the JSON.

{{"rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "concern_score": 35, "key_dev": "No material news.", "action": "Hold"}}]}}

Rules:
- All 38 names must appear in rows.
- All dollar figures in $Bn. Round to one decimal.
- Net Debt/EBITDA: number only, no "x".
- EBITDA Margin: number only, no % sign.
- Stock percentages: string with + or - prefix, no % symbol.
- week52_high and week52_low: USD price, no $ sign, two decimals.
- concern_score: integer 0-100.
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
Source from yahoo.com/finance, google.com/finance, or stockanalysis.com. Use yesterday's close for 1-day if market is closed.

NEXT EARNINGS DATE:
Source from earningswhispers.com, yahoo.com/finance, or the company's IR page.

NEWS (last 24 to 48 hours):
Source from reuters.com, bloomberg.com, wsj.com, ft.com, agency press releases (moodys.com, spglobal.com, fitchratings.com), or sec.gov 8-K filings.

MACRO INDICATORS (source once):
Source from wsj.com, bloomberg.com, or fred.stlouisfed.org.
- US HY OAS spread (ICE BofA index, in basis points)
- US IG OAS spread (ICE BofA index, in basis points)
- 10-year US Treasury yield (%)
- 2-year US Treasury yield (%)
- VIX index level
- S&P 500 level and 1-day percentage change

Use web search to source values. For well-known public companies, use your best available knowledge if a specific value is not directly returned by search. Only return "n/a" if the value is genuinely unknowable or the data is unavailable for that company. Financial metrics that are not found via search should be estimated from the most recent publicly available figures rather than defaulting to n/a.

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
- Cap the total at 100.

OUTPUT FORMAT: Return ONLY a valid JSON object. No markdown. No code fences. No text before or after the JSON.

{{"macro": {{"hy_oas": "350", "ig_oas": "95", "treasury_10y": "4.42", "treasury_2y": "4.85", "vix": "18.2", "sp500": "5234", "sp500_1d": "+0.8"}}, "rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "concern_score": 35, "key_dev": "No material news.", "action": "Hold"}}], "top3": [{{"name": "Company A", "note": "Short reason"}}]}}

Rules:
- All 37 names must appear in rows.
- All dollar figures in $Bn. Round to one decimal.
- Net Debt/EBITDA: number only, no "x".
- EBITDA Margin: number only, no % sign.
- Stock percentages: string with + or - prefix, no % symbol.
- week52_high and week52_low: USD price, no $ sign, two decimals.
- concern_score: integer 0-100.
- key_dev for GREEN: exactly "No material news."
- key_dev for AMBER/RED: 1-2 sentences, under 200 characters.
- top3: 3 names from across BOTH batches most requiring attention today.
- macro values: hy_oas and ig_oas as integer strings. treasury yields and vix one decimal. sp500 integer string no comma. sp500_1d with + or - prefix.
- Public information only."""


def call_claude(prompt, batch_name):
    print(f"Calling Claude for {batch_name}...")
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=16000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
        messages=[{"role": "user", "content": prompt}]
    )
    # Extract the final text response
    for block in reversed(response.content):
        if hasattr(block, 'text'):
            return block.text.strip()
    return ""


def parse_json(raw, label):
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        cleaned = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    try:
        return json.loads(cleaned), None
    except Exception as e:
        return None, f"JSON parse error in {label}: {str(e)[:200]}"


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
    bar = f'<div style="background:#21262d;border-radius:3px;height:5px;margin-top:3px;width:60px;display:inline-block"><div style="background:{color};border-radius:3px;height:5px;width:{min(score,100)}%"></div></div>'
    return f'<td class="num-cell" style="color:{color};font-weight:700">{score}<br>{bar}</td>'


def build_html(all_rows, macro, top3, datetime_str):
    rows_html = []
    for r in all_rows:
        status = r.get('status', 'green').lower()
        rows_html.append(
            f'<tr data-status="{status}">'
            f'<td style="font-weight:600">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            f'<td class="status {status}">{status.upper()}</td>'
            + num_cell(r.get('mkt_cap'))
            + num_cell(r.get('nd_ebitda'))
            + num_cell(r.get('ebitda_margin'), '%')
            + num_cell(r.get('fcf_ltm'))
            + num_cell(r.get('cash'))
            + num_cell(r.get('total_debt'))
            + f'<td>{r.get("earnings","TBD")}</td>'
            + stock_cell(r.get('stock_1d'))
            + stock_cell(r.get('stock_1m'))
            + stock_cell(r.get('stock_ytd'))
            + num_cell(r.get('week52_high'))
            + num_cell(r.get('week52_low'))
            + score_cell(r.get('concern_score', 'n/a'))
            + f'<td class="key-dev">{r.get("key_dev","")}</td>'
            + f'<td class="action-cell"><span class="action-badge {status}">{r.get("action","Hold")}</span></td>'
            + '</tr>'
        )

    top3_html = ''.join(
        f'<li><strong>{i.get("name","")}</strong>: {i.get("note","")}</li>'
        for i in top3
    )

    hy_oas = macro.get('hy_oas', 'n/a')
    ig_oas = macro.get('ig_oas', 'n/a')
    t10y = macro.get('treasury_10y', 'n/a')
    t2y = macro.get('treasury_2y', 'n/a')
    vix = macro.get('vix', 'n/a')
    sp500 = macro.get('sp500', 'n/a')
    sp500_1d = macro.get('sp500_1d', '')
    sp500_up = str(sp500_1d).startswith('+')

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

    css = (
        '@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{font-family:"IBM Plex Sans",-apple-system,sans-serif;background:#0a0e14;color:#e6edf3;font-size:13px}'
        'header{background:linear-gradient(135deg,#6b0000 0%,#8B0000 60%,#a00000 100%);color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;border-bottom:2px solid #ff000033}'
        '.title{font-size:22px;font-weight:700;letter-spacing:2px;font-family:"IBM Plex Mono",monospace}'
        '.subtitle{font-size:11px;margin-top:3px;opacity:.75;letter-spacing:1px;text-transform:uppercase}'
        '.right-block{text-align:right}'
        '.pills{display:flex;gap:8px;justify-content:flex-end}'
        '.pill{padding:5px 14px;border-radius:3px;font-weight:700;font-size:11px;color:#fff;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}'
        '.pill.red{background:#cc0000}.pill.amber{background:#e6a700}.pill.green{background:#2e7d32}'
        '.last-refresh{font-size:10px;margin-top:6px;opacity:.7;font-family:"IBM Plex Mono",monospace}'
        '.macro-strip{background:#0d1520;border-bottom:1px solid #1e3a5f;padding:10px 28px;display:flex;gap:0;flex-wrap:wrap;align-items:center}'
        '.macro-item{padding:4px 20px;border-right:1px solid #1e3a5f;display:flex;flex-direction:column;align-items:center;gap:2px}'
        '.macro-item:last-child{border-right:none;margin-left:auto}'
        '.macro-label{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#4a6080;font-family:"IBM Plex Mono",monospace}'
        '.macro-value{font-size:13px;font-weight:600;color:#a0c4e8;font-family:"IBM Plex Mono",monospace}'
        '.macro-up{font-size:10px;color:#4ec38a;font-weight:600}'
        '.macro-down{font-size:10px;color:#ff6b6b;font-weight:600}'
        '.macro-note{font-size:10px;color:#3a4a5a;align-items:flex-end;border-right:none}'
        '.controls{padding:12px 28px;background:#0d1117;border-bottom:1px solid #1e2a3a;display:flex;gap:8px;flex-wrap:wrap;align-items:center}'
        '.controls button{padding:6px 14px;border:1px solid #1e2a3a;background:#0d1520;color:#a0b4c8;cursor:pointer;font-weight:600;border-radius:3px;font-size:11px;letter-spacing:.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;transition:all .15s}'
        '.controls button:hover{background:#1e2a3a;color:#e6edf3}'
        '.controls button.active{background:#8B0000;color:#fff;border-color:#8B0000}'
        '.controls input,.controls select{padding:6px 12px;border:1px solid #1e2a3a;border-radius:3px;font-size:12px;background:#0d1520;color:#e6edf3}'
        '.controls input{width:200px}'
        'table{width:100%;border-collapse:collapse;background:#0a0e14}'
        'thead th{background:#0d1117;color:#4a6080;padding:10px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;cursor:pointer;user-select:none;position:sticky;top:0;font-family:"IBM Plex Mono",monospace;white-space:nowrap}'
        'thead th:hover{background:#0d1520;color:#a0b4c8}'
        'tbody td{padding:9px 10px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle}'
        'tbody tr:hover{background:#0d1520}'
        '.status{font-weight:700;font-size:11px;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}'
        '.status.red{color:#ff6b6b}.status.amber{color:#f0b429}.status.green{color:#4ec38a}'
        '.sector-tag{background:#0d1520;border:1px solid #1e2a3a;color:#7090a8;font-size:10px;padding:2px 7px;border-radius:2px;letter-spacing:.5px;white-space:nowrap}'
        '.stock-up{color:#4ec38a;font-weight:700;font-family:"IBM Plex Mono",monospace}'
        '.stock-down{color:#ff6b6b;font-weight:700;font-family:"IBM Plex Mono",monospace}'
        '.stock-flat{color:#3a4a5a;font-family:"IBM Plex Mono",monospace}'
        '.num-cell{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace;font-size:12px}'
        '.key-dev{max-width:220px;color:#a0b4c8;font-size:11px;line-height:1.4}'
        '.action-cell{white-space:nowrap}'
        '.action-badge{font-size:10px;padding:3px 10px;border-radius:2px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace}'
        '.action-badge.red{background:#3a0000;color:#ff6b6b;border:1px solid #8B0000}'
        '.action-badge.amber{background:#2a1a00;color:#f0b429;border:1px solid #8b6200}'
        '.action-badge.green{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}'
        'footer{background:linear-gradient(135deg,#6b0000,#8B0000);color:#fff;padding:20px 28px;border-top:2px solid #ff000033}'
        'footer h3{margin-bottom:12px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;opacity:.8}'
        'footer ol{padding-left:20px}'
        'footer li{padding:5px 0;font-size:13px;line-height:1.5}'
        'footer li strong{color:#ffaaaa}'
    )

    js = (
        "(function(){"
        "var tb=document.getElementById('tableBody');"
        "var rows=Array.from(tb.querySelectorAll('tr'));"
        "var s=document.getElementById('searchBox');"
        "var sel=document.getElementById('sectorFilter');"
        "var btns=document.querySelectorAll('.controls button[data-filter]');"
        "var ths=document.querySelectorAll('thead th');"
        "var af='all';"
        "function ap(){"
        "var q=s.value.toLowerCase();var sv=sel.value;var g=0,a=0,r=0;"
        "rows.forEach(function(row){"
        "var st=(row.dataset.status||'').toLowerCase();"
        "var co=(row.cells[0].textContent||'').toLowerCase();"
        "var rs=(row.cells[1].textContent||'').trim();"
        "var pf=af=='all'||st==af;var ps=!q||co.indexOf(q)>-1;var psc=sv=='all'||rs==sv;"
        "var sh=pf&&ps&&psc;row.style.display=sh?'':'none';"
        "if(sh){if(st=='green')g++;else if(st=='amber')a++;else if(st=='red')r++;}"
        "});"
        "document.getElementById('greenCount').textContent='GREEN '+g;"
        "document.getElementById('amberCount').textContent='AMBER '+a;"
        "document.getElementById('redCount').textContent='RED '+r;"
        "}"
        "btns.forEach(function(b){b.addEventListener('click',function(){"
        "btns.forEach(function(x){x.classList.remove('active')});"
        "b.classList.add('active');af=b.dataset.filter;ap();});});"
        "s.addEventListener('input',ap);sel.addEventListener('change',ap);"
        "var secs=new Set();rows.forEach(function(r){var x=(r.cells[1].textContent||'').trim();if(x)secs.add(x);});"
        "Array.from(secs).sort().forEach(function(x){var o=document.createElement('option');o.value=x;o.textContent=x;sel.appendChild(o);});"
        "var sc=-1,sd=1;"
        "ths.forEach(function(th,idx){th.addEventListener('click',function(){"
        "var t=th.dataset.type||'text';"
        "if(sc==idx)sd=-sd;else{sc=idx;sd=1;}"
        "var sr=rows.slice().sort(function(a,b){"
        "var av=a.cells[idx].textContent.trim();var bv=b.cells[idx].textContent.trim();"
        "if(t=='num'){av=parseFloat(av.replace(/[^0-9.\\-]/g,''))||0;bv=parseFloat(bv.replace(/[^0-9.\\-]/g,''))||0;return (av-bv)*sd;}"
        "if(t=='date'){av=new Date(av).getTime()||0;bv=new Date(bv).getTime()||0;return (av-bv)*sd;}"
        "return av.localeCompare(bv)*sd;});"
        "tb.innerHTML='';sr.forEach(function(r){tb.appendChild(r);});});});"
        "ap();})();"
    )

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
      <span class="pill green" id="greenCount">GREEN 0</span>
      <span class="pill amber" id="amberCount">AMBER 0</span>
      <span class="pill red" id="redCount">RED 0</span>
    </div>
    <div class="last-refresh">Updated: {datetime_str}</div>
  </div>
</header>
{macro_html}
<div class="controls">
  <button class="active" data-filter="all">All</button>
  <button data-filter="red">Red</button>
  <button data-filter="amber">Amber</button>
  <button data-filter="green">Green</button>
  <input type="text" id="searchBox" placeholder="Search company...">
  <select id="sectorFilter"><option value="all">All Sectors</option></select>
</div>
<table>
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
  <th data-type="date">Next Earnings</th>
  <th data-type="num">1D %</th>
  <th data-type="num">1M %</th>
  <th data-type="num">YTD %</th>
  <th data-type="num">52W High</th>
  <th data-type="num">52W Low</th>
  <th data-type="num">Concern Score</th>
  <th data-type="text">Key Development</th>
  <th data-type="text">Action</th>
</tr></thead>
<tbody id="tableBody">{"".join(rows_html)}</tbody>
</table>
<footer>
  <h3>&#9650; Top 3 Names Requiring Attention</h3>
  <ol>{top3_html}</ol>
</footer>
<script>{js}</script>
</body>
</html>"""


def main():
    # Call both Claude batches
    raw_a = call_claude(PROMPT_A, "Batch A")
    raw_b = call_claude(PROMPT_B, "Batch B")

    data_a, err_a = parse_json(raw_a, "Batch A")
    data_b, err_b = parse_json(raw_b, "Batch B")

    if err_a:
        print(f"WARNING: {err_a}")
    if err_b:
        print(f"WARNING: {err_b}")

    rows_a = data_a.get('rows', []) if data_a else []
    rows_b = data_b.get('rows', []) if data_b else []
    all_rows = rows_a + rows_b
    macro = (data_b or {}).get('macro', {}) or (data_a or {}).get('macro', {})
    top3 = (data_b or {}).get('top3', []) or (data_a or {}).get('top3', [])

    print(f"Batch A: {len(rows_a)} rows, Batch B: {len(rows_b)} rows, Total: {len(all_rows)}")

    html = build_html(all_rows, macro, top3, datetime_str)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("index.html written successfully.")


if __name__ == '__main__':
    main()
