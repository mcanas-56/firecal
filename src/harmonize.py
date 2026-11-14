"""Harmonize MODIS and VIIRS detections into one monthly fire-activity record (US-02).

Method (see docs/harmonization.md):
1. Match the satellites: MODIS Aqua + VIIRS Suomi-NPP (same ~13:30 / 01:30 overpass).
   Terra (10:30) is left out unless include_terra=True.
2. Count fire cell-days, not pixels: snap detections to a grid (default 0.1 deg) and
   count each cell at most once per day per sensor.
3. Aggregate by month: cell-days per area, sensor, year and month; months with no fires
   are 0, and months a sensor has no data file for are missing (NA), not 0.
4. Find satellite gaps: days one sensor recorded nothing in any area it covers while the
   other sensor saw fires there (e.g. Suomi NPP was offline 27 Jul-10 Aug 2022).
5. Calibrate on the overlap: per area, VIIRS ~= factor x MODIS (least squares through
   the origin) over months where both sensors have data, leaving out gap days.
6. Build the harmonized series: VIIRS where it exists, with VIIRS gap days filled by
   that day's MODIS x factor; otherwise MODIS x factor.

Checks (US-14): the factor fitted per year shows whether one factor per area is stable,
and a power-law fit (VIIRS = a x MODIS^b) is compared with the single factor. The
published series keeps the single factor (team decision, docs/harmonization.md).

The command line reads each CSV once into a daily cell table cached as Parquet in
data/processed/cells/, so a rebuild of 2012-2023 never holds every detection in memory.

Rebuild everything with:  python -m src.harmonize data/*.csv
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / 'data' / 'processed' / 'harmonized_monthly.csv'
CACHE_DIR = ROOT / 'data' / 'processed' / 'cells'
CACHE_VERSION = 2
CELL_KEYS = ['area', 'sensor', 'date', 'ci', 'cj']

# FIRMS 'satellite' values: MODIS reports Aqua/Terra; VIIRS Suomi-NPP reports 'N'.
MATCHED_SATELLITES = {
    'modis': {'AQUA'},
    'viirs': {'N', 'NPP', 'SUOMI NPP', 'SUOMI-NPP'},
}
TERRA = 'TERRA'
OUTPUT_COLUMNS = ['area', 'year', 'month', 'modis_cell_days', 'viirs_cell_days',
                  'modis_scaled', 'harmonized', 'source', 'factor', 'viirs_gap_days']
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


def _cell_days(df: pd.DataFrame, grid: float, include_terra: bool) -> pd.DataFrame:
    """Steps 1-2. One row per area, sensor, date and grid cell with a detection.

    Also keeps, per cell-day, the number of detections, night detections, and the
    highest and summed FRP (MW), so the cached table can feed later features (US-15)
    without re-reading the CSVs.
    """
    if grid <= 0:
        raise ValueError('grid must be positive (degrees)')
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
        'frp': pd.to_numeric(df['frp'], errors='coerce') if 'frp' in df else np.nan,
        'night': (df['daynight'].astype('string').str.strip().str.upper().eq('N').fillna(False)
                  if 'daynight' in df else False),
    })[keep.fillna(False).astype(bool)]
    return (d.groupby(CELL_KEYS, sort=False)
            .agg(detections=('frp', 'size'), night=('night', 'sum'),
                 frp_max=('frp', 'max'), frp_sum=('frp', 'sum'))
            .reset_index())


def sensor_gaps(cells: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """Step 4. Days a sensor recorded nothing while the other sensor saw fires.

    A day is a gap for sensor S when every area S covers that month has zero S detections
    and the other sensor has detections in at least one of those areas the same day.
    VIIRS sees more fires than MODIS, so a whole day of MODIS fires with no VIIRS at all
    means VIIRS was not recording, not that there were no fires. Returns sensor, date.
    """
    per_day = cells.groupby(['sensor', 'date', 'area']).size()
    has = set(per_day.index)
    covered = {(r.sensor, r.period, r.area) for r in coverage.itertuples(index=False)}
    out = []
    for s, other in (('viirs', 'modis'), ('modis', 'viirs')):
        dates = sorted({d for (sen, d, _) in has if sen == other})
        for d in dates:
            period = d.to_period('M')
            areas = [a for (sen, p, a) in covered if sen == s and p == period]
            both = [a for a in areas if (other, period, a) in covered]
            if not both:
                continue
            if any((s, d, a) in has for a in areas):
                continue
            if any((other, d, a) in has for a in both):
                out.append((s, d))
    return pd.DataFrame(out, columns=['sensor', 'date'])


def _monthly(cells: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """Step 3. Long table: area, sensor, year, month, cell_days (Int64; NA = no data)."""
    counts = (cells.assign(period=cells['date'].dt.to_period('M'))
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


def monthly_cell_days(df: pd.DataFrame, grid: float = 0.1, include_terra: bool = False) -> pd.DataFrame:
    """Steps 1-3. Long table: area, sensor, year, month, cell_days (Int64; NA = no data).

    Takes cleaned detections from src.load_data.load_hotspots. Raw counts: satellite
    gaps are not filled here (see harmonize).
    """
    return _monthly(_cell_days(df, grid, include_terra), _coverage(df))


def _wide(long: pd.DataFrame) -> pd.DataFrame:
    wide = (long.pivot_table(index=['area', 'year', 'month'], columns='sensor',
                             values='cell_days', aggfunc='first', dropna=False)
            .reindex(columns=['modis', 'viirs'])
            .rename(columns={'modis': 'modis_cell_days', 'viirs': 'viirs_cell_days'})
            .reset_index())
    wide.columns.name = None
    for col in ('modis_cell_days', 'viirs_cell_days'):
        wide[col] = wide[col].astype('Int64')
    return wide


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


def fit_factors_by_year(wide: pd.DataFrame) -> pd.DataFrame:
    """The single factor fitted on each year alone: area, year + the fit_factors columns.

    One factor per area assumes the MODIS-VIIRS ratio is stable over time; this shows
    whether it is.
    """
    parts = []
    for year, grp in wide.groupby('year'):
        fits = fit_factors(grp)
        fits.insert(1, 'year', int(year))
        parts.append(fits)
    if not parts:
        return pd.DataFrame(columns=['area', 'year', 'factor', 'r2', 'pearson_r',
                                     'median_abs_pct_diff', 'overlap_months'])
    return pd.concat(parts, ignore_index=True).sort_values(['area', 'year'], ignore_index=True)


def _errors(v: np.ndarray, scaled: np.ndarray) -> tuple[float, float]:
    """(median |% diff|, activity-weighted |% diff|) over months with VIIRS > 0."""
    pos = v > 0
    if not pos.any():
        return np.nan, np.nan
    diff = np.abs(scaled[pos] - v[pos])
    return float(np.median(diff / v[pos]) * 100), float(diff.sum() / v[pos].sum() * 100)


def compare_methods(wide: pd.DataFrame) -> pd.DataFrame:
    """Single factor vs power law (VIIRS = a x MODIS^b) on the same overlap months.

    The power law is fitted in log space on months where both counts are above 0; a
    month with MODIS 0 is predicted as 0. Quiet months are those with VIIRS below the
    area's median overlap month, busy months the rest. One row per area and method.
    """
    rows = []
    for area, grp in wide.groupby('area'):
        both = grp.dropna(subset=['modis_cell_days', 'viirs_cell_days'])
        m = both['modis_cell_days'].astype(float).to_numpy()
        v = both['viirs_cell_days'].astype(float).to_numpy()
        if not len(both) or (m * m).sum() == 0:
            continue
        quiet = v < np.median(v)
        factor = float((m * v).sum() / (m * m).sum())
        candidates = [('factor', f'factor {factor:.2f}', factor * m)]
        pos = (m > 0) & (v > 0)
        if pos.sum() >= 3 and np.log(m[pos]).std() > 0:
            b, log_a = np.polyfit(np.log(m[pos]), np.log(v[pos]), 1)
            a = float(np.exp(log_a))
            candidates.append(('power', f'a {a:.2f}, b {b:.2f}', np.where(m > 0, a * np.power(m, b), 0.0)))
        for method, params, scaled in candidates:
            median_all, weighted = _errors(v, scaled)
            rows.append(dict(area=area, method=method, params=params,
                             median_abs_pct_diff=median_all, weighted_abs_pct_diff=weighted,
                             quiet_median_abs_pct_diff=_errors(v[quiet], scaled[quiet])[0],
                             busy_median_abs_pct_diff=_errors(v[~quiet], scaled[~quiet])[0],
                             overlap_months=len(both)))
    return pd.DataFrame(rows, columns=['area', 'method', 'params', 'median_abs_pct_diff',
                                       'weighted_abs_pct_diff', 'quiet_median_abs_pct_diff',
                                       'busy_median_abs_pct_diff', 'overlap_months'])


def harmonize(df: pd.DataFrame, grid: float = 0.1, include_terra: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Steps 1-6. Returns (monthly table with OUTPUT_COLUMNS, per-area fit table).

    The fit table also has gap_days: the satellite-gap days left out of that area's fit.
    table.attrs['gaps'] lists every gap day (sensor, date); fits.attrs['by_year'] and
    fits.attrs['methods'] hold fit_factors_by_year and compare_methods on the fit months.
    """
    return harmonize_cells(_cell_days(df, grid, include_terra), _coverage(df))


