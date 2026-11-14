"""Cell-month feature table for the fire outlook (US-15).

One row per area, 0.1 deg grid cell and month, built from VIIRS Suomi-NPP cell-days
(the daily cell table cached by src.harmonize.cached_cells). Every cell that had at
least one VIIRS detection in the record gets a row for every month.

Columns
- area, ci, cj, lat, lon        where (lat/lon = cell centre)
- year, month                   when
- What happened that month (targets, never inputs for the same month):
  cell_days (days with a detection), burned (cell_days > 0), detections, frp_max,
  frp_mean (MW), night_share (share of detections at night; empty without detections)
- Predictors, using only months BEFORE the row's month, so there is no leakage:
  lag1_cell_days          cell-days the month before
  lag12_cell_days         cell-days in the same month a year before
  past_rate_month         share of earlier years in which the cell burned in this calendar
                          month; past_years says how many earlier years that is (0 = empty)
  months_since_burn       months since the cell last burned (empty if not since the record
                          began; months_observed says how long the record was by then)
  neigh_lag1_cell_days    cell-days the month before in the 8 surrounding cells
  neigh_burned_12m        how many of the 8 surrounding cells burned in the last 12 months
  neigh_past_rate_month   mean past_rate_month of the 8 surrounding cells
- Data quality and evaluation helpers:
  viirs_gap_days          days that month VIIRS was not recording (counts there are low)
  first_seen_year         first year the cell had a detection. Rows only exist because the
                          cell burned at some point, so evaluate on cells first seen in the
                          training years (first_seen_year <= train end), or say so.

Build with:  python -m src.features            (writes data/processed/cell_month.parquet)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.harmonize import CACHE_DIR, ROOT, _expand, cached_cells, sensor_gaps

DEFAULT_OUT = ROOT / 'data' / 'processed' / 'cell_month.parquet'
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
COLUMNS = ['area', 'ci', 'cj', 'lat', 'lon', 'year', 'month',
           'cell_days', 'burned', 'detections', 'frp_max', 'frp_mean', 'night_share',
           'lag1_cell_days', 'lag12_cell_days', 'past_rate_month', 'past_years',
           'months_since_burn', 'months_observed',
           'neigh_lag1_cell_days', 'neigh_burned_12m', 'neigh_past_rate_month',
           'viirs_gap_days', 'first_seen_year']


def _shift(a: np.ndarray, k: int) -> np.ndarray:
    """a moved k months later along axis 1; the first k months are NaN."""
    out = np.full(a.shape, np.nan, dtype='float32')
    if k < a.shape[1]:
        out[:, k:] = a[:, :-k]
    return out


def _past_rate(burned: np.ndarray, months: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Share of earlier same-calendar-month columns that burned, and how many there were."""
    rate = np.full(burned.shape, np.nan, dtype='float32')
    years = np.zeros(burned.shape[1], dtype='int16')
    for m in range(1, 13):
        cols = np.flatnonzero(months == m)
        if not len(cols):
            continue
        hits = burned[:, cols].astype('float32')
        before = np.cumsum(hits, axis=1) - hits          # burns in earlier years only
        n = np.arange(len(cols), dtype='float32')        # number of earlier years
        with np.errstate(invalid='ignore', divide='ignore'):
            rate[:, cols] = np.where(n > 0, before / n, np.nan)
        years[cols] = n
    return rate, years


def _months_since(burned: np.ndarray) -> np.ndarray:
    out = np.full(burned.shape, np.nan, dtype='float32')
    last = np.full(burned.shape[0], -1)
    for t in range(burned.shape[1]):
        seen = last >= 0
        out[seen, t] = t - last[seen]
        last[burned[:, t]] = t
    return out


def _neighbour_index(ci: np.ndarray, cj: np.ndarray) -> np.ndarray:
    """(n, 8) row of each surrounding cell; n (a row of zeros) where it never burned."""
    lookup = {(i, j): k for k, (i, j) in enumerate(zip(ci.tolist(), cj.tolist()))}
    n = len(ci)
    return np.array([[lookup.get((i + di, j + dj), n) for di, dj in NEIGHBOURS]
                     for i, j in zip(ci.tolist(), cj.tolist())], dtype='int64').reshape(n, 8)


def _neighbour_sum(values: np.ndarray, idx: np.ndarray) -> np.ndarray:
    padded = np.vstack([np.nan_to_num(values), np.zeros((1, values.shape[1]), dtype=values.dtype)])
    return padded[idx].sum(axis=1)


