"""
Sector Snapshot panel for the credit surveillance dashboard.

Renders the rollup section that sits at the top of the Overview tab.
Shows two portfolio-level composition bars (by rating, by severity),
a 90-day rating action summary, and a per-sector table with rating
distribution, median leverage, 90-day actions count, and the lowest-rated
name per sector.

Usage:
    from sector_snapshot import build_sector_snapshot
    snapshot_html = build_sector_snapshot(all_rows)
    # Insert snapshot_html into the overview pane at the top.

Notes on data lineage:
- Severity counts use the `severity` field set by compute_status_from_flags
  in generate.py (values: critical, high, watch, monitor).
- Rating bucket assignment uses the WORST rating across Moody's, S&P, and
  Fitch (most conservative credit-officer view) to bucket each name into
  HY, XO (BB+ split), BBB, A, AA+, or NR.
- Median rating per sector is the median of names' worst-rating numeric
  scores, converted back to S&P-equivalent letter.
- 90-day actions is a COUNT of names with any agency rating action date
  within the last 90 days (direction is not tracked since the framework
  doesn't yet persist prior-state ratings; can be enhanced later via
  runs.json diffing).
"""

from datetime import datetime
from collections import defaultdict


# S&P rating scale as canonical numeric values (lower = higher rating).
SP_RATING_SCALE = {
    'AAA': 1,
    'AA+': 2, 'AA': 3, 'AA-': 4,
    'A+': 5, 'A': 6, 'A-': 7,
    'BBB+': 8, 'BBB': 9, 'BBB-': 10,
    'BB+': 11, 'BB': 12, 'BB-': 13,
    'B+': 14, 'B': 15, 'B-': 16,
    'CCC+': 17, 'CCC': 18, 'CCC-': 19,
    'CC': 20, 'C': 21, 'D': 22,
}
NUMERIC_TO_SP = {v: k for k, v in SP_RATING_SCALE.items()}

# Moody's notation to S&P-equivalent mapping.
MOODYS_TO_SP = {
    'AAA': 'AAA',
    'AA1': 'AA+', 'AA2': 'AA', 'AA3': 'AA-',
    'A1': 'A+', 'A2': 'A', 'A3': 'A-',
    'BAA1': 'BBB+', 'BAA2': 'BBB', 'BAA3': 'BBB-',
    'BA1': 'BB+', 'BA2': 'BB', 'BA3': 'BB-',
    'B1': 'B+', 'B2': 'B', 'B3': 'B-',
    'CAA1': 'CCC+', 'CAA2': 'CCC', 'CAA3': 'CCC-',
    'CA': 'CC', 'C': 'C',
}


def _normalize_rating(rating_str):
    """Convert any rating to S&P-equivalent canonical uppercase string, or None."""
    if not rating_str:
        return None
    r = str(rating_str).strip().upper()
    if not r or r in ('N/A', 'NR', '-', 'NONE'):
        return None
    if r in SP_RATING_SCALE:
        return r
    if r in MOODYS_TO_SP:
        return MOODYS_TO_SP[r]
    return None


def _rating_to_numeric(rating_str):
    canonical = _normalize_rating(rating_str)
    return SP_RATING_SCALE.get(canonical) if canonical else None


def _numeric_to_rating(n):
    return NUMERIC_TO_SP.get(n, 'NR')


def _worst_rating_numeric(row):
    """Numeric value of the worst (lowest) rating across the three agencies."""
    worst = None
    for rf in ('sp_rating', 'fitch_rating', 'moodys_rating'):
        n = _rating_to_numeric(row.get(rf))
        if n is not None and (worst is None or n > worst):
            worst = n
    return worst


def _rating_bucket(row):
    """Assign a name to a rating quality bucket based on worst rating."""
    worst = _worst_rating_numeric(row)
    if worst is None:
        return 'nr'
    if worst <= 4:
        return 'aa_plus'
    if worst <= 7:
        return 'a'
    if worst <= 10:
        return 'bbb'
    if worst == 11:
        return 'xo'
    return 'hy'


