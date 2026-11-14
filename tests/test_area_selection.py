"""US-03: one area control drives the whole page."""
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.calendar_view import sample_monthly

APP = Path(__file__).resolve().parents[1] / 'src' / 'app.py'


def write_area(folder: Path, area: str, peak_month: int, lat: float, lon: float) -> None:
    """One year of MODIS Aqua + VIIRS S-NPP files with a clear peak month.

    Every month has one fire cell-day; the peak month has 20 extra cells.
    """
    for sensor, instrument, satellite, conf in [('modis', 'MODIS', 'Aqua', '80'),
                                                ('viirs-snpp', 'VIIRS', 'N', 'n')]:
        rows = []
        for m in range(1, 13):
            extra = 20 if m == peak_month else 0
            for k in range(1 + extra):
                rows.append(dict(latitude=lat + k * 0.2, longitude=lon, acq_date=f'2022-{m:02d}-15',
                                 acq_time='1330', satellite=satellite, instrument=instrument,
                                 confidence=conf, frp=10.0, type=0))
        pd.DataFrame(rows).to_csv(folder / f'{sensor}_2022_{area}.csv', index=False)


@contextmanager
def app_with_two_areas():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        write_area(folder, 'Canada', peak_month=7, lat=55.0, lon=-110.0)
        write_area(folder, 'Argentina', peak_month=9, lat=-35.0, lon=-60.0)
        old = os.environ.get('FIRECAL_DATA_DIR')
        os.environ['FIRECAL_DATA_DIR'] = str(folder)
        try:
            yield AppTest.from_file(str(APP), default_timeout=60)
        finally:
            if old is None:
                os.environ.pop('FIRECAL_DATA_DIR')
            else:
                os.environ['FIRECAL_DATA_DIR'] = old


def peak(at: AppTest) -> str:
    return next(m.value for m in at.metric if m.label == 'Peak')


class AreaSelectionTests(unittest.TestCase):
    def test_starts_on_canada_with_canada_first(self):
        with app_with_two_areas() as at:
            at.run()
            self.assertEqual([e.message for e in at.exception], [])
            control = at.radio(key='area')
            self.assertEqual(control.value, 'Canada')
            self.assertEqual(list(control.options), ['Canada', 'Argentina'])
            self.assertEqual(peak(at), 'July')

    def test_switching_area_updates_every_section(self):
        with app_with_two_areas() as at:
            at.run()
            at.radio(key='area').set_value('Argentina').run()
            self.assertEqual([e.message for e in at.exception], [])
            self.assertEqual(peak(at), 'September')
            headers = [h.value for h in at.subheader]
            self.assertTrue(any('Argentina' in h for h in headers), headers)
            self.assertFalse(any('Canada' in h for h in headers), headers)
            self.assertEqual(at.query_params.get('area'), 'Argentina')

    def test_link_with_area_opens_that_area(self):
        with app_with_two_areas() as at:
            at.query_params['area'] = 'Argentina'
            at.run()
            self.assertEqual(at.radio(key='area').value, 'Argentina')
            self.assertEqual(peak(at), 'September')

    def test_unknown_area_in_link_falls_back_to_canada(self):
        with app_with_two_areas() as at:
            at.query_params['area'] = 'Atlantis'
            at.run()
            self.assertEqual([e.message for e in at.exception], [])
            self.assertEqual(at.radio(key='area').value, 'Canada')

    def test_summary_has_no_second_area_picker(self):
        with app_with_two_areas() as at:
            at.run()
            self.assertEqual(len(at.selectbox), 0)


class SummaryWithAreaTests(unittest.TestCase):
    def test_render_with_area_skips_its_own_picker(self):
        script = """
import pandas as pd
from src.season_summary import render_season_summary
rows = [dict(area=a, year=2022, month=m, harmonized=(50 if m == p else 1))
        for a, p in [('Canada', 7), ('Argentina', 9)] for m in range(1, 13)]
render_season_summary(pd.DataFrame(rows), area='Argentina')
"""
        at = AppTest.from_string(script).run()
        self.assertEqual(len(at.selectbox), 0)
        self.assertEqual(peak(at), 'September')


class SampleByAreaTests(unittest.TestCase):
    def test_argentina_sample_peaks_later_than_canada(self):
        def peak_month(area):
            s = sample_monthly(area)
            return int(s.loc[s['harmonized'].idxmax(), 'month'])
        self.assertEqual(peak_month('Canada'), 7)
        self.assertIn(peak_month('Argentina'), (8, 9))


if __name__ == '__main__':
    unittest.main()
