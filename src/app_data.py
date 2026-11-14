"""Where FireCal's data lives, and rebuilding the harmonized record when it is stale (US-09).

src/web_data.py uses these helpers so `python -m src.serve` rebuilds the page data only
when a CSV in data/ is newer than what was built last.
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