def area_features(cells: pd.DataFrame, periods: pd.PeriodIndex, gap_days: pd.Series, grid: float) -> pd.DataFrame:
    """Feature rows for one area from its VIIRS cell-days over the given months."""
    keys = cells[['ci', 'cj']].drop_duplicates().sort_values(['ci', 'cj'], ignore_index=True)
    n, T = len(keys), len(periods)
    t_all = periods.get_indexer(pd.PeriodIndex(cells['date'].dt.to_period('M')))
    inside = t_all >= 0
    c, t = cells[inside], t_all[inside]
    r = pd.MultiIndex.from_frame(keys).get_indexer(pd.MultiIndex.from_frame(c[['ci', 'cj']]))

    def matrix(values, dtype):
        m = np.zeros((n, T), dtype=dtype)
        np.add.at(m, (r, t), values)
        return m

    cell_days = matrix(1, 'int16')
    detections = matrix(c['detections'].to_numpy(), 'int32')
    night = matrix(c['night'].to_numpy(), 'int32')
    frp_sum = matrix(c['frp_sum'].fillna(0).to_numpy(), 'float32')
    frp_max = np.full((n, T), np.nan, dtype='float32')
    np.fmax.at(frp_max, (r, t), c['frp_max'].to_numpy(dtype='float32'))
    burned = cell_days > 0
    months = np.array([q.month for q in periods])

    with np.errstate(invalid='ignore', divide='ignore'):
        frp_mean = np.where(detections > 0, frp_sum / detections, np.nan).astype('float32')
        night_share = np.where(detections > 0, night / detections, np.nan).astype('float32')
    past_rate, past_years = _past_rate(burned, months)
    idx = _neighbour_index(keys['ci'].to_numpy(), keys['cj'].to_numpy())
    lag1 = _shift(cell_days, 1)
    burned_12m = np.zeros((n, T), dtype=bool)
    cum = np.concatenate([np.zeros((n, 1)), np.cumsum(burned, axis=1)], axis=1)
    for t_ in range(T):  # burned in any of the 12 months before t_
        burned_12m[:, t_] = cum[:, t_] - cum[:, max(0, t_ - 12)] > 0
    first_col = np.where(burned.any(axis=1), burned.argmax(axis=1), 0)

    def flat(a):
        return a.reshape(-1)

    grid_years = np.array([q.year for q in periods])
    out = pd.DataFrame({
        'ci': np.repeat(keys['ci'].to_numpy(), T), 'cj': np.repeat(keys['cj'].to_numpy(), T),
        'year': np.tile(grid_years, n).astype('int16'), 'month': np.tile(months, n).astype('int8'),
        'cell_days': flat(cell_days), 'burned': flat(burned), 'detections': flat(detections),
        'frp_max': flat(frp_max), 'frp_mean': flat(frp_mean), 'night_share': flat(night_share),
        'lag1_cell_days': flat(lag1), 'lag12_cell_days': flat(_shift(cell_days, 12)),
        'past_rate_month': flat(past_rate), 'past_years': np.tile(past_years, n),
        'months_since_burn': flat(_months_since(burned)),
        'months_observed': np.tile(np.arange(T, dtype='int16'), n),
        'neigh_lag1_cell_days': flat(_neighbour_sum(lag1, idx).astype('float32')),
        'neigh_burned_12m': flat(_neighbour_sum(burned_12m.astype('int8'), idx).astype('int8')),
        'neigh_past_rate_month': flat((_neighbour_sum(past_rate, idx) / 8).astype('float32')),
        'viirs_gap_days': np.tile(gap_days.reindex(periods, fill_value=0).to_numpy(dtype='int8'), n),
        'first_seen_year': np.repeat(grid_years[first_col], T).astype('int16'),
    })
    for name in ('lag1_cell_days', 'lag12_cell_days', 'neigh_lag1_cell_days', 'neigh_past_rate_month'):
        out.loc[out['months_observed'] < (12 if name == 'lag12_cell_days' else 1), name] = np.nan
    out.loc[out['past_years'] == 0, 'neigh_past_rate_month'] = np.nan
    out['lat'] = ((out['ci'] + 0.5) * grid).astype('float32')
    out['lon'] = ((out['cj'] + 0.5) * grid).astype('float32')
    return out


def build_features(cells: pd.DataFrame, coverage: pd.DataFrame, grid: float = 0.1,
                   extend_months: int = 0) -> pd.DataFrame:
    """The cell-month table (COLUMNS) for every area with VIIRS data.

    extend_months adds that many months after the data ends. Their predictors are real
    (they only use earlier months); their outcome columns are 0 because nothing is known
    yet. The outlook (src/outlook.py) uses this to forecast the month after the record.
    """
    gaps = sensor_gaps(cells, coverage)
    gap_dates = pd.to_datetime(gaps.loc[gaps['sensor'] == 'viirs', 'date'])
    gap_days = pd.PeriodIndex(gap_dates, freq='M').value_counts()
    viirs = cells[cells['sensor'] == 'viirs']
    parts = []
    for area, grp in viirs.groupby('area'):
        cov = coverage[(coverage['area'] == area) & (coverage['sensor'] == 'viirs')]['period']
        if not len(cov):
            continue
        periods = pd.period_range(cov.min(), cov.max() + extend_months, freq='M')
        part = area_features(grp, periods, gap_days, grid)
        part.insert(0, 'area', area)
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.concat(parts, ignore_index=True)[COLUMNS]
    out['area'] = out['area'].astype('category')
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the cell-month feature table (US-15).')
    parser.add_argument('paths', nargs='*', default=[str(ROOT / 'data' / '*.csv')],
                        help='FIRMS CSVs (default: data/*.csv)')
    parser.add_argument('--grid', type=float, default=0.1, help='grid cell size in degrees (default: 0.1)')
    parser.add_argument('--train-end', type=int, default=2019,
                        help='last training year, for the summary only (default: 2019)')
    parser.add_argument('--cache-dir', type=Path, default=CACHE_DIR, help='cell-day cache folder')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='output Parquet path')
    args = parser.parse_args(argv)

    paths = _expand(args.paths)
    if not paths:
        parser.error('no CSV files found; download them with: python3 scripts/get_data.py')
    cells, coverage, _ = cached_cells(paths, args.grid, cache_dir=args.cache_dir)
    table = build_features(cells, coverage, grid=args.grid)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)

    print(f'Cell-month table: {len(table):,} rows, {table["burned"].mean():.1%} of cell-months burned')
    print(f"{'area':<12} {'cells':>7} {'months':>7} {'first seen after ' + str(args.train_end):>22}")
    for area, grp in table.groupby('area', observed=True):
        per_cell = grp.drop_duplicates(['ci', 'cj'])
        late = int((per_cell['first_seen_year'] > args.train_end).sum())
        print(f'{area:<12} {len(per_cell):7,} {grp["year"].nunique() * 12:7d} {late:16,} ({late / len(per_cell):.0%})')
    print(f'Wrote {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
