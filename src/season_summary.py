"""Fire-season estimates from US-02's harmonized monthly record (US-05)."""
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class SeasonSummary:
    area: str
    status: str
    years: tuple[int, ...] = ()
    start_month: int | None = None
    peak_month: int | None = None
    end_month: int | None = None
    season_months: tuple[int, ...] = ()
    threshold_fraction: float = 0.2


def summarize_season(monthly: pd.DataFrame, area: str, *,
                     threshold_fraction: float = 0.2) -> SeasonSummary:
    """Estimate the dominant season using complete years only.

    Mean harmonized activity by calendar month; earliest calendar month wins a
    peak tie. Walk backwards/forwards around that peak while activity >= the
    chosen fraction of the peak, wrapping December/January. Other disconnected
    peaks are excluded. All 12 active months are reported as January–December.
    Missing data is never filled with zero. Invalid values/duplicate keys raise.
    """
    if not math.isfinite(threshold_fraction) or not 0 < threshold_fraction <= 1:
        raise ValueError('threshold_fraction must be in (0, 1]')
    missing = {'area', 'year', 'month', 'harmonized'} - set(monthly.columns)
    if missing:
        raise ValueError('Missing required columns: ' + ', '.join(sorted(missing)))
    d = monthly.loc[monthly['area'].eq(area), ['year', 'month', 'harmonized']].copy()
    if d.empty:
        return SeasonSummary(area, 'no_data', threshold_fraction=threshold_fraction)
    for key in ('year', 'month'):
        d[key] = pd.to_numeric(d[key], errors='raise')
        if d[key].isna().any() or not d[key].map(lambda x: math.isfinite(x) and x == int(x)).all():
            raise ValueError(f'{key} must contain finite integers')
        d[key] = d[key].astype(int)
    if not d['month'].between(1, 12).all():
        raise ValueError('month must be between 1 and 12')
    if d.duplicated(['year', 'month']).any():
        raise ValueError('Expected one row per area-year-month')
    d['harmonized'] = pd.to_numeric(d['harmonized'], errors='raise')
    values = d['harmonized'].dropna()
    if not values.map(lambda x: math.isfinite(x) and x >= 0).all():
        raise ValueError('harmonized must be nonnegative and finite, or missing')
    complete = d.groupby('year').filter(lambda g: len(g) == 12 and g['harmonized'].notna().all())
    years = tuple(sorted(complete['year'].unique().tolist()))
    if not years:
        return SeasonSummary(area, 'incomplete_data', threshold_fraction=threshold_fraction)
    profile = complete.groupby('month')['harmonized'].mean().reindex(range(1, 13))
    peak = int(profile.idxmax())
    if profile.max() == 0:
        return SeasonSummary(area, 'no_activity', years, threshold_fraction=threshold_fraction)
    active = profile.ge(float(profile.max()) * threshold_fraction)
    if active.all():
        return SeasonSummary(area, 'year_round', years, 1, peak, 12,
                             tuple(range(1, 13)), threshold_fraction)
    start = peak
    while active.loc[(start - 2) % 12 + 1]:
        start = (start - 2) % 12 + 1
    months = [start]
    while active.loc[months[-1] % 12 + 1]:
        months.append(months[-1] % 12 + 1)
    return SeasonSummary(area, 'ok', years, start, peak, months[-1], tuple(months), threshold_fraction)


def render_season_summary(monthly: pd.DataFrame) -> None:
    """Streamlit area selection and summary, reusable by the future app shell."""
    import calendar
    import streamlit as st

    st.subheader('Fire-season summary')
    areas = sorted(monthly['area'].dropna().unique())
    if not areas:
        st.info('No area data available.')
        return
    area = st.selectbox('Area', areas, key='season_area')
    try:
        summary = summarize_season(monthly, area)
    except ValueError as exc:
        st.error(f'Cannot calculate a season: {exc}')
        return
    messages = {
        'no_data': 'No data available for this area.',
        'incomplete_data': 'No complete year available. Missing months are not treated as zero activity.',
        'no_activity': 'No fire activity recorded in the complete years; no season can be estimated.',
    }
    if summary.status in messages:
        st.info(messages[summary.status])
        return
    for column, label, month in zip(st.columns(3), ('Start', 'Peak', 'End'),
                                     (summary.start_month, summary.peak_month, summary.end_month)):
        column.metric(label, calendar.month_name[month])
    if summary.status == 'year_round':
        st.info('Activity meets the threshold year-round; there is no distinct seasonal start or end.')
    elif summary.start_month > summary.end_month:
        st.caption('The season crosses December–January.')
    st.caption('Estimated dominant season: consecutive months around the peak with at least 20% '
               'of peak mean monthly harmonized activity. Uses complete years only: '
               + ', '.join(map(str, summary.years)) + '. Tied peaks use the earliest calendar month. '
               'This is a descriptive estimate, not a forecast or an official fire-season declaration.')
