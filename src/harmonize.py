"""Harmonize MODIS and VIIRS detections into one monthly fire-activity record (US-02).

Method (see docs/harmonization.md):
1. Match the satellites: MODIS Aqua + VIIRS Suomi-NPP (same ~13:30 / 01:30 overpass).
   Terra (10:30) is left out unless include_terra=True.
2. Count fire cell-days, not pixels: snap detections to a grid (default 0.1 deg) and
   count each cell at most once per day per sensor.
3. Aggregate by month: cell-days per area, sensor, year and month; months with no fires
   are 0, and months a sensor has no data file for are missing (NA), not 0.
4. Calibrate on the overlap: per area, VIIRS ~= factor x MODIS (least squares through
   the origin) over months where both sensors have data.
5. Build the harmonized series: VIIRS where it exists, otherwise MODIS x factor.

Rebuild everything with:  python -m src.harmonize data/*.csv
"""
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / 'data' / 'processed' / 'harmonized_monthly.csv'

# FIRMS 'satellite' values: MODIS reports Aqua/Terra; VIIRS Suomi-NPP reports 'N'.
MATCHED_SATELLITES = {
    'modis': {'AQUA'},
    'viirs': {'N', 'NPP', 'SUOMI NPP', 'SUOMI-NPP'},
}
TERRA = 'TERRA'
OUTPUT_COLUMNS = ['area', 'year', 'month', 'modis_cell_days', 'viirs_cell_days',
                  'modis_scaled', 'harmonized', 'source', 'factor']
FILE_PATTERN = re.compile(r'^(?P<sensor>modis|viirs)[^_]*_(?P<year>\d{4})_', re.IGNORECASE)


def _sensor(instrument: pd.Series) -> pd.Series:
    return instrument.astype('string').str.strip().str.upper().map({'MODIS': 'modis', 'VIIRS': 'viirs'})


def _area(df: pd.DataFrame) -> pd.Series:
    if 'area' not in df:
        return pd.Series('All', index=df.index, dtype='string')
    return df['area'].astype('string').fillna('All')