def _median(values):
    """Median of a list (returns the more conservative middle value for even counts)."""
    if not values:
        return None
    sv = sorted(values)
    n = len(sv)
    mid = n // 2
    # Odd: middle element. Even: take the higher index (= worse rating numeric) for conservatism.
    return sv[mid] if n % 2 == 1 else sv[mid]


def _has_negative_outlook(row):
    for of in ('moodys_outlook', 'sp_outlook', 'fitch_outlook'):
        val = (row.get(of) or '').strip().lower()
        if val in ('negative', 'rur'):
            return True
    return False


def _aggregate_sector(name, rows):
    n = len(rows)
    sev_counts = {'critical': 0, 'high': 0, 'watch': 0, 'monitor': 0}
    rating_buckets = {'hy': 0, 'xo': 0, 'bbb': 0, 'a': 0, 'aa_plus': 0, 'nr': 0}
    rating_numerics = []
    neg_outlook_count = 0

    for r in rows:
        sev = (r.get('severity') or '').lower()
        if sev in sev_counts:
            sev_counts[sev] += 1
        bucket = _rating_bucket(r)
        rating_buckets[bucket] += 1
        n_val = _worst_rating_numeric(r)
        if n_val is not None:
            rating_numerics.append(n_val)
        if _has_negative_outlook(r):
            neg_outlook_count += 1

    median_numeric = _median(rating_numerics)
    median_rating = _numeric_to_rating(median_numeric) if median_numeric is not None else 'NR'

    lev_values = []
    for r in rows:
        try:
            v_str = str(r.get('nd_ebitda', '')).replace('x', '').strip()
            if v_str and v_str.lower() not in ('n/a', 'none', ''):
                lev_values.append(float(v_str))
        except (ValueError, TypeError):
            pass
    median_lev = _median(lev_values) if lev_values else None

    today = datetime.now().date()
    actions_90d = 0
    for r in rows:
        for df in ('moodys_date', 'sp_date', 'fitch_date'):
            d_str = r.get(df)
            if d_str and d_str != 'n/a':
                try:
                    d = datetime.strptime(d_str, '%Y-%m-%d').date()
                    if 0 <= (today - d).days <= 90:
                        actions_90d += 1
                        break
                except (ValueError, TypeError):
                    pass

    lowest = _find_lowest_rated(rows)

    return {
        'name': name,
        'n': n,
        'sev': sev_counts,
        'rtg_buckets': rating_buckets,
        'median_rating': median_rating,
        'neg_outlook': neg_outlook_count,
        'median_lev': median_lev,
        'actions_90d': actions_90d,
        'lowest_rated': lowest,
    }


def _find_lowest_rated(rows):
    """Find the lowest-rated name (NR treated as bottom of scale, ties broken by flag count)."""
    if not rows:
        return None
    tagged = []
    for r in rows:
        worst = _worst_rating_numeric(r)
        flag_count = int(r.get('_flag_count', 0) or 0)
        watch_count = int(r.get('_watch_count', 0) or 0)
        tagged.append((worst, flag_count, watch_count, r))

    def sort_key(t):
        worst, flags, watches, _ = t
        worst_for_sort = worst if worst is not None else 99
        return (-worst_for_sort, -flags, -watches)

    tagged.sort(key=sort_key)
    worst, flag_count, watch_count, winner = tagged[0]
    rating_label = _numeric_to_rating(worst) if worst is not None else 'NR'

    return {
        'name': winner.get('company', ''),
        'rating': rating_label,
        'flag_count': flag_count,
        'watch_count': watch_count,
    }


def _aggregate_portfolio(all_rows):
    total = len(all_rows)
    sev_totals = {'critical': 0, 'high': 0, 'watch': 0, 'monitor': 0}
    rating_totals = {'hy': 0, 'xo': 0, 'bbb': 0, 'a': 0, 'aa_plus': 0, 'nr': 0}
    rating_numerics = []

    for r in all_rows:
        sev = (r.get('severity') or '').lower()
        if sev in sev_totals:
            sev_totals[sev] += 1
        bucket = _rating_bucket(r)
        rating_totals[bucket] += 1
        n_val = _worst_rating_numeric(r)
        if n_val is not None:
            rating_numerics.append(n_val)

    median_numeric = _median(rating_numerics)
    median_rating = _numeric_to_rating(median_numeric) if median_numeric is not None else 'NR'

    ig_count = rating_totals['bbb'] + rating_totals['a'] + rating_totals['aa_plus']
    hy_count = rating_totals['hy'] + rating_totals['xo']
    ig_pct = (ig_count / total * 100) if total > 0 else 0
    hy_pct = (hy_count / total * 100) if total > 0 else 0

    return {
        'total_names': total,
        'sev_totals': sev_totals,
        'rating_totals': rating_totals,
        'median_rating': median_rating,
        'ig_pct': ig_pct,
        'hy_pct': hy_pct,
    }


