"""FireCal entry point, with the US-05 summary ready for the US-09 app shell."""
from pathlib import Path

import pandas as pd
import streamlit as st

from src.season_summary import render_season_summary

st.set_page_config(page_title='FireCal', page_icon='🔥')
st.title('FireCal')
st.write('Fire-season calendar from NASA FIRMS MODIS + VIIRS hotspots.')
monthly_path = Path(__file__).resolve().parents[1] / 'data' / 'processed' / 'harmonized_monthly.csv'
if not monthly_path.exists():
    st.info('Build the harmonized monthly dataset to see the fire-season summary. '
            'From the repository root, run:')
    st.code('python -m src.harmonize "data/*.csv"', language='bash')
else:
    try:
        monthly = pd.read_csv(monthly_path)
        missing = {'area', 'year', 'month', 'harmonized'} - set(monthly.columns)
        if missing:
            raise ValueError('Missing required columns: ' + ', '.join(sorted(missing)))
        render_season_summary(monthly)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f'Cannot load monthly data: {exc}')
