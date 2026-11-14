"""Load FIRMS archive CSVs without harmonizing sensor confidence or counts."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

REQUIRED = {'latitude', 'longitude', 'acq_date', 'instrument', 'confidence', 'type'}


def load_hotspots(
    paths: str | Path | Iterable[str | Path], *,
    min_modis_confidence: float = 30, verbose: bool = True,
) -> pd.DataFrame:
    """Return clean detections; print exclusive rejection counts per source file.

    Keep type 0 (presumed vegetation fire), MODIS confidence in [cutoff, 100],
    and VIIRS nominal/high confidence. The cutoff is a project choice, not a
    calibration between sensors. No deduplication or monthly aggregation occurs.
    Input columns are retained, with normalized names and parsed coordinates/date.
    Adds source_file and area (from the country archive filename; otherwise NA).
    Detailed per-file reports are available in result.attrs['cleaning_reports'].
    """
    if not 0 <= min_modis_confidence <= 100:
        raise ValueError('min_modis_confidence must be between 0 and 100')
    if isinstance(paths, (str, Path)):
        paths = [paths]
    paths = list(paths)
    if not paths:
        raise ValueError('Provide at least one CSV file')
    frames, reports = [], []
    for item in paths:
        path = Path(item)
        df = pd.read_csv(path, dtype={'confidence': 'string', 'acq_time': 'string'})
        df.columns = df.columns.str.strip().str.lower()
        if df.columns.duplicated().any():
            raise ValueError(f'{path.name}: duplicate column names after normalization')
        missing = REQUIRED - set(df.columns)
        if missing:
            raise ValueError(f'{path.name}: missing required columns: {", ".join(sorted(missing))}')
        total = len(df)
        instrument = df['instrument'].astype('string').str.strip().str.upper()
        confidence = df['confidence'].astype('string').str.strip().str.lower()
        numeric_conf = pd.to_numeric(confidence, errors='coerce')
        lat = pd.to_numeric(df['latitude'], errors='coerce')
        lon = pd.to_numeric(df['longitude'], errors='coerce')
        dates = pd.to_datetime(df['acq_date'].astype('string').str.strip(),
                               format='%Y-%m-%d', errors='coerce')
        supported = instrument.isin(['MODIS', 'VIIRS'])
        modis = instrument.eq('MODIS').fillna(False)
        valid_conf = ((modis & numeric_conf.between(0, 100)) |
                      (instrument.eq('VIIRS') & confidence.isin(['l', 'n', 'h'])))
        low_conf = ((modis & numeric_conf.lt(min_modis_confidence)) |
                    (instrument.eq('VIIRS') & confidence.eq('l')))
        # First matching reason wins; counts therefore sum to total dropped.
        reasons = pd.Series('', index=df.index, dtype='string')
        checks = {
            'unsupported_instrument': ~supported,
            'invalid_coordinates': ~(lat.between(-90, 90) & lon.between(-180, 180)),
            'invalid_date': dates.isna(),
            'invalid_confidence': ~valid_conf,
            'low_confidence': low_conf,
            'non_vegetation_or_invalid_type': ~pd.to_numeric(df['type'], errors='coerce').eq(0),
        }
        for reason, mask in checks.items():
            reasons.loc[reasons.eq('') & mask.fillna(True)] = reason
        keep = reasons.eq('')
        df['latitude'], df['longitude'], df['acq_date'] = lat, lon, dates
        df['instrument'], df['confidence'] = instrument, confidence
        df['type'] = pd.to_numeric(df['type'], errors='coerce')
        df['source_file'] = path.name
        parts = path.stem.split('_', 2)
        df['area'] = parts[2].replace('_', ' ') if len(parts) == 3 and parts[1].isdigit() else pd.NA
        clean = df.loc[keep].copy()
        counts = {reason: int(reasons.eq(reason).sum()) for reason in checks}
        report = {'source_file': path.name, 'input_rows': total, 'kept_rows': len(clean),
                  'dropped_rows': total - len(clean), 'drop_reasons': counts}
        reports.append(report)
        frames.append(clean)
        if verbose:
            print(f'{path.name}: {total:,} read; {len(clean):,} kept; {total-len(clean):,} dropped')
            print('  ' + '; '.join(f'{key}={value:,}' for key, value in counts.items()))
    result = pd.concat(frames, ignore_index=True, sort=False)
    result.attrs['cleaning_reports'] = reports
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--min-modis-confidence', type=float, default=30)
    args = parser.parse_args()
    load_hotspots(args.paths, min_modis_confidence=args.min_modis_confidence)


if __name__ == '__main__':
    main()
