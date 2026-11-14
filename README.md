# FireCal

A fire-season calendar built from NASA FIRMS MODIS and VIIRS hotspot data — Team Lanesra, NASA Space Apps Challenge (COM805).

## Project structure

```
firecal/
├── data/        Raw NASA FIRMS CSVs (gitignored — download locally, never commit)
├── src/         App and data-processing code (entry point: src/app.py; colours in src/palette.py)
├── docs/        Design notes (calendar wireframe and palette: docs/t-03-calendar-design.md)
├── notebooks/   Exploration notebooks
├── tests/       Tests
├── scripts/     setup.sh (macOS) / setup.ps1 (Windows), the setup engine, get_data.py
├── .claude/     Shared Claude Code commands (/setup)
├── AGENTS.md    Project context and rules for coding agents (Codex reads it)
├── CLAUDE.md    Imports AGENTS.md for Claude Code
└── requirements.txt
```

## Setup (once per laptop)

You need Git, Python 3.11+, and an editor (VS Code recommended).

### Quick way: one setup script

Clone the repo (step 1 below), then either:

- **Claude Code:** open it in the `firecal` folder and type `/setup`.
- **Codex:** open it in the `firecal` folder and ask it to "set up my environment".
- **Yourself, in a terminal:** `bash scripts/setup.sh` on macOS, or on Windows `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`.

All three run the same script. It checks Git and Python, creates `.venv`, installs the packages, starts the app for a few seconds to prove it works, and tells you which Machine readiness cells to mark Done. Approve the commands your agent asks to run.

### By hand

