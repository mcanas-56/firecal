"""Build the data the FireCal page reads, from our own pipeline.

    python -m src.web_data          # rebuild now (src.serve does this for you on start)

Reads data/*.csv once with load_hotspots (US-01), harmonizes it (US-02) and summarizes
the season (US-05), then writes to data/processed/ (local, gitignored):

- harmonized_monthly.csv  the US-02 table (same file `python -m src.harmonize` writes)
- web/archive.json        daily detections for the calendar, globe and timeline:
                          date -> area -> {total, frp, points: [[lat, lon, frp]]}
- web/monthly.json        per area: harmonized monthly record, MODIS->VIIRS fit,
                          season summary, and which sensor the daily view uses

Daily view: cleaned VIIRS Suomi-NPP detections where a VIIRS S-NPP file covers that
area and year (finer pixels, same satellite the harmonization is calibrated to),
otherwise MODIS. A yearly country file covers every day of its year, so a covered day
with no detections is 0; days no file covers are absent (shown as "no data").
Satellite gaps: a day on which none of the downloaded areas has a single detection from
that sensor is treated as missing data (e.g. Suomi NPP was offline 27 Jul-10 Aug 2022),
not as a fire-free day. This needs at least two areas, since one quiet area proves nothing.
Harmonization is monthly by design, so the month x year view and the season summary
use the harmonized record.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.app_data import csv_inputs, data_dir, is_stale, monthly_path
from src.harmonize import FILE_PATTERN, harmonize
from src.load_data import load_hotspots
from src.season_summary import summarize_season

POINTS_PER_DAY = 60          # sampled globe markers per area and day (counts use every detection)
SENSOR_LABEL = {'viirs': 'VIIRS S-NPP', 'modis': 'MODIS'}


def web_dir(folder: Path) -> Path:
    return folder / 'processed' / 'web'


def outputs(folder: Path) -> list[Path]:
    return [web_dir(folder) / 'archive.json', web_dir(folder) / 'monthly.json', monthly_path(folder)]


def _file_info(path: Path) -> dict | None:
    """sensor, year and area from a FIRMS yearly country file name (modis_2023_Canada.csv)."""
    m = FILE_PATTERN.match(path.name)
    parts = path.stem.split('_', 2)
    if not m or len(parts) < 3:
        return None
    return dict(name=path.name, sensor=m['sensor'].lower(), year=int(m['year']),
                area=parts[2].replace('_', ' '), snpp=path.name.lower().startswith('viirs-snpp'))


def daily_files(paths: list[Path]) -> dict[tuple[str, int], dict]:
    """(area, year) -> {sensor, files}: VIIRS S-NPP files when present, else MODIS."""
    by_key: dict[tuple[str, int], list[dict]] = {}
    for info in filter(None, map(_file_info, paths)):
        by_key.setdefault((info['area'], info['year']), []).append(info)
    chosen = {}
    for key, infos in by_key.items():
        viirs = [i for i in infos if i['sensor'] == 'viirs' and i['snpp']]
        modis = [i for i in infos if i['sensor'] == 'modis']
        pick, sensor = (viirs, 'viirs') if viirs else (modis, 'modis')
        if pick:
            chosen[key] = dict(sensor=sensor, files={i['name'] for i in pick})
    return chosen


def _sample(points: np.ndarray, n: int = POINTS_PER_DAY) -> np.ndarray:
    """Evenly spaced rows, so the same data always gives the same markers."""
    if len(points) <= n:
        return points
    return points[np.linspace(0, len(points) - 1, n).round().astype(int)]


def daily_archive(df: pd.DataFrame, chosen: dict[tuple[str, int], dict]) -> dict:
    archive: dict[str, dict] = {}
    frp = pd.to_numeric(df.get('frp', pd.Series(np.nan, index=df.index)), errors='coerce').fillna(0.0)
    d = pd.DataFrame({'area': df['area'].astype('string'), 'source_file': df['source_file'],
                      'date': df['acq_date'].dt.strftime('%Y-%m-%d'),
                      'lat': df['latitude'].round(4), 'lon': df['longitude'].round(4), 'frp': frp.round(2)})
    for (area, year), pick in sorted(chosen.items()):
        rows = d[(d['area'] == area) & d['source_file'].isin(pick['files'])
                 & d['date'].str.startswith(str(year))].sort_values(['date', 'lat', 'lon'])
        groups = {day: g for day, g in rows.groupby('date')}
        day = date(year, 1, 1)
        while day.year == year:
            key = day.isoformat()
            g = groups.get(key)
            if g is None:
                entry = {'total': 0, 'frp': 0.0, 'points': []}
            else:
                pts = _sample(g[['lat', 'lon', 'frp']].to_numpy())
                entry = {'total': int(len(g)), 'frp': round(float(g['frp'].sum()), 2),
                         'points': [[float(a), float(b), float(c)] for a, b, c in pts]}
            archive.setdefault(key, {})[area] = entry
            day += timedelta(days=1)
    return dict(sorted(archive.items()))


def sensor_gaps(archive: dict, chosen: dict[tuple[str, int], dict]) -> dict[str, list[str]]:
    """{year: [days]} where every area using the same daily files/sensor recorded nothing."""
    gaps: dict[str, list[str]] = {}
    years = {y for _, y in chosen}
    for year in sorted(years):
        for sensor in ('viirs', 'modis'):
            areas = [a for (a, y), p in chosen.items() if y == year and p['sensor'] == sensor]
            if len(areas) < 2:
                continue
            for day, by_area in archive.items():
                if day.startswith(str(year)) and all(by_area.get(a, {}).get('total', 1) == 0 for a in areas):
                    gaps.setdefault(str(year), []).append(day)
                    for a in areas:
                        by_area.pop(a, None)          # absent = no data
    return gaps


def _num(x, digits: int | None = None):
    """JSON-safe number: NaN / NA -> None."""
    if x is None or pd.isna(x):
        return None
    x = float(x)
    if not math.isfinite(x):
        return None
    return round(x, digits) if digits is not None else x


def monthly_summary(table: pd.DataFrame, fits: pd.DataFrame, chosen: dict, files: list[Path],
                    gaps: dict[str, list[str]] | None = None) -> dict:
    areas = {}
    fit_by_area = fits.set_index('area').to_dict('index') if len(fits) else {}
    for area, grp in table.groupby('area'):
        season = summarize_season(table, area)
        fit = fit_by_area.get(area, {})
        areas[area] = {
            'fit': {k: _num(fit.get(k), 4) for k in ('factor', 'r2', 'pearson_r', 'median_abs_pct_diff')}
                   | {'overlap_months': int(fit.get('overlap_months', 0) or 0)},
            'months': [{'year': int(r.year), 'month': int(r.month),
                        'modis': _num(r.modis_cell_days), 'viirs': _num(r.viirs_cell_days),
                        'harmonized': _num(r.harmonized, 1), 'source': str(r.source)}
                       for r in grp.itertuples()],
            'season': {'status': season.status, 'years': list(season.years),
                       'start': season.start_month, 'peak': season.peak_month, 'end': season.end_month,
                       'months': list(season.season_months), 'threshold': season.threshold_fraction},
            'daily_sensor': {str(y): SENSOR_LABEL[p['sensor']] for (a, y), p in sorted(chosen.items()) if a == area},
        }
    return {'built': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'files': [p.name for p in files], 'daily_gaps': gaps or {}, 'areas': areas}


def build(folder: Path | None = None, *, verbose: bool = True) -> dict:
    """Load, clean, harmonize and write every output. Returns a small report."""
    folder = folder or data_dir()
    files = csv_inputs(folder)
    if not files:
        raise FileNotFoundError(f'No FIRMS CSVs in {folder}')
    t0 = time.time()
    df = load_hotspots(files, verbose=False)
    table, fits = harmonize(df)
    chosen = daily_files(files)
    archive = daily_archive(df, chosen)
    gaps = sensor_gaps(archive, chosen)
    summary = monthly_summary(table, fits, chosen, files, gaps)

    monthly_path(folder).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(monthly_path(folder), index=False)
    out = web_dir(folder)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'archive.json').write_text(json.dumps(archive, separators=(',', ':')), encoding='utf-8')
    (out / 'monthly.json').write_text(json.dumps(summary, separators=(',', ':')), encoding='utf-8')
    report = {'files': len(files), 'detections': int(len(df)), 'days': len(archive),
              'gap_days': sum(len(v) for v in gaps.values()),
              'areas': sorted(summary['areas']), 'seconds': round(time.time() - t0, 1)}
    if verbose:
        print(f"Built FireCal data from {report['files']} files: {report['detections']:,} detections, "
              f"{report['days']} days, {', '.join(report['areas'])}, {report['gap_days']} satellite-gap days "
              f"({report['seconds']}s)")
    return report


def ensure(folder: Path | None = None, *, verbose: bool = True) -> str:
    """Rebuild when outputs are missing or a CSV is newer. Returns 'built', 'cached' or 'no_data'."""
    folder = folder or data_dir()
    files = csv_inputs(folder)
    if not files:
        return 'cached' if all(p.exists() for p in outputs(folder)[:2]) else 'no_data'
    if any(is_stale(p, files) for p in outputs(folder)):
        if verbose:
            print('Preparing FireCal data from data/*.csv (takes a few seconds)...', flush=True)
        build(folder, verbose=verbose)
        return 'built'
    return 'cached'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the FireCal page data from data/*.csv.')
    parser.add_argument('--data', type=Path, default=None, help='folder with FIRMS CSVs (default data/)')
    args = parser.parse_args(argv)
    try:
        build(args.data)
    except FileNotFoundError as exc:
        print(f'{exc}. Download the practice set with: python3 scripts/get_data.py')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
