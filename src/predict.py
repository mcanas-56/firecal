"""Fire outlook models and their evaluation (US-16).

Three outlooks, each judged against a plain climatology baseline on the test years:

1. Cell burn probability: the chance that a 0.1 deg cell has at least one fire
   cell-day next month. Baseline: the share of earlier years the cell burned in that
   calendar month (past_rate_month). Model: logistic regression per area on the
   US-15 predictors (src/features.py), all from months before the one predicted.
2. Monthly area outlook: harmonized fire cell-days per area and month. Baseline: the
   mean of that calendar month over the fitting years. Nowcast: the baseline scaled
   by how far last month was above or below its own normal.
3. Season timing: the peak month of the climatology vs each test year's peak.

Years: fit on 2012-2019, choose settings on 2020-2021, then refit on 2012-2021 and
test once on 2022-2023. A model gets ship=True only if it beats the baseline on the
test years; otherwise the app shows the baseline (the US-16 rule).

For the cell model, months with VIIRS gap days are left out of fitting and scoring
(raw VIIRS counts are low there for a technical reason); the monthly outlook uses the
harmonized value, which already fills those days. For honest scoring, cells must have been seen before the
period that is scored (see first_seen_year in src/features.py).

Run with:  python -m src.predict    (needs data/processed/cell_month.parquet from
python -m src.features and data/processed/harmonized_monthly.csv from src.harmonize)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.harmonize import DEFAULT_OUT as MONTHLY_CSV
from src.harmonize import ROOT
from src.features import DEFAULT_OUT as FEATURES_PARQUET

OUT_DIR = ROOT / 'data' / 'processed' / 'prediction'
TRAIN, TUNE, TEST = (2012, 2019), (2020, 2021), (2022, 2023)
L2_CHOICES = (0.1, 10.0, 1000.0)
RELIABILITY_EDGES = (0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0)
FEATURE_NAMES = (['past_rate', 'sqrt_past_rate', 'log_lag1', 'log_lag12', 'log_neigh_lag1',
                  'neigh_burned_12m', 'neigh_past_rate', 'log_months_since_burn', 'never_burned']
                 + [f'month_{m}' for m in range(2, 13)])


# ---------------------------------------------------------------- metrics

def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Area under the ROC curve (Mann-Whitney, ties count half). NaN without both classes."""
    y = np.asarray(y, dtype=bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if not n_pos or not n_neg:
        return float('nan')
    ranks = pd.Series(np.asarray(p, dtype=float)).rank(method='average').to_numpy()
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(y: np.ndarray, p: np.ndarray, edges=RELIABILITY_EDGES) -> list[dict]:
    """Predicted vs observed burn rate per probability band (bands with rows only)."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    band = np.clip(np.searchsorted(edges, p, side='right') - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = band == b
        if m.any():
            rows.append(dict(low=edges[b], high=edges[b + 1], rows=int(m.sum()),
                             predicted=float(p[m].mean()), observed=float(y[m].mean())))
    return rows


def scores(y, p) -> dict:
    return dict(auc=auc(y, p), brier=brier(y, p), log_loss=log_loss(y, p),
                rows=int(len(y)), burn_rate=float(np.mean(y)) if len(y) else float('nan'))


# ---------------------------------------------------------------- logistic regression

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 30,
                 chunk: int = 400_000) -> dict:
    """L2-penalised logistic regression by Newton's method; standardises X itself.

    Returns {'mean', 'scale', 'w'} for predict_logistic; w[0] is the (unpenalised)
    intercept. Works in row chunks so millions of rows fit in memory.
    """
    X = np.asarray(X)  # kept as given (float32 is fine); each chunk is converted to float64
    y = np.asarray(y, dtype='float64')
    mean, scale = X.mean(axis=0, dtype='float64'), X.std(axis=0, dtype='float64')
    scale[scale == 0] = 1.0
    k = X.shape[1] + 1
    w = np.zeros(k)
    rate = np.clip(y.mean(), 1e-6, 1 - 1e-6)
    w[0] = np.log(rate / (1 - rate))
    penalty = np.full(k, l2)
    penalty[0] = 0.0

    def chunks():
        for s in range(0, len(y), chunk):
            yield (np.hstack([np.ones((len(y[s:s + chunk]), 1)),
                              (X[s:s + chunk].astype('float64') - mean) / scale]), y[s:s + chunk])

    def objective(w_):  # penalised negative log-likelihood
        total = 0.5 * (penalty * w_ * w_).sum()
        for Z, yy in chunks():
            z = np.clip(Z @ w_, -35, 35)
            total += (np.logaddexp(0, z) - yy * z).sum()
        return total

    current = objective(w)
    for _ in range(iters):
        grad, hess = penalty * w, np.diag(penalty)
        for Z, yy in chunks():
            p = _sigmoid(Z @ w)
            grad += Z.T @ (p - yy)
            hess += (Z * (p * (1 - p))[:, None]).T @ Z
        step = np.linalg.solve(hess + 1e-9 * np.eye(k), grad)
        t = 1.0
        while t > 1e-6:  # damped Newton: halve the step until the loss goes down
            trial = objective(w - t * step)
            if trial <= current:
                break
            t /= 2
        else:
            break
        w, improvement, current = w - t * step, current - trial, trial
        if np.max(np.abs(t * step)) < 1e-7 or improvement < 1e-10 * max(1.0, abs(current)):
            break
    return {'mean': mean, 'scale': scale, 'w': w}


def predict_logistic(model: dict, X: np.ndarray) -> np.ndarray:
    w = model['w'][1:] / model['scale']  # fold the standardisation into the weights
    return _sigmoid(model['w'][0] - (w * model['mean']).sum() + np.asarray(X) @ w)


# ---------------------------------------------------------------- cell burn probability

def design(df: pd.DataFrame) -> np.ndarray:
    """FEATURE_NAMES columns (float32) from the US-15 table, using only earlier months."""
    X = np.empty((len(df), len(FEATURE_NAMES)), dtype='float32')
    rate = df['past_rate_month'].fillna(0).to_numpy(dtype='float32')
    msb = df['months_since_burn'].to_numpy(dtype='float32')
    X[:, 0], X[:, 1] = rate, np.sqrt(rate)
    X[:, 2] = np.log1p(df['lag1_cell_days'].fillna(0).to_numpy(dtype='float32'))
    X[:, 3] = np.log1p(df['lag12_cell_days'].fillna(0).to_numpy(dtype='float32'))
    X[:, 4] = np.log1p(df['neigh_lag1_cell_days'].fillna(0).to_numpy(dtype='float32'))
    X[:, 5] = df['neigh_burned_12m'].to_numpy(dtype='float32') / 8
    X[:, 6] = df['neigh_past_rate_month'].fillna(0).to_numpy(dtype='float32')
    X[:, 7] = np.log1p(np.nan_to_num(msb, nan=0.0))
    X[:, 8] = np.isnan(msb)
    month = df['month'].to_numpy()
    for i, m in enumerate(range(2, 13), start=9):
        X[:, i] = month == m
    return X


def _rows(df: pd.DataFrame, years: tuple[int, int], seen_by: int) -> pd.DataFrame:
    """Scorable rows: in the years, after the first year of history, no VIIRS gap days,
    cell already seen by seen_by."""
    return df[df['year'].between(max(years[0], df['year'].min() + 1), years[1])
              & (df['viirs_gap_days'] == 0) & (df['first_seen_year'] <= seen_by)]


def cell_models(table: pd.DataFrame, train=TRAIN, tune=TUNE, test=TEST, l2_choices=L2_CHOICES):
    """Per area: pick L2 on tune, refit on train+tune, score baseline and model on test.

    Returns (results per area, test predictions DataFrame).
    """
    results, preds = {}, []
    for area, df in table.groupby('area', observed=True):
        fit, val = _rows(df, train, train[1]), _rows(df, tune, train[1])
        tuning = {}
        for l2 in l2_choices:
            m = fit_logistic(design(fit), fit['burned'].to_numpy(), l2=l2)
            tuning[l2] = log_loss(val['burned'].to_numpy(), predict_logistic(m, design(val)))
        best = min(tuning, key=tuning.get)
        full = _rows(df, (train[0], tune[1]), tune[1])
        model = fit_logistic(design(full), full['burned'].to_numpy(), l2=best)
        ev = _rows(df, test, tune[1])
        y = ev['burned'].to_numpy()
        p_base = ev['past_rate_month'].fillna(0).to_numpy(dtype='float64')
        p_model = predict_logistic(model, design(ev))
        base, mod = scores(y, p_base), scores(y, p_model)
        results[str(area)] = {
            'baseline': base, 'model': mod, 'l2': best,
            'tuning_log_loss': {str(k): v for k, v in tuning.items()},
            'ship': bool(mod['auc'] > base['auc'] and mod['brier'] < base['brier']),
            'reliability_model': reliability(y, p_model),
            'reliability_baseline': reliability(y, p_base),
            'coefficients': dict(zip(['intercept'] + FEATURE_NAMES, map(float, model['w']))),
            'cells_scored': int(ev[['ci', 'cj']].drop_duplicates().shape[0]),
        }
        preds.append(pd.DataFrame({'area': str(area), 'ci': ev['ci'].to_numpy(), 'cj': ev['cj'].to_numpy(),
                                   'year': ev['year'].to_numpy(), 'month': ev['month'].to_numpy(),
                                   'burned': y, 'p_baseline': p_base.astype('float32'),
                                   'p_model': p_model.astype('float32')}))
    return results, (pd.concat(preds, ignore_index=True) if preds else pd.DataFrame())


# ---------------------------------------------------------------- monthly area outlook

def climatology(monthly: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    """Per area and calendar month: mean, median, min and max harmonized cell-days."""
    m = monthly[monthly['year'].between(*years)].dropna(subset=['harmonized'])
    return (m.groupby(['area', 'month'])['harmonized']
            .agg(mean='mean', median='median', low='min', high='max', years='count').reset_index())


def _with_last_month(monthly: pd.DataFrame, clim: pd.DataFrame) -> pd.DataFrame:
    """Monthly rows with this month's and last month's normal and last month's value."""
    d = monthly.sort_values(['area', 'year', 'month']).copy()
    d['prev'] = d.groupby('area')['harmonized'].shift(1)
    d['prev_month'] = (d['month'] - 2) % 12 + 1
    norm = clim.set_index(['area', 'month'])['mean']
    d['norm'] = norm.reindex(pd.MultiIndex.from_frame(d[['area', 'month']])).to_numpy()
    d['prev_norm'] = norm.reindex(pd.MultiIndex.from_frame(d[['area', 'prev_month']])).to_numpy()
    return d.dropna(subset=['harmonized', 'prev', 'norm', 'prev_norm'])


def _anomaly(values, norm):
    return np.log1p(values) - np.log1p(norm)


def fit_persistence(d: pd.DataFrame) -> float:
    """beta in: this month's log anomaly = beta x last month's log anomaly (no intercept)."""
    x, y = _anomaly(d['prev'], d['prev_norm']).to_numpy(), _anomaly(d['harmonized'], d['norm']).to_numpy()
    return float((x * y).sum() / (x * x).sum()) if (x * x).sum() > 0 else 0.0


def nowcast(d: pd.DataFrame, beta: float) -> np.ndarray:
    return np.expm1(np.log1p(d['norm']) + beta * _anomaly(d['prev'], d['prev_norm'])).to_numpy()


def _monthly_errors(actual, predicted) -> dict:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    pos = actual > 0
    return dict(mae_log=float(np.mean(np.abs(np.log1p(predicted) - np.log1p(actual)))),
                median_abs_pct_error=float(np.median(np.abs(predicted[pos] - actual[pos]) / actual[pos]) * 100),
                months=int(len(actual)))


def monthly_models(monthly: pd.DataFrame, train=TRAIN, tune=TUNE, test=TEST) -> dict:
    """Per area: climatology baseline vs persistence nowcast on the test months.

    Uses the harmonized value, which already fills VIIRS gap days from MODIS, so gap
    months stay in (unlike the cell model, which uses raw VIIRS cell-days).
    """
    out = {}
    clim_fit = climatology(monthly, (train[0], tune[1]))
    beta_fit = {a: fit_persistence(g) for a, g in
                _with_last_month(monthly[monthly['year'].between(train[0], tune[1])], clim_fit).groupby('area')}
    ev_all = _with_last_month(monthly, clim_fit)
    for area, ev in ev_all[ev_all['year'].between(*test)].groupby('area'):
        beta = beta_fit.get(area, 0.0)
        base = _monthly_errors(ev['harmonized'], ev['norm'])
        now = _monthly_errors(ev['harmonized'], nowcast(ev, beta))
        c = clim_fit[clim_fit['area'] == area].set_index('month')
        inside = ev.apply(lambda r: c.loc[r['month'], 'low'] <= r['harmonized'] <= c.loc[r['month'], 'high'], axis=1)
        out[str(area)] = {'baseline': base, 'nowcast': now, 'beta': beta,
                          'ship': bool(now['mae_log'] < base['mae_log']),
                          'test_months_inside_range': float(inside.mean())}
    return out


# ---------------------------------------------------------------- season timing

def _month_gap(a: int, b: int) -> int:
    d = abs(a - b) % 12
    return min(d, 12 - d)


def season_timing(monthly: pd.DataFrame, fit_years=(TRAIN[0], TUNE[1]), test=TEST) -> dict:
    """Climatological peak month vs each test year's actual peak (months apart)."""
    clim = climatology(monthly, fit_years)
    out = {}
    for area, c in clim.groupby('area'):
        peak = int(c.loc[c['mean'].idxmax(), 'month'])
        m = monthly[(monthly['area'] == area) & monthly['year'].between(*test)].dropna(subset=['harmonized'])
        actual = {int(y): int(g.loc[g['harmonized'].idxmax(), 'month']) for y, g in m.groupby('year')}
        fit = monthly[(monthly['area'] == area) & monthly['year'].between(*fit_years)].dropna(subset=['harmonized'])
        yearly = [int(g.loc[g['harmonized'].idxmax(), 'month']) for _, g in fit.groupby('year')]
        out[str(area)] = {'climatology_peak': peak, 'test_peaks': actual,
                          'test_months_off': {y: _month_gap(peak, p) for y, p in actual.items()},
                          'fit_years_within_1_month': float(np.mean([_month_gap(peak, p) <= 1 for p in yearly]))}
    return out


# ---------------------------------------------------------------- command line

def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if np.isnan(obj) else round(float(obj), 6)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Fit and evaluate the fire outlook models (US-16).')
    parser.add_argument('--features', type=Path, default=FEATURES_PARQUET, help='US-15 cell-month table')
    parser.add_argument('--monthly', type=Path, default=MONTHLY_CSV, help='US-02 harmonized monthly table')
    parser.add_argument('--out-dir', type=Path, default=OUT_DIR, help='where results go')
    args = parser.parse_args(argv)
    for path, how in ((args.features, 'python -m src.features'), (args.monthly, 'python -m src.harmonize')):
        if not path.exists():
            parser.error(f'{path} not found; build it with: {how}')

    monthly = pd.read_csv(args.monthly)
    table = pd.read_parquet(args.features, columns=[
        'area', 'ci', 'cj', 'year', 'month', 'burned', 'lag1_cell_days', 'lag12_cell_days',
        'past_rate_month', 'months_since_burn', 'neigh_lag1_cell_days', 'neigh_burned_12m',
        'neigh_past_rate_month', 'viirs_gap_days', 'first_seen_year'])
    cells, preds = cell_models(table)
    del table
    report = {'years': {'train': TRAIN, 'tune': TUNE, 'test': TEST},
              'cell_burn_probability': cells,
              'monthly_outlook': monthly_models(monthly),
              'season_timing': season_timing(monthly)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'metrics.json').write_text(json.dumps(_jsonable(report), indent=2), encoding='utf-8')
    preds.to_parquet(args.out_dir / 'cell_test_predictions.parquet', index=False)
    clim = climatology(monthly, (TRAIN[0], TEST[1]))
    clim.to_csv(args.out_dir / 'monthly_climatology.csv', index=False)

    print(f'Fit {TRAIN[0]}-{TRAIN[1]}, tune {TUNE[0]}-{TUNE[1]}, test {TEST[0]}-{TEST[1]}\n')
    print('Cell burn probability (test):        AUC          Brier        log loss    ship')
    for area, r in cells.items():
        b, m = r['baseline'], r['model']
        print(f"  {area:<11} baseline {b['auc']:.3f}  {b['brier']:.4f}  {b['log_loss']:.4f}")
        print(f"  {'':<11} model    {m['auc']:.3f}  {m['brier']:.4f}  {m['log_loss']:.4f}   {r['ship']}  (L2 {r['l2']:g})")
    print('\nMonthly area outlook (test):  median |% error|   mean |log error|   ship')
    for area, r in report['monthly_outlook'].items():
        print(f"  {area:<11} climatology {r['baseline']['median_abs_pct_error']:6.1f}%   {r['baseline']['mae_log']:.3f}")
        print(f"  {'':<11} nowcast     {r['nowcast']['median_abs_pct_error']:6.1f}%   {r['nowcast']['mae_log']:.3f}"
              f"   {r['ship']}  (beta {r['beta']:.2f}); {r['test_months_inside_range']:.0%} of test months inside the range")
    print('\nSeason timing: climatology peak vs test-year peaks (months off)')
    for area, r in report['season_timing'].items():
        print(f"  {area:<11} peak {r['climatology_peak']}; test {r['test_peaks']} -> off {r['test_months_off']}; "
              f"{r['fit_years_within_1_month']:.0%} of fit years within 1 month")
    print(f'\nWrote {args.out_dir / "metrics.json"}, cell_test_predictions.parquet and monthly_climatology.csv')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