RATING_BUCKET_COLORS = {
    'hy':      ('#ff6b6b', '#3a0808'),
    'xo':      ('#ff8a3d', '#3a1a00'),
    'bbb':     ('#f0b429', '#3a2a00'),
    'a':       ('#4ec38a', '#0a2a18'),
    'aa_plus': ('#2e8a5b', '#e6f4ed'),
    'nr':      ('#5a6878', '#e6edf3'),
}
RATING_BUCKET_LABELS = {
    'hy': 'HY', 'xo': 'XO', 'bbb': 'BBB',
    'a': 'A', 'aa_plus': 'AA+', 'nr': 'NR',
}
RATING_BUCKET_ORDER = ['hy', 'xo', 'bbb', 'a', 'aa_plus', 'nr']

SEVERITY_COLORS = {
    'critical': ('#ff5a5a', '#3a0808'),
    'high':     ('#ff8a3d', '#3a1a00'),
    'watch':    ('#f0b429', '#3a2a00'),
    'monitor':  ('#4ec38a', '#0a2a18'),
}
SEVERITY_LABELS = {
    'critical': 'Critical', 'high': 'High',
    'watch': 'Amber', 'monitor': 'Monitor',
}
SEVERITY_ORDER = ['critical', 'high', 'watch', 'monitor']


def _render_big_bar(buckets, order, colors, labels, total, skip_empty_keys=None):
    if total <= 0:
        return ''
    skip_empty_keys = skip_empty_keys or set()
    parts = []
    for key in order:
        count = buckets.get(key, 0)
        if count == 0 and key in skip_empty_keys:
            continue
        pct = (count / total * 100) if total > 0 else 0
        bg, txt = colors[key]
        label = labels[key]
        if pct >= 6:
            content = f'<div class="snap-comp-count">{count}</div><div class="snap-comp-name">{label.upper()}</div>'
        elif pct >= 2.5:
            content = f'<div class="snap-comp-count" style="font-size:12px">{count}</div>'
        else:
            content = ''
        tooltip = f'{count} names &middot; {pct:.1f}% &middot; {label}'
        parts.append(
            f'<div class="snap-comp-seg" title="{tooltip}" '
            f'style="width:{pct:.2f}%; background:{bg}; color:{txt};">'
            f'{content}</div>'
        )
    return f'<div class="snap-comp-bar">{"".join(parts)}</div>'


def _render_actions_summary(sectors_sorted):
    total_actions = sum(s['actions_90d'] for s in sectors_sorted)
    active = sorted(
        [s for s in sectors_sorted if s['actions_90d'] > 0],
        key=lambda s: -s['actions_90d']
    )[:4]
    if active:
        parts = [
            f'{s["name"]} <span style="color:#a0c4e8">{s["actions_90d"]}</span>'
            for s in active
        ]
        sep = ' <span style="color:#2a3645; margin: 0 8px;">|</span> '
        active_str = sep.join(parts)
    else:
        active_str = '<span style="color:#4a6080">No actions in last 90 days.</span>'

    total_label = f'{total_actions} action{"s" if total_actions != 1 else ""} across the watchlist'
    return f'''
    <div class="snap-actions-footer">
      <div>
        <span class="snap-actions-label">90D RATING ACTIONS</span>
        <span class="snap-actions-value">{total_label}</span>
      </div>
      <div>
        <span class="snap-actions-label">MOST ACTIVE</span>
        <span class="snap-actions-value">{active_str}</span>
      </div>
    </div>
    '''


