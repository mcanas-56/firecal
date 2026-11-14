import math
import unittest

import numpy as np
import pandas as pd

from src.predict import (_month_gap, _rows, auc, brier, cell_models, fit_logistic, log_loss,
                         monthly_models, predict_logistic, reliability, season_timing)


class MetricTests(unittest.TestCase):
    def test_auc(self):
        y = np.array([0, 0, 1, 1])
        self.assertEqual(auc(y, [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertEqual(auc(y, [0.9, 0.8, 0.2, 0.1]), 0.0)
        self.assertEqual(auc(y, [0.5, 0.5, 0.5, 0.5]), 0.5)
        self.assertTrue(math.isnan(auc([1, 1], [0.2, 0.3])))

    def test_brier_and_log_loss(self):
        self.assertAlmostEqual(brier([0, 1], [0.2, 0.6]), (0.04 + 0.16) / 2)
        self.assertAlmostEqual(log_loss([1], [0.5]), math.log(2))

    def test_reliability_bands(self):
        rows = reliability([0, 1, 0, 1], [0.005, 0.015, 0.6, 0.65])
        self.assertEqual([(r['low'], r['rows']) for r in rows], [(0, 1), (0.01, 1), (0.5, 2)])
        self.assertAlmostEqual(rows[2]['observed'], 0.5)


class LogisticTests(unittest.TestCase):
    def test_recovers_known_coefficients(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(40_000, 2))
        y = rng.random(40_000) < 1 / (1 + np.exp(-(-1 + 2 * X[:, 0] - 0.5 * X[:, 1])))
        model = fit_logistic(X, y, l2=0.0, chunk=7_000)
        w = model['w'][1:] / model['scale']                  # back to raw units
        intercept = model['w'][0] - (w * model['mean']).sum()
        self.assertAlmostEqual(intercept, -1, delta=0.08)
        self.assertAlmostEqual(w[0], 2, delta=0.08)
        self.assertAlmostEqual(w[1], -0.5, delta=0.08)
        p = predict_logistic(model, X)
        self.assertTrue(((p > 0) & (p < 1)).all())

    def test_strong_penalty_shrinks_to_the_base_rate(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(5_000, 1))
        y = X[:, 0] > 0
        p = predict_logistic(fit_logistic(X, y, l2=1e9), X)
        self.assertLess(p.max() - p.min(), 0.01)


def synthetic_cells(n_cells=150, seed=2):
    """Cells whose fires persist month to month; past_rate_month is pure noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cells):
        prev = 0
        for year in range(2012, 2024):
            for month in range(1, 13):
                burned = rng.random() < (0.6 if prev else 0.05)
                rows.append(dict(area='Canada', ci=c, cj=0, year=year, month=month, burned=burned,
                                 cell_days=int(burned), lag1_cell_days=float(prev), lag12_cell_days=0.0,
                                 past_rate_month=rng.random() * 0.1, months_since_burn=np.nan,
                                 neigh_lag1_cell_days=0.0, neigh_burned_12m=0, neigh_past_rate_month=0.0,
                                 viirs_gap_days=0, first_seen_year=2012))
                prev = int(burned)
    return pd.DataFrame(rows)


class CellModelTests(unittest.TestCase):
    def test_model_beats_an_uninformative_baseline_and_ships(self):
        results, preds = cell_models(synthetic_cells(), l2_choices=(1.0,))
        r = results['Canada']
        self.assertGreater(r['model']['auc'], 0.75)
        self.assertLess(abs(r['baseline']['auc'] - 0.5), 0.1)
        self.assertTrue(r['ship'])
        self.assertEqual(set(preds['year']), {2022, 2023})
        self.assertGreater(r['coefficients']['log_lag1'], 0)

    def test_scored_rows_skip_gap_months_and_cells_seen_later(self):
        df = synthetic_cells(n_cells=3)
        df.loc[(df['year'] == 2022) & (df['month'] == 7), 'viirs_gap_days'] = 5
        df.loc[df['ci'] == 2, 'first_seen_year'] = 2023
        rows = _rows(df, (2022, 2023), 2021)
        self.assertFalse(((rows['year'] == 2022) & (rows['month'] == 7)).any())
        self.assertNotIn(2, set(rows['ci']))
        self.assertEqual(int(_rows(df, (2012, 2019), 2019)['year'].min()), 2013)  # first year has no history


def synthetic_monthly(seed=3, phi=0.8):
    """Seasonal monthly cell-days with persistent (AR(1)) anomalies."""
    rng = np.random.default_rng(seed)
    season = 100 + 900 * np.exp(-((np.arange(1, 13) - 7) ** 2) / 4)
    rows, a = [], 0.0
    for year in range(2012, 2024):
        for month in range(1, 13):
            a = phi * a + rng.normal(scale=0.3)
            rows.append(dict(area='Canada', year=year, month=month,
                             harmonized=season[month - 1] * np.exp(a), viirs_gap_days=0))
    return pd.DataFrame(rows)


class MonthlyAndTimingTests(unittest.TestCase):
    def test_nowcast_beats_climatology_when_anomalies_persist(self):
        r = monthly_models(synthetic_monthly())['Canada']
        self.assertGreater(r['beta'], 0.5)
        self.assertLess(r['nowcast']['mae_log'], r['baseline']['mae_log'])
        self.assertTrue(r['ship'])

    def test_nowcast_does_not_ship_without_persistence(self):
        r = monthly_models(synthetic_monthly(seed=4, phi=0.0))['Canada']
        self.assertLess(abs(r['beta']), 0.3)

    def test_season_timing(self):
        self.assertEqual(_month_gap(12, 1), 1)
        self.assertEqual(_month_gap(3, 9), 6)
        r = season_timing(synthetic_monthly())['Canada']
        self.assertEqual(r['climatology_peak'], 7)
        self.assertEqual(set(r['test_peaks']), {2022, 2023})


if __name__ == '__main__':
    unittest.main()
