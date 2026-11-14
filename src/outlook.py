"""Page data for the globe's Outlook mode (US-18): outlook.json.

Built by src/web_data.py next to archive.json and monthly.json, from the US-14 cell
cache, the US-15 feature table and the US-16 models. Per area it holds:

- skill: how each US-16 outlook scored on the 2022-2023 test years against its
  climatology baseline, and whether it ships (beats the baseline). An outlook that
  does not ship is replaced by its baseline below.
- forecast: the month after the record ends. A map of cells with at least a 5% chance
  of a fire cell-day (the model refitted on every year, or the baseline if the model
  does not ship), and the expected harmonized fire cell-days for the area with the
  historical low-high range for that month.
- backtest: each 2022-2023 month as the tested model saw it: the predicted map, every
  cell that actually burned (fires in cells the model could not score, first seen after
  2021, count as misses: new_area_fires), the share of fires that fell on cells shown
  on the outlook map (on_map_share), and the monthly prediction vs what happened. Months with VIIRS gap
  days are shown with viirs_gap_days (observed fires undercounted) but not scored.
- climatology: mean, low and high harmonized fire cell-days per calendar month.

Everything is labelled as an outlook from 2012-2023 patterns, not a forecast: the
models know only fire history, not weather. If anything fails, outlook.json says
status "unavailable" with the reason, and the Outlook tab shows that reason.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.features import build_features
from src.harmonize import cached_cells, harmonize_cells
from src.predict import (TEST, TRAIN, TUNE, _rows, _with_last_month, cell_models, climatology, design,
                         fit_logistic, fit_persistence, monthly_models, predict_logistic, season_timing)

LABEL = 'Outlook from 2012–2023 patterns, not a forecast'
MIN_P = 0.05          # cells below this chance are left off the map
MAX_CELLS = 2500      # per map, highest chances first
MAX_FIRES = 2500      # actual burned cells per back-test month (evenly sampled beyond this)


def _r(x, digits=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), digits)


def _map_rows(p) -> np.ndarray:
    """Rows shown on an outlook map: chance >= MIN_P, highest first, at most MAX_CELLS."""
    p = np.asarray(p)
    keep = np.flatnonzero(p >= MIN_P)
    return keep[np.argsort(-p[keep], kind='stable')][:MAX_CELLS]


def _cell_list(lat, lon, p) -> list:
    lat, lon, p = map(np.asarray, (lat, lon, p))
    return [[round(float(lat[i]), 2), round(float(lon[i]), 2), round(float(p[i]), 3)] for i in _map_rows(p)]


def _fire_list(lat, lon) -> list:
    every = max(1, int(np.ceil(len(lat) / MAX_FIRES)))
    return [[round(float(a), 2), round(float(b), 2)] for a, b in zip(lat[::every], lon[::every])]


def _skill(cell: dict | None, monthly: dict | None, timing: dict | None) -> dict:
    out = {}
    if cell:
        out['cell'] = {'auc_baseline': _r(cell['baseline']['auc']), 'auc_model': _r(cell['model']['auc']),
                       'brier_baseline': _r(cell['baseline']['brier'], 4), 'brier_model': _r(cell['model']['brier'], 4),
                       'ship': cell['ship'], 'cells_scored': cell['cells_scored']}
    if monthly:
        out['monthly'] = {'error_baseline': _r(monthly['baseline']['median_abs_pct_error'], 1),
                          'error_nowcast': _r(monthly['nowcast']['median_abs_pct_error'], 1),
                          'ship': monthly['ship'], 'beta': _r(monthly['beta'])}
    if timing:
        out['timing'] = {'peak': timing['climatology_peak'], 'test_peaks': timing['test_peaks']}
    return out


def build_outlook(cells: pd.DataFrame, coverage: pd.DataFrame, monthly: pd.DataFrame, grid: float = 0.1) -> dict:
    """outlook.json content from the cell table, its coverage and the harmonized monthly table."""
    viirs = coverage[coverage['sensor'] == 'viirs']['period']
    years = {p.year for p in viirs}
    needed = set(range(TRAIN[0], TEST[1] + 1))
    if not needed <= years:
        missing = sorted(needed - years)
        raise ValueError(f'the outlook needs VIIRS data for {TRAIN[0]}-{TEST[1]} '
                         f'({len(missing)} year(s) missing, e.g. {missing[0]}); run python3 scripts/get_data.py')
    table = build_features(cells, coverage, grid, extend_months=1)
    data_end = viirs.max()
    target = data_end + 1
    first_year, last_year = int(viirs.min().year), int(data_end.year)
    future = (table['year'] == target.year) & (table['month'] == target.month)
    history = table[~future]
    tested = {}
    cell_res, preds = cell_models(history, models_out=tested)
    mon_res, timing = monthly_models(monthly), season_timing(monthly)
    clim_all = climatology(monthly, (first_year, last_year))
    clim_fit = climatology(monthly, (TRAIN[0], TUNE[1]))

    areas = {}
    for area, df in table.groupby('area', observed=True):
        area = str(area)
        cell, mon = cell_res.get(area), mon_res.get(area)
        fut = df[future.loc[df.index]]

        # Forecast map: refit the chosen model on every year, or fall back to the baseline.
        use_model = bool(cell and cell['ship'])
        if use_model:
            fit = _rows(df[~future.loc[df.index]], (first_year, last_year), last_year)
            model = fit_logistic(design(fit), fit['burned'].to_numpy(), l2=cell['l2'])
            p_future = predict_logistic(model, design(fut))
        else:
            p_future = fut['past_rate_month'].fillna(0).to_numpy(dtype='float64')

        # Forecast for the area: nowcast from the last month, or the monthly normal.
        m_area = monthly[monthly['area'] == area].sort_values(['year', 'month'])
        c_area = clim_all[clim_all['area'] == area].set_index('month')
        normal = float(c_area.loc[target.month, 'mean'])
        expected, method_monthly = normal, 'climatology'
        if mon and mon['ship'] and len(m_area):
            hist = _with_last_month(m_area, clim_all)
            beta = fit_persistence(hist)
            prev = float(m_area['harmonized'].iloc[-1])
            prev_normal = float(c_area.loc[data_end.month, 'mean'])
            expected = float(np.expm1(np.log1p(normal) + beta * (np.log1p(prev) - np.log1p(prev_normal))))
            method_monthly = 'nowcast'

        forecast = {
            'month': str(target), 'method_map': 'model' if use_model else 'climatology',
            'cells': _cell_list(fut['lat'], fut['lon'], p_future),
            'cells_30': int((p_future >= 0.3).sum()), 'expected_cells': _r(p_future.sum(), 1),
            'monthly': {'expected': _r(expected, 0), 'normal': _r(normal, 0),
                        'low': _r(c_area.loc[target.month, 'low'], 0), 'high': _r(c_area.loc[target.month, 'high'], 0),
                        'method': method_monthly, 'last_month': str(data_end),
                        'last_month_value': _r(m_area['harmonized'].iloc[-1], 0) if len(m_area) else None},
        }

        # Back-tests: the tested model (or baseline) month by month on the test years.
        backtest = {}
        pa = preds[preds['area'] == area] if len(preds) else preds
        # Months with VIIRS gap days are left out of the scores but still shown, flagged:
        # the tested model's chances are valid there, the observed fires are undercounted.
        gap_rows = df[df['year'].between(*TEST) & (df['viirs_gap_days'] > 0) & (df['first_seen_year'] <= TUNE[1])]
        if len(gap_rows) and area in tested:
            p_gap = (predict_logistic(tested[area], design(gap_rows)) if use_model
                     else gap_rows['past_rate_month'].fillna(0).to_numpy(dtype='float64'))
            pa = pd.concat([pa, pd.DataFrame({
                'area': area, 'ci': gap_rows['ci'].to_numpy(), 'cj': gap_rows['cj'].to_numpy(),
                'year': gap_rows['year'].to_numpy(), 'month': gap_rows['month'].to_numpy(),
                'burned': gap_rows['burned'].to_numpy(), 'p_baseline': p_gap, 'p_model': p_gap})], ignore_index=True)
        gap_days = df.drop_duplicates(['year', 'month']).set_index(['year', 'month'])['viirs_gap_days']
        bt_monthly = _with_last_month(m_area, clim_fit)
        beta_fit = mon['beta'] if mon else 0.0
        for (y, m), g in pa.groupby(['year', 'month']):
            p = (g['p_model'] if use_model else g['p_baseline']).to_numpy(dtype='float64')
            burned = g['burned'].to_numpy(dtype=bool)
            lat = ((g['ci'].to_numpy() + 0.5) * grid).astype('float64')
            lon = ((g['cj'].to_numpy() + 0.5) * grid).astype('float64')
            row = bt_monthly[(bt_monthly['year'] == y) & (bt_monthly['month'] == m)]
            predicted = None
            if len(row):
                r = row.iloc[0]
                anomaly = np.log1p(r['prev']) - np.log1p(r['prev_norm'])
                predicted = float(np.expm1(np.log1p(r['norm']) + (beta_fit if mon and mon['ship'] else 0.0) * anomaly))
            # Every cell that burned that month, including cells the model could not score
            # (first seen after the fitting years): those count as misses.
            month_fires = df[(df['year'] == y) & (df['month'] == m) & df['burned']]
            n_fires, scored_fires = len(month_fires), int(burned.sum())
            backtest[f'{int(y)}-{int(m):02d}'] = {
                'cells': _cell_list(lat, lon, p),
                'fires': _fire_list(month_fires['lat'].to_numpy(), month_fires['lon'].to_numpy()),
                'burned_cells': n_fires, 'new_area_fires': n_fires - scored_fires, 'expected_cells': _r(p.sum(), 1),
                'on_map_share': _r(burned[_map_rows(p)].sum() / n_fires) if n_fires else None,
                'monthly_predicted': _r(predicted, 0),
                'monthly_actual': _r(row.iloc[0]['harmonized'], 0) if len(row) else None,
                'viirs_gap_days': int(gap_days.get((y, m), 0)),
            }

        areas[area] = {
            'skill': _skill(cell, mon, timing.get(area)),
            'forecast': forecast,
            'backtest': backtest,
            'climatology': [{'month': int(mm), 'mean': _r(r['mean'], 0), 'low': _r(r['low'], 0), 'high': _r(r['high'], 0)}
                            for mm, r in c_area.iterrows()],
        }
    return {'status': 'ok', 'label': LABEL, 'built': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'data_end': str(data_end), 'forecast_month': str(target),
            'years': {'train': list(TRAIN), 'tune': list(TUNE), 'test': list(TEST)},
            'min_p': MIN_P, 'max_cells': MAX_CELLS, 'areas': areas}


def write_outlook(files: list[Path], out: Path, cache_dir: Path, *, verbose: bool = True) -> dict:
    """Build outlook.json from the cell cache; on any failure write status 'unavailable'.

    Works from the US-14 cache only (the harmonized table comes from harmonize_cells,
    identical to loading every detection). src/web_data.py runs it in its own process
    (run_outlook), so its memory is returned before the page build loads every detection.
    """
    try:
        cells, coverage, _ = cached_cells(files, cache_dir=cache_dir)
        monthly, _ = harmonize_cells(cells, coverage)
        data = build_outlook(cells, coverage, monthly)
    except Exception as exc:  # the rest of the page must not depend on the outlook
        if verbose:
            print(f'Outlook not built ({exc}); the Outlook tab will say so.')
            traceback.print_exc()
        data = {'status': 'unavailable', 'reason': str(exc), 'label': LABEL, 'areas': {}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    return data


def run_outlook(files: list[Path], out: Path, cache_dir: Path, *, verbose: bool = True) -> dict:
    """write_outlook in a separate Python process; returns what it wrote."""
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, '-m', 'src.outlook', '--out', str(out), '--cache-dir', str(cache_dir)]
    cmd += [] if verbose else ['--quiet']
    proc = subprocess.run(cmd + [str(f) for f in files], cwd=root)
    if proc.returncode != 0 or not out.exists():
        data = {'status': 'unavailable', 'reason': f'outlook process exited with {proc.returncode}',
                'label': LABEL, 'areas': {}}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data), encoding='utf-8')
        return data
    return json.loads(out.read_text(encoding='utf-8'))


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Build outlook.json for the globe\'s Outlook mode (US-18).')
    parser.add_argument('paths', nargs='+', type=Path, help='FIRMS CSVs')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    data = write_outlook(args.paths, args.out, args.cache_dir, verbose=not args.quiet)
    return 0 if data.get('status') in ('ok', 'unavailable') else 1


if __name__ == '__main__':
    raise SystemExit(main())