def _rating_color_text(rating):
    if not rating or rating == 'NR':
        return '#5a6878'
    r = rating.upper()
    if r.startswith('AAA') or r.startswith('AA'):
        return '#2e8a5b'
    if r[0] == 'A':
        return '#4ec38a'
    if r.startswith('BBB'):
        return '#f0b429'
    if r.startswith('BB+'):
        return '#ff8a3d'
    return '#ff6b6b'


def _format_severity_sublabel(sev):
    parts = []
    if sev['critical'] > 0:
        parts.append(f'<span style="color:#ff5a5a">{sev["critical"]}C</span>')
    if sev['high'] > 0:
        parts.append(f'<span style="color:#ff8a3d">{sev["high"]}H</span>')
    if sev['watch'] > 0:
        parts.append(f'<span style="color:#f0b429">{sev["watch"]}A</span>')
    parts.append(f'<span style="color:#4ec38a">{sev["monitor"]}M</span>')
    return ' &middot; '.join(parts)


def _format_rating_label(median_rating, neg_outlook):
    rtg_color = _rating_color_text(median_rating)
    label = f'<span style="color:{rtg_color}">Median {median_rating}</span>'
    if neg_outlook > 0:
        label += (
            f' <span style="color:#7090a8">&middot;</span> '
            f'<span style="color:#ff8a3d">{neg_outlook} neg outlook'
            f'{"s" if neg_outlook > 1 else ""}</span>'
        )
    return label


def _format_med_lev(lev):
    if lev is None:
        return '<span style="color:#5a6878">n/a</span>'
    color = '#a0b4c8'
    if lev > 5:
        color = '#ff5a5a'
    elif lev > 3:
        color = '#f0b429'
    return f'<span style="color:{color}">{lev:.1f}x</span>'


def _format_actions(count):
    if count == 0:
        return '<span style="color:#4a6080">&mdash;</span>'
    return f'<span style="color:#a0c4e8">{count}</span>'


def _format_lowest_rated_cell(lr):
    if not lr:
        return ''
    rtg_color = _rating_color_text(lr['rating'])
    main = (
        f'<span class="snap-lr-name">{lr["name"]}</span>'
        f'<span class="snap-lr-rating" style="color:{rtg_color}">{lr["rating"]}</span>'
    )
    if lr['flag_count'] > 0 or lr['watch_count'] > 0:
        flag_color = '#7090a8'
        if lr['flag_count'] >= 5:
            flag_color = '#ff5a5a'
        elif lr['flag_count'] >= 3:
            flag_color = '#ff8a3d'
        elif lr['flag_count'] >= 1:
            flag_color = '#f0b429'
        suffix = []
        if lr['flag_count'] > 0:
            suffix.append(f'{lr["flag_count"]}F')
        if lr['watch_count'] > 0:
            suffix.append(f'{lr["watch_count"]}W')
        main += f'<div class="snap-lr-flags" style="color:{flag_color}">{"+".join(suffix)}</div>'
    return main


def _left_border_color(rtg_buckets, n):
    if rtg_buckets['hy'] > 0:
        return '#ff6b6b'
    if rtg_buckets['xo'] > 0:
        return '#ff8a3d'
    if rtg_buckets['bbb'] >= n / 2:
        return '#f0b429'
    return 'transparent'


def _render_rating_dist_bar(rtg_buckets, n):
    if n <= 0:
        return ''
    parts = []
    for key in RATING_BUCKET_ORDER:
        pct = rtg_buckets[key] / n * 100
        if pct > 0:
            bg = RATING_BUCKET_COLORS[key][0]
            parts.append(f'<div style="background:{bg}; width:{pct:.1f}%"></div>')
    return f'<div class="snap-mix-bar">{"".join(parts)}</div>'