def _coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Months each (area, sensor) has data for.

    A yearly FIRMS country file covers all 12 months of its year, so a month with no
    detections inside it is a real zero. Without a recognisable file name, coverage is
    the first to last month seen in the data.
    """
    base = pd.DataFrame({'area': _area(df), 'sensor': _sensor(df['instrument']),
                         'source_file': df.get('source_file', pd.Series(pd.NA, index=df.index)),
                         'date': pd.to_datetime(df['acq_date'])}).dropna(subset=['sensor'])
    parts = []
    for (area, sensor, source), grp in base.groupby(['area', 'sensor', 'source_file'], dropna=False):
        match = FILE_PATTERN.match(str(source)) if pd.notna(source) else None
        if match and match['sensor'].lower() == sensor:
            year = int(match['year'])
            months = pd.period_range(f'{year}-01', f'{year}-12', freq='M')
        else:
            months = pd.period_range(grp['date'].min().to_period('M'),
                                     grp['date'].max().to_period('M'), freq='M')
        parts.append(pd.DataFrame({'area': area, 'sensor': sensor, 'period': months}))
    if not parts:
        return pd.DataFrame(columns=['area', 'sensor', 'period'])
    return pd.concat(parts, ignore_index=True).drop_duplicates()


def monthly_cell_days(df: pd.DataFrame, grid: float = 0.1, include_terra: bool = False) -> pd.DataFrame:
    """Steps 1-3. Long table: area, sensor, year, month, cell_days (Int64; NA = no data).

    Takes cleaned detections from src.load_data.load_hotspots.
    """
    if grid <= 0:
        raise ValueError('grid must be positive (degrees)')
    coverage = _coverage(df)

    sensor = _sensor(df['instrument'])
    satellite = df['satellite'].astype('string').str.strip().str.upper()
    keep = ((sensor.eq('modis') & satellite.isin(MATCHED_SATELLITES['modis'] | ({TERRA} if include_terra else set())))
            | (sensor.eq('viirs') & satellite.isin(MATCHED_SATELLITES['viirs'])))
    d = pd.DataFrame({
        'area': _area(df), 'sensor': sensor,
        'date': pd.to_datetime(df['acq_date']).dt.normalize(),
        # small epsilon so values exactly on a grid line don't fall into the cell below
        'ci': np.floor(df['latitude'].astype(float) / grid + 1e-9).astype('int64'),
        'cj': np.floor(df['longitude'].astype(float) / grid + 1e-9).astype('int64'),
    })[keep.fillna(False)]
    cell_days = d.drop_duplicates(['area', 'sensor', 'date', 'ci', 'cj'])
    counts = (cell_days.assign(period=cell_days['date'].dt.to_period('M'))
              .groupby(['area', 'sensor', 'period']).size().rename('cell_days'))

    # Every month of every year an area has data for, for both sensors.
    rows = []
    for area, grp in coverage.groupby('area'):
        years = sorted({p.year for p in grp['period']})
        months = pd.period_range(f'{years[0]}-01', f'{years[-1]}-12', freq='M')
        months = [p for p in months if p.year in years]
        for s in ('modis', 'viirs'):
            rows.append(pd.DataFrame({'area': area, 'sensor': s, 'period': months}))
    if not rows:
        return pd.DataFrame(columns=['area', 'sensor', 'year', 'month', 'cell_days'])
    out = pd.concat(rows, ignore_index=True)
    covered = set(map(tuple, coverage[['area', 'sensor', 'period']].itertuples(index=False)))
    out['covered'] = [(a, s, p) in covered for a, s, p in out[['area', 'sensor', 'period']].itertuples(index=False)]
    out = out.join(counts, on=['area', 'sensor', 'period'])
    out['cell_days'] = out['cell_days'].fillna(0).astype('Int64').where(out['covered'])
    out['year'] = [p.year for p in out['period']]
    out['month'] = [p.month for p in out['period']]
    return out[['area', 'sensor', 'year', 'month', 'cell_days']].sort_values(
        ['area', 'sensor', 'year', 'month'], ignore_index=True)


def fit_factors(wide: pd.DataFrame) -> pd.DataFrame:
    """Step 4. One row per area: factor, r2, pearson_r, median_abs_pct_diff, overlap_months.

    factor minimises sum (viirs - factor * modis)^2 over months where both are present.
    r2 is computed against the mean of VIIRS (1 = perfect, can be negative for a bad fit).
    median_abs_pct_diff is the median of |modis_scaled - viirs| / viirs, in %, over
    overlap months with VIIRS > 0.
    """
    out = []
    for area, grp in wide.groupby('area'):
        both = grp.dropna(subset=['modis_cell_days', 'viirs_cell_days'])
        m = both['modis_cell_days'].astype(float).to_numpy()
        v = both['viirs_cell_days'].astype(float).to_numpy()
        fit = dict(area=area, factor=np.nan, r2=np.nan, pearson_r=np.nan,
                   median_abs_pct_diff=np.nan, overlap_months=len(both))
        if len(both) and (m * m).sum() > 0:
            factor = float((m * v).sum() / (m * m).sum())
            scaled = factor * m
            ss_tot = ((v - v.mean()) ** 2).sum()
            fit['factor'] = factor
            fit['r2'] = float(1 - ((v - scaled) ** 2).sum() / ss_tot) if ss_tot > 0 else np.nan
            if len(both) > 1 and m.std() > 0 and v.std() > 0:
                fit['pearson_r'] = float(np.corrcoef(m, v)[0, 1])
            pos = v > 0
            if pos.any():
                fit['median_abs_pct_diff'] = float(np.median(np.abs(scaled[pos] - v[pos]) / v[pos]) * 100)
        out.append(fit)
    return pd.DataFrame(out, columns=['area', 'factor', 'r2', 'pearson_r',
                                      'median_abs_pct_diff', 'overlap_months'])


def harmonize(df: pd.DataFrame, grid: float = 0.1, include_terra: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Steps 1-5. Returns (monthly table with OUTPUT_COLUMNS, per-area fit table)."""
    long = monthly_cell_days(df, grid=grid, include_terra=include_terra)
    wide = (long.pivot_table(index=['area', 'year', 'month'], columns='sensor',
                             values='cell_days', aggfunc='first', dropna=False)
            .reindex(columns=['modis', 'viirs'])
            .rename(columns={'modis': 'modis_cell_days', 'viirs': 'viirs_cell_days'})
            .reset_index())
    wide.columns.name = None
    for col in ('modis_cell_days', 'viirs_cell_days'):
        wide[col] = wide[col].astype('Int64')
    fits = fit_factors(wide)
    wide['factor'] = wide['area'].map(fits.set_index('area')['factor'])
    wide['modis_scaled'] = wide['modis_cell_days'].astype('Float64') * wide['factor']
    has_viirs = wide['viirs_cell_days'].notna()
    has_scaled = wide['modis_scaled'].notna()
    wide['harmonized'] = wide['viirs_cell_days'].astype('Float64').where(has_viirs, wide['modis_scaled'])
    wide['source'] = np.where(has_viirs, 'viirs', np.where(has_scaled, 'modis_scaled', 'none'))
    return wide[OUTPUT_COLUMNS].sort_values(['area', 'year', 'month'], ignore_index=True), fits