1. Clone the repo:

   ```bash
   git clone git@github.com:mcanas-56/firecal.git
   cd firecal
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # macOS / Linux
   .venv\Scripts\activate           # Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Download the practice data (see below).

## Practice data

The app reads NASA FIRMS hotspot CSVs from `data/`. Download the practice set (MODIS + VIIRS Suomi-NPP, 2022–2023, Canada + Argentina: 8 files, about 230 MB) straight from NASA with:

```bash
python3 scripts/get_data.py          # Windows: py -3 scripts\get_data.py
```

`/setup` (or Codex setup) offers to run this for you. Running it again only downloads what's missing. Change the set with flags, for example `--years 2012-2023`, `--countries Canada`, `--sensors modis,viirs-snpp,viirs-jpss1`; `--list` shows the files without downloading.

The files are public ([FIRMS country yearly data](https://firms.modaps.eosdis.nasa.gov/country/), no login) and stay on your laptop: `data/` is gitignored, and GitHub rejects files over 100 MB anyway. At the event, NASA's official datasets also go in `data/`.

## Run the app

With the virtual environment active, from the repo root:

```bash
streamlit run src/app.py
```

The app opens in your browser at http://localhost:8501. Stop it with `Ctrl+C` in the terminal.

On first run (or after you add or change files in `data/`) the app rebuilds the harmonized monthly record from `data/*.csv` itself, which takes a few seconds; you don't need to run `python -m src.harmonize` first. With no data it shows the download command. The page follows the T-03 layout: season summary, monthly activity for Canada (placeholder until the US-04 calendar) and slots for the tasks still to come.

Each time you open a new terminal, activate the environment again (`source .venv/bin/activate`) before running the app.

Tested setup: Python 3.13.1, pandas 3.1.1, streamlit 1.67.0 (macOS). If the page says "If you can see this, your setup works.", you're ready.

### Troubleshooting

- `streamlit: command not found` → the virtual environment isn't active; run `source .venv/bin/activate`.
- `Port 8501 is already in use` → another Streamlit is running; stop it, or run `streamlit run src/app.py --server.port 8502`.
- `python3: command not found` (Windows) → use `python` or `py` instead of `python3`.

## How we work

- **Never commit straight to `main`.** One feature branch per task, named by task ID:

  ```bash
  git checkout main && git pull
  git checkout -b us-04-heatmap
  ```

- Hand the task spec to Claude Code on your branch, then review and test the output against the acceptance criteria.
- Push your branch and open a pull request. One other teammate reviews it before it merges to `main`.
- **Definition of Done:** acceptance criteria pass on Canada and Argentina, tested on a second laptop, reviewed and merged, README updated.

## Load and clean hotspots (US-01)

From the repo root, with `.venv` activated:

```bash
python -m src.load_data data/modis_2022_Canada.csv data/viirs-snpp_2022_Canada.csv
python -m unittest discover -s tests -v
```

In Python:

```python
from pathlib import Path
from src.load_data import load_hotspots

clean = load_hotspots(sorted(Path('data').glob('*.csv')))
reports = clean.attrs['cleaning_reports']
```

The loader returns one dataframe with normalized lowercase column names, numeric
coordinates, parsed `acq_date`, normalized `instrument` and original sensor-scale
`confidence` values stored as strings. Other input columns are retained (sensor-only
columns are null for the other sensor). `source_file` records provenance; `area`
comes from the downloader's `<sensor>_<year>_<country>.csv` naming convention,
otherwise it is missing. Pass explicit paths; the loader does not download data.

Cleaning rejects unsupported instruments, missing/non-numeric/out-of-range
coordinates, invalid or missing dates, invalid confidence, low confidence, and
non-vegetation or missing/invalid `type`, in that order. Only `type=0` (presumed
vegetation fire) is kept, excluding industrial sources, volcanoes and offshore
anomalies. Each rejected row receives its first matching reason so per-file drop
counts add up exactly. Reports print by default; use `verbose=False` to suppress.
Missing required columns raise a descriptive error, rather than silently losing a
whole file. Required: latitude, longitude, acq_date, instrument, confidence, type.

The default MODIS cutoff is **30** (inclusive, valid range 0–100); this is an
explicit project filtering choice, configurable with `min_modis_confidence` or
`--min-modis-confidence`. VIIRS keeps `n` and `h`, following the confidence-filtering
example in [NASA's FIRMS tutorial](https://firms.modaps.eosdis.nasa.gov/content/academy/data_ingest/firms_data_ingest.html).
No conversion between the sensors' confidence scales is claimed. Acquisition time
is preserved as text; this task validates acquisition dates only. No deduplication,
monthly aggregation, confidence calibration or inference about burned area occurs;
harmonization belongs to US-02.

## Harmonize into one monthly record (US-02)

From the repo root, with `.venv` activated and the practice data in `data/`:

```bash
python -m src.harmonize data/*.csv
```

This runs the US-01 loader, then turns MODIS Aqua and VIIRS Suomi-NPP detections into fire cell-days (each 0.1° grid cell counted once per day per sensor), sums them by month, fits one VIIRS/MODIS factor per area on the overlap months, and writes `data/processed/harmonized_monthly.csv` (one row per area-month, local only). It prints the factor, R², Pearson r and median % difference per area. Options: `--grid 0.25`, `--include-terra`, `--out path.csv`, `--quiet`.

In Python:

```python
from pathlib import Path
from src.load_data import load_hotspots
from src.harmonize import harmonize

table, fits = harmonize(load_hotspots(sorted(Path('data').glob('*.csv')), verbose=False))
```

Method, results and limits: [docs/harmonization.md](docs/harmonization.md).

## Fire-season summary (US-05)

Build the monthly record and start the app from the repository root:

```bash
python -m src.harmonize "data/*.csv"
streamlit run src/app.py
```

Choose Canada or Argentina to update the **Start**, **Peak**, and **End** metrics.
The app reads `data/processed/harmonized_monthly.csv`; if missing, it displays the
build command. Rebuild that file after changing raw inputs. Processed data stays
local and gitignored. The reusable UI function is `render_season_summary(monthly)`
in `src/season_summary.py`, ready for integration into the US-09 app shell.

In Python, call `summarize_season(monthly, area, threshold_fraction=0.2)` with the
US-02 table (`area`, `year`, `month`, `harmonized`). It returns a `SeasonSummary`
containing the status, included years, numbered start/peak/end months, and ordered
season months. This summarizes the available years, not an individual year.

Method: use only complete years with 12 non-missing monthly values, average each
calendar month's harmonized activity across those years, and select the largest
mean as the peak (ties choose the earliest calendar month). Starting at that peak,
walk both ways through consecutive months reaching **20% of the peak mean**,
including equality and wrapping December–January. This threshold is an explicit
project heuristic, configurable in the calculation API, not an official season
boundary. Disconnected secondary seasons are excluded. If all months qualify,
report January–December and label the activity year-round. All-zero data has no
estimated season. Missing months are never interpreted as zeros; without a
complete year the UI reports insufficient coverage instead of invented dates.
Negative/nonfinite values, duplicate month keys and invalid month/year fields
raise descriptive errors. Only the selected area's records are evaluated.

These are descriptive activity estimates, not forecasts or burned-area estimates.
The practice data covers just 2022–2023, so results are not a long-term climate
baseline. Teammate review and testing on a second laptop remain required.

## Calendar view (US-04a)

`src/calendar_view.py` draws the month × year calendar from the T-03 wireframe as HTML: one row per year (newest first), one column per month, cells coloured with `src/palette.py` on its log scale, peak cells labelled (`16.6k`), a tooltip on every cell, a legend, and optional outlines for unusual years.

```python
from src.calendar_view import calendar_html, sample_monthly

st.html(calendar_html(sample_monthly('Canada'), flags={2023: 'high', 2020: 'low'}))
```

The app currently shows it with **sample values** (`sample_monthly`) so the team can agree the layout. US-04 passes the real harmonized rows for the selected area instead: `calendar_html(monthly[monthly.area == area])`.
