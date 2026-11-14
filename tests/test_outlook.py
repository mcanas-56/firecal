import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.harmonize import harmonize_cells
from src.outlook import LABEL, MAX_CELLS, MIN_P, build_outlook, write_outlook


def synthetic_record(seed=5, n_cells=60):
    """2012-2023 daily cell table for two areas: seasonal fires that persist month to month,
    seen by both sensors, plus a VIIRS outage (MODIS only) on 5 July 2023."""
    rng = np.random.default_rng(seed)
    rows = []
    for area, peak, ci0 in (('Canada', 7, 550), ('Argentina', 8, -350)):
        for c in range(n_cells):
            prev = False
            for year in range(2012, 2024):
                for month in range(1, 13):
                    season = 0.5 if abs(month - peak) <= 1 else 0.05
                    burned = rng.random() < (0.6 if prev else season * (0.3 + c / n_cells))
                    if burned:
                        day = pd.Timestamp(year, month, 10)
                        for sensor in ('viirs', 'modis'):
                            rows.append(dict(area=area, sensor=sensor, date=day, ci=ci0 + c // 8, cj=-1100 + c % 8,
                                             detections=2, night=0, frp_max=9.0, frp_sum=18.0))
                    prev = burned
        rows.append(dict(area=area, sensor='modis', date=pd.Timestamp(2023, 7, 5), ci=ci0, cj=-1100,
                         detections=1, night=0, frp_max=5.0, frp_sum=5.0))
    cells = pd.DataFrame(rows)
    cells['area'] = cells['area'].astype('string')
    cells['sensor'] = cells['sensor'].astype('string')
    periods = pd.period_range('2012-01', '2023-12', freq='M')
    coverage = pd.concat([pd.DataFrame({'area': a, 'sensor': s, 'period': periods})
                          for a in ('Canada', 'Argentina') for s in ('modis', 'viirs')], ignore_index=True)
    return cells, coverage


class BuildOutlookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cells, coverage = synthetic_record()
        monthly, _ = harmonize_cells(cells, coverage)
        cls.data = build_outlook(cells, coverage, monthly)

    def test_top_level(self):
        d = self.data
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['label'], LABEL)
        self.assertEqual((d['data_end'], d['forecast_month']), ('2023-12', '2024-01'))
        self.assertEqual(set(d['areas']), {'Canada', 'Argentina'})
        json.dumps(d, allow_nan=False)   # valid JSON, no NaN

    def test_forecast_map_and_monthly(self):
        f = self.data['areas']['Canada']['forecast']
        self.assertEqual(f['month'], '2024-01')
        chances = [c[2] for c in f['cells']]
        self.assertTrue(all(MIN_P <= p <= 1 for p in chances))
        self.assertEqual(chances, sorted(chances, reverse=True))
        self.assertLessEqual(len(chances), MAX_CELLS)
        mo = f['monthly']
        self.assertLessEqual(mo['low'], mo['normal'])
        self.assertLessEqual(mo['normal'], mo['high'])
        self.assertIn(mo['method'], ('nowcast', 'climatology'))

    def test_backtests_cover_every_test_month_and_flag_gaps(self):
        bt = self.data['areas']['Canada']['backtest']
        self.assertEqual(len(bt), 24)
        self.assertEqual(bt['2023-07']['viirs_gap_days'], 1)       # shown though not scored
        self.assertEqual(bt['2023-06']['viirs_gap_days'], 0)
        for b in bt.values():
            self.assertGreaterEqual(b['burned_cells'], b['new_area_fires'])
            if b['on_map_share'] is not None:
                self.assertTrue(0 <= b['on_map_share'] <= 1)

    def test_skill_and_climatology(self):
        a = self.data['areas']['Argentina']
        self.assertEqual(set(a['skill']), {'cell', 'monthly', 'timing'})
        self.assertIn('ship', a['skill']['cell'])
        self.assertEqual([c['month'] for c in a['climatology']], list(range(1, 13)))
        self.assertIn(a['skill']['timing']['peak'], (7, 8, 9))   # the synthetic season, Jul-Sep


class WriteOutlookTests(unittest.TestCase):
    def test_short_record_is_unavailable_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [dict(latitude=55.05, longitude=-110.05, acq_date=f'2022-{m:02d}-15', instrument=i,
                         satellite=s, confidence=c, type=0, frp=3.0)
                    for m in range(1, 13) for i, s, c in (('MODIS', 'Aqua', '80'), ('VIIRS', 'N', 'n'))]
            paths = []
            for sensor, inst in (('modis', 'MODIS'), ('viirs-snpp', 'VIIRS')):
                path = tmp / f'{sensor}_2022_Canada.csv'
                pd.DataFrame([r for r in rows if r['instrument'] == inst]).to_csv(path, index=False)
                paths.append(path)
            out = tmp / 'web' / 'outlook.json'
            data = write_outlook(paths, out, tmp / 'cells', verbose=False)
            self.assertEqual(data['status'], 'unavailable')
            self.assertIn('2012-2023', data['reason'])
            self.assertEqual(json.loads(out.read_text())['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