def _expand(paths: list[str]) -> list[Path]:
    """Expand globs ourselves so `data/*.csv` also works in Windows PowerShell."""
    out: list[Path] = []
    for p in paths:
        matches = sorted(glob.glob(p)) if any(ch in p for ch in '*?[') else [p]
        out.extend(Path(m) for m in matches)
    return out


def main(argv: list[str] | None = None) -> int:
    from src.load_data import load_hotspots

    parser = argparse.ArgumentParser(description='Build the harmonized monthly fire record (US-02).')
    parser.add_argument('paths', nargs='*', default=[str(ROOT / 'data' / '*.csv')],
                        help='FIRMS CSVs (default: data/*.csv)')
    parser.add_argument('--grid', type=float, default=0.1, help='grid cell size in degrees (default: 0.1)')
    parser.add_argument('--include-terra', action='store_true', help='also use MODIS Terra')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='output CSV path')
    parser.add_argument('--quiet', action='store_true', help="don't print per-file cleaning counts")
    args = parser.parse_args(argv)

    paths = _expand(args.paths)
    if not paths:
        parser.error('no CSV files found; download them with: python3 scripts/get_data.py')
    df = load_hotspots(paths, verbose=not args.quiet)
    table, fits = harmonize(df, grid=args.grid, include_terra=args.include_terra)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out, index=False)

    sats = 'Aqua + Terra' if args.include_terra else 'Aqua'
    print(f'\nHarmonization: MODIS {sats} vs VIIRS Suomi-NPP, {args.grid} deg cell-days')
    print(f"{'area':<12} {'factor':>7} {'R2':>6} {'r':>6} {'median |%diff|':>15} {'months':>7}")
    for f in fits.itertuples():
        print(f'{f.area:<12} {f.factor:7.2f} {f.r2:6.2f} {f.pearson_r:6.2f} '
              f'{f.median_abs_pct_diff:14.1f}% {f.overlap_months:7d}')
    no_fit = fits.loc[fits['factor'].isna(), 'area'].tolist()
    if no_fit:
        print(f"\nNo factor for {', '.join(no_fit)}: needs months with both MODIS and VIIRS data "
              '(download both sensors for the same years). Their harmonized values are VIIRS-only.')
    print(f'\nWrote {len(table):,} area-months to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
