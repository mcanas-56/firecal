"""Data loading for the app shell (US-09).

The app reads the harmonized monthly record from US-02. If it is missing, or any CSV in
data/ is newer than it, the record is rebuilt first, so `streamlit run src/app.py` is the
only command a teammate needs once the FIRMS files are downloaded.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """data/ in the repo, or FIRECAL_DATA_DIR (used by tests)."""
    return Path(os.environ.get('FIRECAL_DATA_DIR', ROOT / 'data'))


def monthly_path(folder: Path) -> Path:
    return folder / 'processed' / 'harmonized_monthly.csv'


def csv_inputs(folder: Path) -> list[Path]:
    return sorted(folder.glob('*.csv'))


def is_stale(out: Path, inputs: list[Path]) -> bool:
    if not out.exists():
        return True
    built = out.stat().st_mtime
    return any(p.stat().st_mtime > built for p in inputs)


def load_or_build_monthly(folder: Path, out: Path | None = None) -> tuple[pd.DataFrame | None, str]:
    """Return (monthly table, status). status: 'built', 'cached' or 'no_data'."""
    from src.harmonize import harmonize
    from src.load_data import load_hotspots

    out = out or monthly_path(folder)
    inputs = csv_inputs(folder)
    if not inputs:
        if out.exists():
            return pd.read_csv(out), 'cached'
        return None, 'no_data'
    if is_stale(out, inputs):
        table, _ = harmonize(load_hotspots(inputs, verbose=False))
        out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(out, index=False)
        return pd.read_csv(out), 'built'
    return pd.read_csv(out), 'cached'


def signature(folder: Path) -> tuple:
    """Changes whenever a data file is added, removed or modified (Streamlit cache key)."""
    files = csv_inputs(folder)
    out = monthly_path(folder)
    return tuple((p.name, p.stat().st_mtime, p.stat().st_size) for p in files) + (
        (out.name, out.stat().st_mtime) if out.exists() else ())
