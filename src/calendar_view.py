"""Month x year burning-activity calendar (US-04a: layout with sample values).

Draws the T-03 wireframe as HTML: one row per year (newest at the top), one column per
month, cells coloured with src/palette.py on its log scale, peak cells labelled with
their value, a tooltip on every cell, a legend, and optional outlines for unusual years
(US-06). US-04 feeds it the real harmonized record instead of sample_monthly().

    st.html(calendar_html(sample_monthly(), title='...'))
"""
from __future__ import annotations

import html
import math

import pandas as pd

from src import palette as P

LABEL_FRACTION = 0.05  # label cells with at least 5% of the busiest month on screen
FLAG_TEXT = {'high': 'unusually high', 'low': 'unusually low'}
FLAG_COLOR = {'high': P.FLAG_HIGH_COLOR, 'low': P.FLAG_LOW_COLOR}

# Sample values, shaped like a Canadian fire season (placeholders, not FIRMS data).
_SAMPLE_PROFILE = [2, 6, 25, 120, 600, 2500, 5200, 4100, 900, 200, 30, 3]
_SAMPLE_YEAR_SCALE = {2012: 0.9, 2013: 1.0, 2014: 1.4, 2015: 1.0, 2016: 1.2, 2017: 1.1,
                      2018: 1.3, 2019: 1.0, 2020: 0.35, 2021: 1.15, 2022: 0.95, 2023: 3.2}


def sample_monthly(area: str = 'Canada') -> pd.DataFrame:
    """Placeholder monthly record, 2012-2023, same columns the real data uses.

    Includes one month with no data (Jan 2012) and one with zero fires (Dec 2012) so the
    two special colours show; 2023 is a record year and 2020 a quiet one.
    """
    rows = []
    for year, scale in _SAMPLE_YEAR_SCALE.items():
        for month, base in enumerate(_SAMPLE_PROFILE, start=1):
            rows.append(dict(area=area, year=year, month=month, harmonized=float(round(base * scale))))
    df = pd.DataFrame(rows)
    df.loc[(df.year == 2012) & (df.month == 1), 'harmonized'] = math.nan
    df.loc[(df.year == 2012) & (df.month == 12), 'harmonized'] = 0.0
    return df


def format_count(value: float) -> str:
    """Short cell label: 950, 1.2k, 16.6k, 1.2M."""
    if value >= 1_000_000:
        return f'{math.floor(value / 100_000) / 10:.1f}M'
    if value >= 1_000:
        return f'{math.floor(value / 100) / 10:.1f}k'
    return f'{value:.0f}'


def _missing(value) -> bool:
    return value is None or pd.isna(value)


def calendar_html(monthly: pd.DataFrame, value_col: str = 'harmonized', *,
                  title: str = 'Monthly burning activity',
                  legend_title: str = 'Fire cell-days per month',
                  flags: dict[int, str] | None = None) -> str:
    """HTML for the calendar of one area. monthly: year, month and value_col columns.

    flags: {year: 'high' | 'low'} draws an outline around that year's row (US-06).
    """
    flags = flags or {}
    grid = (monthly.pivot_table(index='year', columns='month', values=value_col,
                                aggfunc='first', dropna=False)
            .reindex(columns=range(1, 13)).sort_index(ascending=False))
    top = pd.to_numeric(monthly[value_col], errors='coerce').max()
    vmax = float(top) if pd.notna(top) else 0.0
    esc = html.escape

    head = ''.join(f'<th class="fc-month">{m}</th>' for m in P.MONTH_LABELS)
    body = []
    for year, row in grid.iterrows():
        flag = flags.get(int(year))
        style = f' style="outline:3px solid {FLAG_COLOR[flag]};outline-offset:-1px"' if flag in FLAG_COLOR else ''
        cells = []
        for month in range(1, 13):
            v = row.get(month)
            name = f'{P.MONTH_LABELS[month - 1]} {int(year)}'
            if _missing(v):
                fill, label, tip = P.NO_DATA_COLOR, '', f'{name}: no data'
            else:
                v = float(v)
                fill = P.activity_color(v, vmax)
                show = vmax > 0 and v > 0 and v >= LABEL_FRACTION * vmax
                label = format_count(v) if show else ''
                tip = f'{name}: {v:,.0f}'
            cells.append(f'<td class="fc-cell" data-year="{int(year)}" data-month="{month}" '
                         f'title="{esc(tip)}" style="background:{fill};color:{P.text_color_for(fill)}">'
                         f'{esc(label)}</td>')
        note = f'<td class="fc-flag" style="color:{FLAG_COLOR[flag]}">{FLAG_TEXT[flag]}</td>' if flag in FLAG_COLOR else '<td class="fc-flag"></td>'
        body.append(f'<tr{style}><th class="fc-year" scope="row">{int(year)}</th>{"".join(cells)}{note}</tr>')

    def swatch(color: str, label: str, border: str = '#d0d0d0') -> str:
        return (f'<span class="fc-key"><span class="fc-swatch" style="background:{color};'
                f'border-color:{border}"></span><span>{esc(label)}</span></span>')

    legend = [swatch(P.NO_DATA_COLOR, 'no data'), swatch(P.ZERO_COLOR, '0')]
    legend += [swatch(c, label) for c, label in P.legend_bins(vmax)] if vmax > 0 else []
    flag_keys = ''.join(
        f'<span class="fc-key"><span class="fc-swatch" style="background:#fff;border:3px solid {FLAG_COLOR[k]}"></span>'
        f'<span>Year {FLAG_TEXT[k]} vs long-term average</span></span>'
        for k in ('high', 'low') if k in flags.values())

    return f"""
<style>
.fc-wrap {{ font-family: 'Source Sans Pro', Helvetica, Arial, sans-serif; color: {P.TEXT_DARK}; }}
.fc-title {{ font-weight: 600; font-size: 1.05rem; margin: 0 0 .5rem; }}
.fc-scroll {{ overflow-x: auto; }}
.fc-table {{ border-collapse: separate; border-spacing: 2px; }}
.fc-month {{ font-weight: 400; font-size: .8rem; color: #555; padding: 2px 0; min-width: 52px; }}
.fc-year {{ font-weight: 400; font-size: .85rem; color: #555; padding-right: 8px; text-align: right; }}
.fc-cell {{ width: 52px; height: 26px; text-align: center; font-size: .72rem; font-weight: 600;
            border-radius: 2px; }}
.fc-flag {{ font-size: .75rem; font-weight: 600; padding-left: 8px; white-space: nowrap; }}
.fc-legend {{ margin-top: .75rem; font-size: .8rem; }}
.fc-legend-title {{ font-weight: 600; margin-bottom: .25rem; }}
.fc-key {{ display: inline-flex; align-items: center; gap: 6px; margin: 0 14px 6px 0; }}
.fc-swatch {{ display: inline-block; width: 26px; height: 14px; border: 1px solid; border-radius: 2px; }}
</style>
<div class="fc-wrap">
  <div class="fc-title">{esc(title)}</div>
  <div class="fc-scroll"><table class="fc-table">
    <thead><tr><th></th>{head}<th></th></tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table></div>
  <div class="fc-legend"><div class="fc-legend-title">{esc(legend_title)}</div>
    <div>{''.join(legend)}</div><div>{flag_keys}</div></div>
</div>"""
