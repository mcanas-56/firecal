import math
import unittest

import pandas as pd

from src.features import COLUMNS, build_features

PREDICTORS = ['lag1_cell_days', 'lag12_cell_days', 'past_rate_month', 'past_years', 'months_since_burn',
              'neigh_lag1_cell_days', 'neigh_burned_12m', 'neigh_past_rate_month']
A, B, C = (450, -751), (451, -751), (460, -760)   # B is next to A; C is far away


def cell(date, where, sensor='viirs', detections=1, night=0, frp=2.0):
    return dict(area='Canada', sensor=sensor, date=pd.Timestamp(date), ci=where[0], cj=where[1],
                detections=detections, night=night, frp_max=frp, frp_sum=frp * detections)


def coverage(years=(2012, 2013)):
    periods = pd.period_range(f'{years[0]}-01', f'{years[-1]}-12', freq='M')
    return pd.concat([pd.DataFrame({'area': 'Canada', 'sensor': s, 'period': periods})
                      for s in ('modis', 'viirs')], ignore_index=True)


def base_cells():
    return [cell('2012-01-05', A, detections=3, night=1, frp=6.0), cell('2012-01-06', A),
            cell('2013-01-10', A), cell('2012-02-03', B), cell('2013-06-01', C)]


def build(rows):
    table = build_features(pd.DataFrame(rows), coverage())
    return table.set_index(['ci', 'cj', 'year', 'month'])


class FeatureTableTests(unittest.TestCase):
    def setUp(self):
        self.t = build(base_cells())

    def at(self, where, year, month):
        return self.t.loc[(where[0], where[1], year, month)]

    def test_one_row_per_cell_and_month_with_spec_columns(self):
        table = build_features(pd.DataFrame(base_cells()), coverage())
        self.assertEqual(list(table.columns), COLUMNS)
        self.assertEqual(len(table), 3 * 24)

    def test_month_outcome_columns(self):
        jan = self.at(A, 2012, 1)
        self.assertEqual(int(jan.cell_days), 2)
        self.assertTrue(bool(jan.burned))
        self.assertEqual(int(jan.detections), 4)
        self.assertAlmostEqual(float(jan.frp_max), 6.0)
        self.assertAlmostEqual(float(jan.frp_mean), (18 + 2) / 4)
        self.assertAlmostEqual(float(jan.night_share), 0.25)
        self.assertTrue(math.isnan(self.at(A, 2012, 3).night_share))

    def test_lags_and_history(self):
        self.assertTrue(math.isnan(self.at(A, 2012, 1).lag1_cell_days))
        self.assertEqual(float(self.at(A, 2012, 2).lag1_cell_days), 2)
        jan13 = self.at(A, 2013, 1)
        self.assertEqual(float(jan13.lag12_cell_days), 2)
        self.assertEqual(float(jan13.past_rate_month), 1.0)
        self.assertEqual(int(jan13.past_years), 1)
        self.assertEqual(float(jan13.months_since_burn), 12)
        self.assertTrue(math.isnan(self.at(A, 2012, 1).past_rate_month))
        self.assertTrue(math.isnan(self.at(A, 2012, 1).months_since_burn))

    def test_neighbours(self):
        self.assertEqual(float(self.at(B, 2012, 2).neigh_lag1_cell_days), 2)   # A in January
        self.assertEqual(float(self.at(A, 2012, 3).neigh_lag1_cell_days), 1)   # B in February
        self.assertEqual(int(self.at(B, 2012, 2).neigh_burned_12m), 1)
        self.assertEqual(int(self.at(C, 2012, 2).neigh_burned_12m), 0)
        self.assertAlmostEqual(float(self.at(B, 2013, 1).neigh_past_rate_month), 1 / 8)

    def test_first_seen_year(self):
        self.assertEqual(int(self.at(A, 2012, 5).first_seen_year), 2012)
        self.assertEqual(int(self.at(C, 2012, 5).first_seen_year), 2013)

    def test_later_data_never_changes_earlier_predictors(self):
        more = base_cells() + [cell('2013-03-01', A), cell('2013-02-01', B), cell('2013-07-01', B)]
        changed = build(more)
        for col in PREDICTORS:
            before = self.t.xs(2012, level='year')[col]
            after = changed.xs(2012, level='year')[col]
            pd.testing.assert_series_equal(before, after, check_names=False)
        # and a month's own fires never feed its own predictors
        march = changed.loc[(A[0], A[1], 2013, 3)]
        self.assertEqual(float(march.past_rate_month), 0.0)

    def test_viirs_gap_days_are_flagged(self):
        rows = base_cells() + [cell('2012-08-05', A, sensor='modis')]   # MODIS sees fire, VIIRS nothing
        t = build(rows)
        self.assertEqual(int(t.loc[(A[0], A[1], 2012, 8)].viirs_gap_days), 1)
        self.assertEqual(int(t.loc[(A[0], A[1], 2012, 9)].viirs_gap_days), 0)


if __name__ == '__main__':
    unittest.main()