def _render_sector_row(s):
    lb = _left_border_color(s['rtg_buckets'], s['n'])
    sev_sublabel = _format_severity_sublabel(s['sev'])
    rtg_bar = _render_rating_dist_bar(s['rtg_buckets'], s['n'])
    rtg_label = _format_rating_label(s['median_rating'], s['neg_outlook'])
    med_lev = _format_med_lev(s['median_lev'])
    actions = _format_actions(s['actions_90d'])
    lr_cell = _format_lowest_rated_cell(s['lowest_rated'])

    return (
        f'<tr class="snap-sec-row" data-sector="{s["name"]}" '
        f'style="border-left: 3px solid {lb};">'
        f'<td class="snap-sec-cell">'
        f'<div class="snap-sec-name">{s["name"]}</div>'
        f'<div class="snap-sec-sev">{sev_sublabel}</div>'
        f'</td>'
        f'<td class="snap-sec-cell snap-sec-n">{s["n"]}</td>'
        f'<td class="snap-sec-cell">'
        f'{rtg_bar}'
        f'<div class="snap-mix-label">{rtg_label}</div>'
        f'</td>'
        f'<td class="snap-sec-cell snap-metric-cell">{med_lev}</td>'
        f'<td class="snap-sec-cell snap-actions-cell">{actions}</td>'
        f'<td class="snap-sec-cell">{lr_cell}</td>'
        f'</tr>'
    )


def build_sector_snapshot(all_rows, top_n=14):
    """Build the full Sector Snapshot HTML section.

    Insert the returned string at the top of the Overview pane in build_html().
    Returns empty string if all_rows is empty.
    """
    if not all_rows:
        return ''

    by_sector = defaultdict(list)
    for r in all_rows:
        sec = r.get('sector') or 'Unknown'
        by_sector[sec].append(r)

    sectors = [_aggregate_sector(name, rows) for name, rows in by_sector.items()]
    portfolio = _aggregate_portfolio(all_rows)

    sectors_sorted = sorted(sectors, key=lambda s: (
        -(s['rtg_buckets']['hy'] + s['rtg_buckets']['xo']),
        -(s['rtg_buckets']['bbb'] / max(s['n'], 1)),
        -s['n'],
    ))
    top_sectors = sectors_sorted[:top_n]

    rating_bar_html = _render_big_bar(
        portfolio['rating_totals'], RATING_BUCKET_ORDER, RATING_BUCKET_COLORS,
        RATING_BUCKET_LABELS, portfolio['total_names'],
        skip_empty_keys={'nr', 'xo'}
    )
    severity_bar_html = _render_big_bar(
        portfolio['sev_totals'], SEVERITY_ORDER, SEVERITY_COLORS,
        SEVERITY_LABELS, portfolio['total_names']
    )
    actions_summary_html = _render_actions_summary(sectors_sorted)
    rows_html = ''.join(_render_sector_row(s) for s in top_sectors)

    more_note = ''
    if len(sectors_sorted) > top_n:
        more_note = f'SHOWING TOP {top_n} OF {len(sectors_sorted)} SECTORS BY STRESS &middot; '

    return f'''
    <style>{_SNAPSHOT_CSS}</style>
    <div class="snap-section">
      <div class="snap-header">
        <div>
          <div class="snap-title">SECTOR SNAPSHOT</div>
          <div class="snap-subtitle">Portfolio composition (top) and per-sector credit quality (table).</div>
        </div>
        <div class="snap-summary">
          <div>{portfolio["total_names"]} NAMES &middot; {len(sectors)} SECTORS</div>
          <div class="snap-summary-stats">MEDIAN {portfolio["median_rating"]} &middot; {portfolio["ig_pct"]:.0f}% IG &middot; {portfolio["hy_pct"]:.0f}% HY/XO</div>
        </div>
      </div>

      <div class="snap-composition">
        <div class="snap-comp-header">
          <div class="snap-comp-label">BY RATING</div>
          <div class="snap-comp-sublabel">STRUCTURAL CREDIT QUALITY</div>
        </div>
        {rating_bar_html}

        <div class="snap-comp-header" style="margin-top: 18px;">
          <div class="snap-comp-label">BY SEVERITY</div>
          <div class="snap-comp-sublabel">CURRENT FLAG-FRAMEWORK STATE</div>
        </div>
        {severity_bar_html}

        {actions_summary_html}
      </div>

      <table class="snap-table">
        <colgroup>
          <col style="width: 19%;">
          <col style="width: 5%;">
          <col style="width: 28%;">
          <col style="width: 9%;">
          <col style="width: 14%;">
          <col style="width: 25%;">
        </colgroup>
        <thead>
          <tr>
            <th style="text-align: left;">Sector</th>
            <th style="text-align: center;">N</th>
            <th style="text-align: left;">Rating Distribution</th>
            <th style="text-align: right;">Med Lev</th>
            <th style="text-align: center;">Actions 90d</th>
            <th style="text-align: left;">Lowest Rated</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>

      <div class="snap-footer">
        <span>{more_note}HOVER ANY BAR SEGMENT FOR DETAIL &middot; ACTIONS 90D = NAMES WITH ANY AGENCY ACTION IN LAST 90 DAYS</span>
      </div>
    </div>
    '''


