"""Build the data the FireCal page reads, from our own pipeline.

    python -m src.web_data          # rebuild now (src.serve does this for you on start)

Reads data/*.csv once with load_hotspots (US-01), harmonizes it (US-02) and summarizes
the season (US-05), then writes to data/processed/ (local, gitignored):

- harmonized_monthly.csv  the US-02 table (same file `python -m src.harmonize` writes)
- web/archive.json        daily detections for the calendar, globe and timeline:
                          date -> area -> {total, frp, points: [[lat, lon, frp]]}
- web/monthly.json        per area: harmonized monthly record, MODIS->VIIRS fit,
                          season summary, and which sensor the daily view uses
- web/outlook.json        the globe's Outlook mode (US-18, src/outlook.py): next
                          month's outlook, 2022-2023 back-tests and model skill

Daily view: cleaned VIIRS Suomi-NPP detections where a VIIRS S-NPP file covers that
area and year (finer pixels, same satellite the harmonization is calibrated to),
otherwise MODIS. A yearly country file covers every day of its year, so a covered day
with no detections is 0; days no file covers are absent (shown as "no data").
Satellite gaps come from the harmonization (src/harmonize.sensor_gaps): days a sensor
recorded nothing while the other saw fires (e.g. Suomi NPP was offline 27 Jul-10 Aug
2022). The daily view shows those days as no data, not as fire-free days.
Harmonization is monthly by design, so the month x year view and the season summary
use the harmonized record.
"""
from __future__ import annotations

import argparse
import hashlib
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
from src.outlook import run_outlook
from src.season_summary import summarize_season

# Code that shapes the page data. Editing any of these (after a git pull, say) makes the
# next `python -m src.serve` rebuild, so every laptop shows what the current code computes.
PIPELINE_FILES = ('load_data.py', 'harmonize.py', 'season_summary.py', 'web_data.py', 'app_data.py',
                  'features.py', 'predict.py', 'outlook.py')   # the outlook's code (US-18) too
POINTS_PER_DAY = 60          # sampled globe markers per area and day (counts use every detection)
SENSOR_LABEL = {'viirs': 'VIIRS S-NPP', 'modis': 'MODIS'}


def pipeline_version() -> str:
    """Fingerprint of the pipeline code (line endings ignored, so Windows checkouts match)."""
    h = hashlib.sha256()
    src = Path(__file__).resolve().parent
    for name in PIPELINE_FILES:
        h.update(name.encode())
        h.update((src / name).read_bytes().replace(b'\r\n', b'\n'))
    return h.hexdigest()[:16]


def web_dir(folder: Path) -> Path:
    return folder / 'processed' / 'web'


def outputs(folder: Path) -> list[Path]:
    return [web_dir(folder) / 'archive.json', web_dir(folder) / 'monthly.json', monthly_path(folder),
            web_dir(folder) / 'outlook.json']


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


def apply_gaps(archive: dict, chosen: dict[tuple[str, int], dict], gaps: pd.DataFrame) -> dict[str, list[str]]:
    """Remove days the daily view's sensor was not recording; returns {year: [days]}."""
    out: dict[str, list[str]] = {}
    gap_set = {(r.sensor, r.date.strftime('%Y-%m-%d')) for r in gaps.itertuples(index=False)}
    for (area, year), pick in chosen.items():
        for day, by_area in archive.items():
            if day.startswith(str(year)) and (pick['sensor'], day) in gap_set and area in by_area:
                del by_area[area]
                out.setdefault(str(year), [])
                if day not in out[str(year)]:
                    out[str(year)].append(day)
    return {y: sorted(d) for y, d in sorted(out.items())}


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
                   | {'overlap_months': int(fit.get('overlap_months', 0) or 0),
                      'gap_days': int(fit.get('gap_days', 0) or 0)},
            'months': [{'year': int(r.year), 'month': int(r.month),
                        'modis': _num(r.modis_cell_days), 'viirs': _num(r.viirs_cell_days),
                        'harmonized': _num(r.harmonized, 1), 'source': str(r.source),
                        'viirs_gap_days': int(r.viirs_gap_days)}
                       for r in grp.itertuples()],
            'season': {'status': season.status, 'years': list(season.years),
                       'start': season.start_month, 'peak': season.peak_month, 'end': season.end_month,
                       'months': list(season.season_months), 'threshold': season.threshold_fraction},
            'daily_sensor': {str(y): SENSOR_LABEL[p['sensor']] for (a, y), p in sorted(chosen.items()) if a == area},
        }
    return {'built': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'pipeline': pipeline_version(),
            'files': [p.name for p in files], 'daily_gaps': gaps or {}, 'areas': areas}


