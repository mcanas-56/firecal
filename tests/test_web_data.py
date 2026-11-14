"""The page data is built from our pipeline (US-01 cleaning, US-02 harmonization, US-05 season)."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

from src import web_data


def write_year(folder: Path, area: str, year: int, *, peak: int, lat: float, lon: float,
               sensors=('modis', 'viirs-snpp'), extra_rows: int = 0, day: int = 15) -> None:
    """One yearly file per sensor. One fire on `day` of every month, 20 more in the peak
    month (spread over separate grid cells), plus a low-confidence row on 3 March that
    must be dropped."""
    meta = {'modis': ('MODIS', 'Aqua', '80', 'l-skip'), 'viirs-snpp': ('VIIRS', 'N', 'n', 'l')}
    for sensor in sensors:
        instrument, satellite, conf, low = meta[sensor]
        rows = []
        for m in range(1, 13):
            for k in range(1 + (20 if m == peak else 0) + extra_rows):
                rows.append(dict(latitude=lat + k * 0.2, longitude=lon, acq_date=f'{year}-{m:02d}-{day:02d}',
                                 acq_time='1330', satellite=satellite, instrument=instrument,
                                 confidence=conf, frp=10.0 + k, type=0))
        rows.append(dict(latitude=lat, longitude=lon, acq_date=f'{year}-03-03', acq_time='1330',
                         satellite=satellite, instrument=instrument,
                         confidence='l' if sensor != 'modis' else '5', frp=99.0, type=0))
        pd.DataFrame(rows).to_csv(folder / f'{sensor}_{year}_{area}.csv', index=False)


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        write_year(cls.data, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
        write_year(cls.data, 'Argentina', 2022, peak=9, lat=-35.0, lon=-60.0, day=16)
        # 2011: MODIS only, so the daily view falls back to MODIS for that year
        write_year(cls.data, 'Canada', 2011, peak=7, lat=55.0, lon=-110.0, sensors=('modis',))
        web_data.build(cls.data, verbose=False)
        out = web_data.web_dir(cls.data)
        cls.archive = json.loads((out / 'archive.json').read_text())
        cls.monthly = json.loads((out / 'monthly.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_archive_format_and_counts(self):
        day = self.archive['2022-07-15']['Canada']
        self.assertEqual(set(day), {'total', 'frp', 'points'})
        self.assertEqual(day['total'], 21)                  # every VIIRS detection that day
        self.assertEqual(len(day['points'][0]), 3)          # [lat, lon, frp]
        self.assertAlmostEqual(day['frp'], sum(10.0 + k for k in range(21)))

    def test_cleaning_drops_low_confidence(self):
        # 3 March only has low-confidence rows, so nothing is left in either area: a gap
        self.assertEqual(self.archive['2022-03-03'], {})
        self.assertEqual(self.archive['2022-03-15']['Canada']['total'], 1)

    def test_covered_days_are_zero_and_every_day_is_present(self):
        days_2022 = [d for d in self.archive if d.startswith('2022')]
        self.assertEqual(len(days_2022), 365)
        self.assertEqual(self.archive['2022-07-15']['Argentina'], {'total': 0, 'frp': 0.0, 'points': []})
        self.assertEqual(self.archive['2022-07-16']['Canada'], {'total': 0, 'frp': 0.0, 'points': []})

    def test_uncovered_area_year_is_absent(self):
        self.assertNotIn('Argentina', self.archive['2011-07-15'])   # no 2011 file for Argentina

    def test_daily_view_prefers_viirs_and_falls_back_to_modis(self):
        sensors = self.monthly['areas']['Canada']['daily_sensor']
        self.assertEqual(sensors, {'2011': 'MODIS', '2022': 'VIIRS S-NPP'})

    def test_monthly_has_harmonized_record_fit_and_season(self):
        canada = self.monthly['areas']['Canada']
        jul = next(m for m in canada['months'] if m['year'] == 2022 and m['month'] == 7)
        self.assertEqual(jul['viirs'], 21)
        self.assertEqual(jul['harmonized'], 21)
        self.assertEqual(jul['source'], 'viirs')
        modis_only = next(m for m in canada['months'] if m['year'] == 2011 and m['month'] == 7)
        self.assertEqual(modis_only['source'], 'modis_scaled')
        self.assertIsNone(modis_only['viirs'])
        self.assertAlmostEqual(canada['fit']['factor'], 1.0, places=3)
        self.assertEqual(canada['season']['peak'], 7)
        self.assertEqual(self.monthly['areas']['Argentina']['season']['peak'], 9)

    def test_json_has_no_nan(self):
        text = (web_data.web_dir(self.data) / 'monthly.json').read_text()
        self.assertNotIn('NaN', text)

    def test_writes_the_us02_table_too(self):
        table = pd.read_csv(self.data / 'processed' / 'harmonized_monthly.csv')
        self.assertEqual(set(table['area']), {'Canada', 'Argentina'})


class SamplingTests(unittest.TestCase):
    def test_at_most_60_points_per_day_but_full_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_year(folder, 'Canada', 2022, peak=7, lat=40.0, lon=-110.0, extra_rows=100)
            web_data.build(folder, verbose=False)
            day = json.loads((web_data.web_dir(folder) / 'archive.json').read_text())['2022-07-15']['Canada']
        self.assertEqual(day['total'], 121)
        self.assertEqual(len(day['points']), web_data.POINTS_PER_DAY)


class GapTests(unittest.TestCase):
    def test_day_with_nothing_in_any_area_is_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_year(folder, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
            write_year(folder, 'Argentina', 2022, peak=9, lat=-35.0, lon=-60.0)
            web_data.build(folder, verbose=False)
            out = web_data.web_dir(folder)
            archive = json.loads((out / 'archive.json').read_text())
            gaps = json.loads((out / 'monthly.json').read_text())['daily_gaps']['2022']
        # fixtures only have fires on the 15th, so other days are empty in both areas
        self.assertIn('2022-07-16', gaps)
        self.assertNotIn('2022-07-15', gaps)
        self.assertEqual(archive['2022-07-16'], {})
        self.assertEqual(archive['2022-07-15']['Canada']['total'], 21)

    def test_one_area_alone_never_counts_as_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_year(folder, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
            web_data.build(folder, verbose=False)
            archive = json.loads((web_data.web_dir(folder) / 'archive.json').read_text())
        self.assertEqual(archive['2022-07-16']['Canada']['total'], 0)


class EnsureTests(unittest.TestCase):
    def test_no_data_then_built_then_cached_then_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(web_data.ensure(folder, verbose=False), 'no_data')
            write_year(folder, 'Canada', 2022, peak=7, lat=55.0, lon=-110.0)
            self.assertEqual(web_data.ensure(folder, verbose=False), 'built')
            self.assertEqual(web_data.ensure(folder, verbose=False), 'cached')
            future = time.time() + 60
            os.utime(folder / 'modis_2022_Canada.csv', (future, future))
            self.assertEqual(web_data.ensure(folder, verbose=False), 'built')


if __name__ == '__main__':
    unittest.main()
