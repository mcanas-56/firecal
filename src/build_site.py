"""Build the public FireCal website as plain files (for GitHub Pages).

    python -m src.build_site            # -> _site/
    python -m src.build_site --out public

Prepares the page data from data/*.csv with the same pipeline as `python -m src.serve`
(src/web_data.py: cleaning, harmonization, season, outlook), then copies web/ and the
generated data files (archive, monthly, outlook) into one folder that any static host can serve. The GitHub Actions workflow in
.github/workflows/pages.yml runs this and publishes the folder.

Preview the result locally:  python -m http.server --directory _site 8000
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.serve import GENERATED, WEB
from src.web_data import data_dir, ensure, web_dir

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / '_site'


def build_site(out: Path = DEFAULT_OUT, folder: Path | None = None, *, verbose: bool = True) -> dict:
    """Write the static site to `out`. Raises FileNotFoundError when there is no data."""
    folder = folder or data_dir()
    if ensure(folder, verbose=verbose) == 'no_data':
        raise FileNotFoundError(f'No FIRMS CSVs in {folder}. Download them with: python3 scripts/get_data.py')
    built = web_dir(folder)

    if out.exists():
        shutil.rmtree(out)
    # The "no data" placeholders are only for the local server before its first build.
    shutil.copytree(WEB, out, ignore=shutil.ignore_patterns('no-data', '.DS_Store'))
    for name in GENERATED:
        shutil.copy2(built / name, out / 'data' / name)
    (out / '.nojekyll').write_text('', encoding='utf-8')   # serve files as they are, no Jekyll step

    monthly = json.loads((out / 'data' / 'monthly.json').read_text(encoding='utf-8'))
    years = sorted({m['year'] for a in monthly['areas'].values() for m in a['months']})
    size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    report = {'out': str(out), 'areas': sorted(monthly['areas']),
              'years': f'{years[0]}-{years[-1]}' if years else '', 'mb': round(size / 1e6, 1)}
    if verbose:
        print(f"Site ready in {out}: {', '.join(report['areas'])}, {report['years']}, {report['mb']} MB")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the public FireCal website into one folder.')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='output folder (default: _site)')
    args = parser.parse_args(argv)
    try:
        build_site(args.out)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