def build(folder: Path | None = None, *, verbose: bool = True) -> dict:
    """Load, clean, harmonize and write every output. Returns a small report."""
    folder = folder or data_dir()
    files = csv_inputs(folder)
    if not files:
        raise FileNotFoundError(f'No FIRMS CSVs in {folder}')
    t0 = time.time()
    out = web_dir(folder)
    # The outlook first, in its own process: it works from the small cell cache and
    # hands its memory back before the full detection table is loaded below.
    outlook = run_outlook(files, out / 'outlook.json', folder / 'processed' / 'cells', verbose=verbose)
    df = load_hotspots(files, verbose=False)
    table, fits = harmonize(df)
    chosen = daily_files(files)
    archive = daily_archive(df, chosen)
    gaps = apply_gaps(archive, chosen, table.attrs.get('gaps', pd.DataFrame(columns=['sensor', 'date'])))
    summary = monthly_summary(table, fits, chosen, files, gaps)

    monthly_path(folder).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(monthly_path(folder), index=False)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'archive.json').write_text(json.dumps(archive, separators=(',', ':')), encoding='utf-8')
    (out / 'monthly.json').write_text(json.dumps(summary, separators=(',', ':')), encoding='utf-8')
    report = {'files': len(files), 'detections': int(len(df)), 'days': len(archive),
              'gap_days': sum(len(v) for v in gaps.values()), 'areas': sorted(summary['areas'])}
    report['outlook'] = outlook.get('status')
    report['seconds'] = round(time.time() - t0, 1)
    if verbose:
        print(f"Built FireCal data from {report['files']} files: {report['detections']:,} detections, "
              f"{report['days']} days, {', '.join(report['areas'])}, {report['gap_days']} satellite-gap days, "
              f"outlook {report['outlook']} ({report['seconds']}s)")
    return report


def _built_with(folder: Path) -> dict:
    try:
        meta = json.loads((web_dir(folder) / 'monthly.json').read_text(encoding='utf-8'))
        return {'pipeline': meta.get('pipeline'), 'files': sorted(meta.get('files', []))}
    except (OSError, ValueError):
        return {}


def why_rebuild(folder: Path, files: list[Path]) -> str | None:
    """Reason the page data is out of date, or None when it is current."""
    if not all(p.exists() for p in outputs(folder)):
        return 'first build'
    built = _built_with(folder)
    if built.get('pipeline') != pipeline_version():
        return 'the FireCal code changed'
    if built.get('files') != sorted(p.name for p in files):
        return 'data files were added or removed'
    if any(is_stale(p, files) for p in outputs(folder)):
        return 'a data file changed'
    return None


def ensure(folder: Path | None = None, *, verbose: bool = True) -> str:
    """Rebuild when the data is missing or out of date (new or changed CSVs, or new pipeline
    code after a git pull). Returns 'built', 'cached' or 'no_data'."""
    folder = folder or data_dir()
    files = csv_inputs(folder)
    if not files:
        return 'cached' if all(p.exists() for p in outputs(folder)[:2]) else 'no_data'
    reason = why_rebuild(folder, files)
    if reason:
        if verbose:
            print(f'Preparing FireCal data from data/*.csv ({reason}; about a minute for 2012-2023)...', flush=True)
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
        print(f'{exc}. Download the data (2012-2023) with: python3 scripts/get_data.py')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
