"""Download NASA FIRMS practice data into data/ (T-04).

Public yearly country CSVs from https://firms.modaps.eosdis.nasa.gov/country/ (no login).
Standard library only, works on macOS and Windows. Run from anywhere:

    python3 scripts/get_data.py                 # Windows: py -3 scripts\\get_data.py
    python3 scripts/get_data.py --years 2019-2023 --countries Canada
    python3 scripts/get_data.py --list          # show what would be downloaded

Files already downloaded (same size as on the server) are skipped, so re-running is cheap.
The data/ folder is gitignored: never commit these files.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
HEADERS = {"User-Agent": "firecal-get-data/1.0"}

DEFAULT_SENSORS = ["modis", "viirs-snpp"]
DEFAULT_YEARS = [2022, 2023]
DEFAULT_COUNTRIES = ["Canada", "Argentina"]
SENSOR_CHOICES = ["modis", "viirs-snpp", "viirs-jpss1", "viirs-jpss2"]
FIRST_YEAR = {"modis": 2000, "viirs-snpp": 2012, "viirs-jpss1": 2018, "viirs-jpss2": 2023}
REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "frp", "type"}


def parse_years(text: str) -> list[int]:
    years: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            years.extend(range(min(a, b), max(a, b) + 1))
        elif part:
            years.append(int(part))
    return sorted(set(years))


def file_name(sensor: str, year: int, country: str) -> str:
    return f"{sensor}_{year}_{country}.csv"


def url_for(sensor: str, year: int, country: str) -> str:
    return f"{BASE}/{sensor}/{year}/{file_name(sensor, year, country)}"


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            length = r.headers.get("Content-Length")
            return int(length) if length else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(url) from e
        return None
    except OSError:
        return None


def check_columns(path: Path) -> str | None:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        header = f.readline().strip().split(",")
    missing = REQUIRED_COLUMNS - set(header)
    return f"missing columns: {', '.join(sorted(missing))}" if missing else None


def download(sensor: str, year: int, country: str, force: bool, retries: int = 3) -> tuple[str, str, str]:
    """Returns (file name, status, detail); status is OK, SKIP or FAIL."""
    name = file_name(sensor, year, country)
    url = url_for(sensor, year, country)
    dest = DATA / name
    try:
        size = remote_size(url)
    except FileNotFoundError:
        return name, "FAIL", "not on the FIRMS server (check the country spelling, e.g. United_States, and the year)"

    if dest.exists() and not force:
        local = dest.stat().st_size
        if (size is not None and local == size) or (size is None and local > 0):
            return name, "SKIP", f"already have it ({local / 1e6:.1f} MB)"

    part = dest.with_suffix(".csv.part")
    last_error = ""
    for attempt in range(1, retries + 1):
        start = time.time()
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
            got = part.stat().st_size
            if size is not None and got != size:
                raise OSError(f"incomplete download ({got} of {size} bytes)")
            problem = check_columns(part)
            if problem:
                part.unlink(missing_ok=True)
                return name, "FAIL", problem
            part.replace(dest)
            secs = time.time() - start
            return name, "OK", f"{got / 1e6:.1f} MB in {secs:.0f}s"
        except ssl.SSLError as e:
            part.unlink(missing_ok=True)
            hint = (" On macOS with the python.org installer, run 'Install Certificates.command' "
                    "from your Applications/Python folder, then try again.") if sys.platform == "darwin" else ""
            return name, "FAIL", f"SSL error: {e.reason}.{hint}"
        except (OSError, urllib.error.URLError) as e:
            last_error = str(getattr(e, "reason", e))
            part.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(2 * attempt)
    return name, "FAIL", f"{last_error} (after {retries} tries; check your internet connection and run again)"


def main() -> int:
    p = argparse.ArgumentParser(description="Download NASA FIRMS practice CSVs into data/")
    p.add_argument("--years", default=",".join(map(str, DEFAULT_YEARS)),
                   help="years, e.g. 2023 or 2019-2023 or 2012,2023 (default: %(default)s)")
    p.add_argument("--countries", default=",".join(DEFAULT_COUNTRIES),
                   help="FIRMS country names, comma separated; spaces become underscores (default: %(default)s)")
    p.add_argument("--sensors", default=",".join(DEFAULT_SENSORS),
                   help=f"any of {', '.join(SENSOR_CHOICES)} (default: %(default)s)")
    p.add_argument("--force", action="store_true", help="download again even if the file exists")
    p.add_argument("--list", action="store_true", help="only list the files and URLs")
    p.add_argument("--workers", type=int, default=4, help="parallel downloads (default: %(default)s)")
    args = p.parse_args()

    years = parse_years(args.years)
    countries = [c.strip().replace(" ", "_") for c in args.countries.split(",") if c.strip()]
    sensors = [s.strip() for s in args.sensors.split(",") if s.strip()]
    bad = [s for s in sensors if s not in SENSOR_CHOICES]
    if bad:
        p.error(f"unknown sensor(s): {', '.join(bad)}. Choose from {', '.join(SENSOR_CHOICES)}")

    jobs, skipped_years = [], []
    for s in sensors:
        for y in years:
            if y < FIRST_YEAR[s]:
                skipped_years.append(f"{s} {y}")
                continue
            for c in countries:
                jobs.append((s, y, c))
    if skipped_years:
        print("Not available (before the sensor launched): " + ", ".join(skipped_years))
    if not jobs:
        print("Nothing to download.")
        return 1

    if args.list:
        for s, y, c in jobs:
            print(url_for(s, y, c))
        return 0

    DATA.mkdir(exist_ok=True)
    print(f"Downloading {len(jobs)} file(s) from NASA FIRMS into {DATA}\n", flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(download, s, y, c, args.force) for s, y, c in jobs]
        for fut in cf.as_completed(futures):
            name, status, detail = fut.result()
            results.append((name, status, detail))
            print(f"[{status:<4}] {name} - {detail}", flush=True)

    failed = [r for r in results if r[1] == "FAIL"]
    total_mb = sum((DATA / n).stat().st_size for n, s, _ in results if s != "FAIL") / 1e6
    print(f"\n{len(results) - len(failed)} of {len(results)} file(s) ready in data/ ({total_mb:.0f} MB).")
    if failed:
        print("RESULT: FAIL. Fix the problems above and run again; finished files are kept.")
        return 1
    print("RESULT: PASS. Mark 'Data' Done in your Machine readiness row. Never commit data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
