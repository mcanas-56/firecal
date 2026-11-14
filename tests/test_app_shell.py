import os
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.app_data import load_or_build_monthly

APP = Path(__file__).resolve().parents[1] / 'src' / 'app.py'


def write_firms(folder: Path, area: str = 'Canada', year: int = 2022) -> None:
    """Two tiny FIRMS-shaped files (MODIS Aqua + VIIRS Suomi-NPP), one fire a month."""
    for sensor, instrument, satellite, conf in [('modis', 'MODIS', 'Aqua', '80'),
                                                ('viirs-snpp', 'VIIRS', 'N', 'n')]:
        rows = [dict(latitude=55.0, longitude=-110.0, acq_date=f'{year}-{m:02d}-15', acq_time='1330',
                     satellite=satellite, instrument=instrument, confidence=conf, frp=10.0, type=0)
                for m in range(1, 13)]
        pd.DataFrame(rows).to_csv(folder / f'{sensor}_{year}_{area}.csv', index=False)


class LoadOrBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        self.out = self.data / 'processed' / 'harmonized_monthly.csv'

    def test_no_csv_files_means_no_data(self):
        monthly, status = load_or_build_monthly(self.data, self.out)
        self.assertIsNone(monthly)
        self.assertEqual(status, 'no_data')

    def test_builds_when_missing_then_reuses(self):
        write_firms(self.data)
        monthly, status = load_or_build_monthly(self.data, self.out)
        self.assertEqual(status, 'built')
        self.assertTrue(self.out.exists())
        self.assertEqual(len(monthly), 12)
        self.assertIn('harmonized', monthly.columns)

        _, status = load_or_build_monthly(self.data, self.out)
        self.assertEqual(status, 'cached')

    def test_rebuilds_when_a_csv_is_newer(self):
        write_firms(self.data)
        load_or_build_monthly(self.data, self.out)
        future = time.time() + 60
        os.utime(self.data / 'modis_2022_Canada.csv', (future, future))
        _, status = load_or_build_monthly(self.data, self.out)
        self.assertEqual(status, 'built')


class AppShellTests(unittest.TestCase):
    def run_app(self, data_dir: Path) -> AppTest:
        old = os.environ.get('FIRECAL_DATA_DIR')
        os.environ['FIRECAL_DATA_DIR'] = str(data_dir)
        try:
            return AppTest.from_file(str(APP), default_timeout=60).run()
        finally:
            if old is None:
                os.environ.pop('FIRECAL_DATA_DIR')
            else:
                os.environ['FIRECAL_DATA_DIR'] = old

    def test_without_data_shows_download_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            at = self.run_app(Path(tmp))
        self.assertEqual([e.message for e in at.exception], [])
        self.assertTrue(any('get_data.py' in c.value for c in at.code))

    def test_with_data_shows_canada_placeholder_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_firms(Path(tmp))
            at = self.run_app(Path(tmp))
        self.assertEqual([e.message for e in at.exception], [])
        headers = [h.value for h in at.subheader]
        self.assertIn('Fire-season summary', headers)
        self.assertTrue(any('Canada' in h for h in headers), headers)

    def test_summary_starts_on_canada_even_when_another_area_sorts_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_firms(Path(tmp))
            write_firms(Path(tmp), area='Argentina')
            at = self.run_app(Path(tmp))
        self.assertEqual([e.message for e in at.exception], [])
        self.assertEqual(at.selectbox(key='season_area').value, 'Canada')


if __name__ == '__main__':
    unittest.main()