_SNAPSHOT_CSS = """
.snap-section { background: #0a0e14; border: 1px solid #1e2a3a; border-radius: 4px; color: #e6edf3; margin: 0 28px 18px; overflow: hidden; font-family: 'IBM Plex Sans', system-ui, -apple-system, sans-serif; }
.snap-header { padding: 14px 18px; border-bottom: 1px solid #1e2a3a; display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.snap-title { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; color: #c11515; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 500; }
.snap-subtitle { font-size: 11px; color: #7090a8; margin-top: 4px; }
.snap-summary { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; color: #4a6080; letter-spacing: 0.5px; text-align: right; }
.snap-summary-stats { margin-top: 4px; color: #7090a8; }
.snap-composition { padding: 18px 18px 16px; border-bottom: 1px solid #1e2a3a; background: linear-gradient(180deg, #0c121b 0%, #0a0e14 100%); }
.snap-comp-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.snap-comp-label { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; color: #a0c4e8; letter-spacing: 1.5px; font-weight: 500; }
.snap-comp-sublabel { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; color: #4a6080; letter-spacing: 0.5px; }
.snap-comp-bar { display: flex; height: 34px; border-radius: 3px; overflow: hidden; background: #0d1520; }
.snap-comp-seg { display: flex; flex-direction: column; justify-content: center; align-items: center; transition: opacity 0.12s; cursor: pointer; padding: 0 8px; border-right: 1px solid rgba(10, 14, 20, 0.4); overflow: hidden; min-width: 0; }
.snap-comp-seg:last-child { border-right: none; }
.snap-comp-seg:hover { opacity: 0.78; }
.snap-comp-count { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-weight: 700; font-size: 15px; line-height: 1; }
.snap-comp-name { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; letter-spacing: 1px; margin-top: 4px; opacity: 0.85; }
.snap-actions-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid #1a2230; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; flex-wrap: wrap; gap: 8px; color: #7090a8; }
.snap-actions-label { color: #4a6080; letter-spacing: 1px; }
.snap-actions-value { margin-left: 10px; }
.snap-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.snap-table thead tr { background: #0d1117; }
.snap-table thead th { padding: 9px 12px; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; color: #4a6080; letter-spacing: 1px; text-transform: uppercase; font-weight: 500; border-bottom: 1px solid #1e2a3a; }
.snap-sec-row { transition: background 0.12s; cursor: pointer; }
.snap-sec-row:hover { background: rgba(139, 0, 0, 0.07); }
.snap-sec-row td { border-bottom: 1px solid #0d1520; vertical-align: middle; }
.snap-sec-cell { padding: 11px 12px; vertical-align: middle; }
.snap-sec-name { font-size: 13px; font-weight: 500; color: #e6edf3; }
.snap-sec-sev { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; color: #7090a8; margin-top: 3px; letter-spacing: 0.3px; }
.snap-sec-n { text-align: center; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; color: #a0b4c8; }
.snap-mix-bar { display: flex; height: 8px; border-radius: 2px; overflow: hidden; background: #0d1520; }
.snap-mix-label { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 10px; margin-top: 4px; letter-spacing: 0.3px; }
.snap-metric-cell { text-align: right; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; padding-right: 8px; }
.snap-actions-cell { text-align: center; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; padding: 11px 8px; }
.snap-lr-name { color: #e6edf3; font-size: 12px; font-weight: 500; }
.snap-lr-rating { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px; font-weight: 600; margin-left: 5px; }
.snap-lr-flags { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; margin-top: 3px; letter-spacing: 0.3px; }
.snap-footer { padding: 11px 18px; border-top: 1px solid #1e2a3a; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 9px; color: #4a6080; letter-spacing: 0.5px; }
"""
