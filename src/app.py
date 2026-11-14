"""FireCal app shell (US-09). Start it with:  streamlit run src/app.py

Layout follows the T-03 wireframe, top to bottom: title, controls, season summary,
calendar, legend, hotspot map. Sections still to be built show a labelled placeholder
with the task that fills them, so each task plugs into its own slot.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # so `from src...` works however Streamlit is started
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.app_data import data_dir, load_or_build_monthly, signature  # noqa: E402
from src.calendar_view import calendar_html, sample_monthly  # noqa: E402
from src.season_summary import render_season_summary  # noqa: E402

DEFAULT_AREA = 'Canada'


@st.cache_data(show_spinner=False)
def get_monthly(folder: str, _sig: tuple) -> tuple[pd.DataFrame | None, str]:
    # _sig is part of the cache key: new or changed CSVs trigger a reload / rebuild.
    return load_or_build_monthly(Path(folder))


st.set_page_config(page_title='FireCal', page_icon='🔥', layout='wide')
st.title('FireCal')
st.write('Harmonized burning-activity calendar from NASA FIRMS MODIS + VIIRS hotspots.')

folder = data_dir()
with st.spinner('Preparing the harmonized monthly record (first run takes a few seconds)...'):
    monthly, status = get_monthly(str(folder), signature(folder))

if monthly is None:
    st.warning('No FIRMS data found in `data/`. Download the practice set, then reload this page:')
    st.code('python3 scripts/get_data.py        # Windows: py -3 scripts\\get_data.py', language='bash')
    st.stop()

areas = sorted(monthly['area'].dropna().unique())
area = DEFAULT_AREA if DEFAULT_AREA in areas else areas[0]

# 2. Controls -------------------------------------------------------------------
st.caption(f'Area: **{area}** (area selection comes with US-03) · data view: harmonized '
           '(raw vs harmonized toggle comes with US-07) · CSV export comes with US-08')

# 3. Season summary (US-05) ------------------------------------------------------
# Start the summary's own area picker on the same area as the rest of the page.
st.session_state.setdefault('season_area', area)
render_season_summary(monthly)

# 4-5. Calendar and legend -----------------------------------------------------------
# US-04a: the agreed layout drawn with SAMPLE values. US-04 swaps in the real record for
# the selected area: calendar_html(monthly[monthly.area == area], ...).
st.subheader(f'Monthly fire activity: {area}')
st.html(calendar_html(sample_monthly(area), flags={2023: 'high', 2020: 'low'},
                      title='Monthly burning activity, harmonized fire cell-days (sample values)'))
st.caption('Sample values to agree the layout (US-04a); the real calendar comes with US-04. '
           'Hover a cell for its value. Colours step on a log scale (T-03 palette); '
           'unusual-year outlines are placeholders for US-06.')

d = monthly[monthly['area'] == area].copy()
with st.expander(f'Real monthly data for {area} (preview until US-04)'):
    d['month_start'] = pd.to_datetime(dict(year=d['year'], month=d['month'], day=1))
    chart = d.set_index('month_start')[['harmonized']].rename(columns={'harmonized': 'Fire cell-days (harmonized)'})
    st.bar_chart(chart, height=260)
    factor = d['factor'].dropna()
    fit_note = (f'VIIRS ≈ {factor.iloc[0]:.2f} × MODIS for {area}. ' if len(factor) else '')
    st.caption(f'{fit_note}Method: docs/harmonization.md.')

# 6. Hotspot map (US-10) ---------------------------------------------------------------
st.subheader('Hotspot map')
st.info('Coming with US-10.')

years = f"{int(monthly['year'].min())}–{int(monthly['year'].max())}"
st.caption(f'Data: NASA FIRMS, {", ".join(areas)}, {years}. '
           + ('Harmonized record rebuilt from data/ just now.' if status == 'built'
              else 'Using data/processed/harmonized_monthly.csv.'))
