import os
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

from src.app_data import load_or_build_monthly


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


if __name__ == '__main__':
    unittest.main()