def harmonize_cells(cells: pd.DataFrame, coverage: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """harmonize() from a daily cell table (_cell_days / cached_cells) and its coverage."""
    gaps = sensor_gaps(cells, coverage)
    gap_dates = set(gaps['date'])
    viirs_gap_dates = set(gaps.loc[gaps['sensor'] == 'viirs', 'date'])

    wide = _wide(_monthly(cells, coverage))
    # Fit on days both sensors were recording.
    fit_cells = cells[~cells['date'].isin(gap_dates)]
    fit_wide = _wide(_monthly(fit_cells, coverage))
    fits = fit_factors(fit_wide)
    fits['gap_days'] = len(gap_dates)
    fits.attrs['by_year'] = fit_factors_by_year(fit_wide)
    fits.attrs['methods'] = compare_methods(fit_wide)
    wide['factor'] = wide['area'].map(fits.set_index('area')['factor'])
    wide['modis_scaled'] = wide['modis_cell_days'].astype('Float64') * wide['factor']

    # MODIS cell-days on VIIRS gap days, per area-month, to fill those days.
    fill = cells[(cells['sensor'] == 'modis') & cells['date'].isin(viirs_gap_dates)]
    fill = (fill.assign(year=fill['date'].dt.year, month=fill['date'].dt.month)
            .groupby(['area', 'year', 'month']).size().rename('modis_on_gaps'))
    gap_counts = pd.Series([1] * len(viirs_gap_dates), dtype='int64',
                           index=pd.MultiIndex.from_tuples([(d.year, d.month) for d in viirs_gap_dates],
                                                           names=['year', 'month'])) if viirs_gap_dates else None
    wide = wide.join(fill, on=['area', 'year', 'month'])
    wide['modis_on_gaps'] = wide['modis_on_gaps'].fillna(0)
    if gap_counts is not None:
        per_month = gap_counts.groupby(level=['year', 'month']).sum().rename('viirs_gap_days')
        wide = wide.join(per_month, on=['year', 'month'])
    else:
        wide['viirs_gap_days'] = 0
    has_viirs = wide['viirs_cell_days'].notna()
    wide['viirs_gap_days'] = wide['viirs_gap_days'].fillna(0).astype('int64').where(has_viirs, 0)

    has_scaled = wide['modis_scaled'].notna()
    filled = wide['viirs_cell_days'].astype('Float64') + (wide['modis_on_gaps'] * wide['factor']).fillna(0)
    wide['harmonized'] = filled.where(has_viirs, wide['modis_scaled'])
    is_filled = has_viirs & wide['modis_on_gaps'].gt(0) & wide['factor'].notna()
    wide['source'] = np.where(is_filled, 'viirs+modis_gap_fill',
                              np.where(has_viirs, 'viirs', np.where(has_scaled, 'modis_scaled', 'none')))
    table = wide[OUTPUT_COLUMNS].sort_values(['area', 'year', 'month'], ignore_index=True)
    table.attrs['gaps'] = gaps
    return table, fits


def _cache_key(path: Path, grid: float, include_terra: bool, min_modis_confidence: float) -> dict:
    stat = path.stat()
    return {'version': CACHE_VERSION, 'file': path.name, 'size': stat.st_size,
            'mtime_ns': stat.st_mtime_ns, 'grid': grid, 'include_terra': include_terra,
            'min_modis_confidence': min_modis_confidence}


def _read_cache(parquet: Path, meta: Path, key: dict) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not (parquet.exists() and meta.exists()):
        return None
    try:
        info = json.loads(meta.read_text(encoding='utf-8'))
        if info.get('key') != key:
            return None
        cells = pd.read_parquet(parquet)
        coverage = pd.DataFrame(info['coverage'], columns=['area', 'sensor', 'period'])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    coverage['period'] = pd.PeriodIndex(coverage['period'], freq='M')
    return cells, coverage


def cached_cells(paths, grid: float = 0.1, include_terra: bool = False, *,
                 min_modis_confidence: float = 30, cache_dir: Path = CACHE_DIR,
                 verbose: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Daily cell table and coverage for many CSVs, reading one CSV at a time.

    Each CSV is cleaned with load_hotspots and reduced to cell-days, then cached as
    <cache_dir>/<name>_g<grid>[_terra].parquet with a .json beside it holding the cache
    key (file size, modification time, settings) and the file's month coverage. A CSV
    is read again only when it or a setting changed. Returns (cells, coverage, number
    of files rebuilt); feed the first two to harmonize_cells.
    """
    from src.load_data import load_hotspots

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cell_parts, coverage_parts, rebuilt = [], [], 0
    for path in map(Path, paths):
        key = _cache_key(path, grid, include_terra, min_modis_confidence)
        stem = f"{path.stem}_g{grid:g}{'_terra' if include_terra else ''}"
        parquet, meta = cache_dir / f'{stem}.parquet', cache_dir / f'{stem}.json'
        cached = _read_cache(parquet, meta, key)
        if cached is None:
            df = load_hotspots([path], min_modis_confidence=min_modis_confidence, verbose=verbose)
            cells, coverage = _cell_days(df, grid, include_terra), _coverage(df)
            del df
            cells.to_parquet(parquet, index=False)
            meta.write_text(json.dumps({'key': key, 'coverage': [
                [str(a), str(s), str(p)] for a, s, p in coverage[['area', 'sensor', 'period']].itertuples(index=False)
            ]}), encoding='utf-8')
            rebuilt += 1
        else:
            cells, coverage = cached
        cell_parts.append(cells)
        coverage_parts.append(coverage)
    if not cell_parts:
        raise ValueError('no CSV files given')
    cells = pd.concat(cell_parts, ignore_index=True)
    cells['area'] = cells['area'].astype('string')
    cells['sensor'] = cells['sensor'].astype('string')
    cells['date'] = pd.to_datetime(cells['date'])
    if cells.duplicated(CELL_KEYS).any():  # the same area, sensor and day in two files
        cells = (cells.groupby(CELL_KEYS, sort=False)
                 .agg(detections=('detections', 'sum'), night=('night', 'sum'),
                      frp_max=('frp_max', 'max'), frp_sum=('frp_sum', 'sum')).reset_index())
    coverage = pd.concat(coverage_parts, ignore_index=True).drop_duplicates(ignore_index=True)
    return cells, coverage, rebuilt


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
    parser.add_argument('--cache-dir', type=Path, default=CACHE_DIR,
                        help='where the per-file cell-day cache lives (default: data/processed/cells)')
    parser.add_argument('--no-cache', action='store_true',
                        help='load every CSV at once instead of using the cache (needs much more memory)')
    args = parser.parse_args(argv)

    paths = _expand(args.paths)
    if not paths:
        parser.error('no CSV files found; download them with: python3 scripts/get_data.py')
    if args.no_cache:
        df = load_hotspots(paths, verbose=not args.quiet)
        table, fits = harmonize(df, grid=args.grid, include_terra=args.include_terra)
    else:
        cells, coverage, rebuilt = cached_cells(paths, args.grid, args.include_terra,
                                                cache_dir=args.cache_dir, verbose=not args.quiet)
        print(f'Cell-day cache: {rebuilt} of {len(paths)} file(s) read from CSV, '
              f'{len(paths) - rebuilt} from {args.cache_dir}')
        table, fits = harmonize_cells(cells, coverage)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out, index=False)
    by_year_out = args.out.with_name(f'{args.out.stem}_factors_by_year.csv')
    methods_out = args.out.with_name(f'{args.out.stem}_methods.csv')
    by_year, methods = fits.attrs['by_year'], fits.attrs['methods']
    by_year.to_csv(by_year_out, index=False)
    methods.to_csv(methods_out, index=False)

    sats = 'Aqua + Terra' if args.include_terra else 'Aqua'
    print(f'\nHarmonization: MODIS {sats} vs VIIRS Suomi-NPP, {args.grid} deg cell-days')
    print(f"{'area':<12} {'factor':>7} {'R2':>6} {'r':>6} {'median |%diff|':>15} {'months':>7}")
    for f in fits.itertuples():
        print(f'{f.area:<12} {f.factor:7.2f} {f.r2:6.2f} {f.pearson_r:6.2f} '
              f'{f.median_abs_pct_diff:14.1f}% {f.overlap_months:7d}')
    no_fit = fits.loc[fits['factor'].isna(), 'area'].tolist()
    if no_fit:
        print(f"\nNo factor for {', '.join(no_fit)}: needs months with both MODIS and VIIRS data "
              '(download both sensors for the same years). Months without VIIRS have no harmonized value.')
    gaps = table.attrs.get('gaps')
    if gaps is not None and len(gaps):
        for sensor, grp in gaps.groupby('sensor'):
            days = grp['date'].sort_values()
            print(f"\n{sensor.upper()} recorded nothing on {len(days)} day(s) while the other sensor saw fires "
                  f"({days.iloc[0]:%Y-%m-%d} .. {days.iloc[-1]:%Y-%m-%d}): left out of the fit"
                  + (', filled with MODIS x factor.' if sensor == 'viirs' else '.'))
    if len(by_year):
        print('\nFactor fitted on each year alone (is one factor per area stable?)')
        for area, grp in by_year.groupby('area'):
            vals = '  '.join(f'{int(r.year)} {r.factor:.2f}' for r in grp.itertuples() if pd.notna(r.factor))
            print(f'{area:<12} {vals}')
    if len(methods):
        print('\nSingle factor vs power law (median |%diff|: all / quiet / busy months; weighted |%diff|)')
        for r in methods.itertuples():
            print(f'{r.area:<12} {r.method:<7} {r.params:<16} {r.median_abs_pct_diff:6.1f}% '
                  f'{r.quiet_median_abs_pct_diff:6.1f}% {r.busy_median_abs_pct_diff:6.1f}%  '
                  f'weighted {r.weighted_abs_pct_diff:5.1f}%')
    print(f'\nWrote {len(table):,} area-months to {args.out}')
    print(f'Wrote the per-year factors to {by_year_out} and the method comparison to {methods_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
