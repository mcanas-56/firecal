# FireCal

A fire-season calendar built from NASA FIRMS MODIS and VIIRS hotspot data — Team Lanesra, NASA Space Apps Challenge (COM805).

## Project structure

```
firecal/
├── data/        Raw NASA FIRMS CSVs (gitignored — download locally, never commit)
├── web/         The FireCal page (HTML, CSS, js/ by feature, bundled D3 and land map, data/archive.json)
├── src/         Data pipeline (load, harmonize, features, outlook models, season, page data) and the local server (src/serve.py)
├── design/      The firecal-demo prototype and its screenshots: the design source of truth (T-05)
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

4. Setup also downloads the data (see below); add `--skip-data` to skip it.

## Data

The app reads NASA FIRMS hotspot CSVs from `data/`. Download the record (MODIS + VIIRS Suomi-NPP, 2012–2023, Canada + Argentina: 48 files, about 740 MB, a few minutes) straight from NASA with:

```bash
python3 scripts/get_data.py          # Windows: py -3 scripts\get_data.py
```

Setup runs this for you (unless `--skip-data`). Running it again only downloads what's missing, so if you already have the old 2022–2023 practice set, just run it again to add 2012–2021; the setup check warns while any of the 48 files are missing. Change the set with flags, for example `--years 2022-2023` for a quick small set, `--countries Canada`, `--sensors modis,viirs-snpp,viirs-jpss1`; `--list` shows the files without downloading.

The files are public ([FIRMS country yearly data](https://firms.modaps.eosdis.nasa.gov/country/), no login) and stay on your laptop: `data/` is gitignored, and GitHub rejects files over 100 MB anyway. At the event, NASA's official datasets also go in `data/`.

## Run the app

From the repo root:

```bash
python -m src.serve        # Windows: py -3 -m src.serve
```

That's the only command. It:

1. prepares the data from `data/*.csv` with our pipeline: cleans the hotspots (US-01), harmonizes MODIS and VIIRS into one monthly record (US-02), estimates the fire season (US-05) and fits the fire outlook (US-18). This takes about a minute the first time for the full 2012–2023 set, and runs again only when the data files or the pipeline code change (for example after a `git pull`). The results go to `data/processed/` (local, gitignored).
2. serves the page at http://localhost:8000 (the next free port if 8000 is taken) and opens your browser. Stop it with `Ctrl+C`.

Options: `--port 8080`, `--no-browser`, `--skip-build` (serve the last build). `python -m src.web_data` rebuilds the data without starting the server. With no data yet, the page shows the download command.

### What's on the page

- **Fire activity ticker:** the scrolling bar under the header. For the selected date or period it shows, per area, the activity level (calendar colours) and detections, the fire-season status, and the harmonized month vs the same month in another year. Real data only; hover or ⏸ pauses it.
- **Area switch** (US-03): Canada | Argentina, plus any other country you download. It drives every section and is kept in the address (`?area=Argentina`).
- **Live view / Past data:** the switch above the globe. Past data (default) explores the archive. Live view is in the MVP as "coming soon": it will show near-real-time NASA FIRMS hotspots from the last 24 hours once a live feed is connected, and shows no invented data until then.
- **Globe:** where the hotspots were, coloured by radiative power. Drag, zoom, reset; at most 300 markers.
- **Time explorer:** Days / Weeks / Months, with a play button.
- **Stat cards:** detections, observation window, harmonized activity for the month.
- **Fire activity calendar:** one month at a time, every day coloured by its number of hotspot detections. Uses cleaned VIIRS Suomi-NPP detections (MODIS for years without VIIRS). Colours are quartiles of the non-zero days for the selected area and year. Pick the year next to the month; click a day to jump to it on the globe.
- **Fire season** (US-05): start, peak and end month from the harmonized record.
- **Month × year calendar** (US-04): harmonized fire cell-days for every month. Tooltips show the VIIRS and MODIS values; click a month to open it in the daily calendar.
- **Dark and light themes.**
- **Report a fire:** marked "coming soon"; the form is disabled and sends nothing.

The design comes from the firecal-demo prototype in `design/` (T-05). Everything runs offline except the two web fonts, which fall back to system fonts.

Tested setup: Python 3.13.1, pandas 3.1.1, pyarrow 26.0.1 (macOS).

### Troubleshooting

- The page says "No fire data on this laptop yet" → run `python3 scripts/get_data.py`, then start FireCal again.
- `No module named pandas` → set up first (`bash scripts/setup.sh`), or activate `.venv` and use its Python.
- `python3: command not found` (Windows) → use `py -3` instead.

## Public website (GitHub Pages)

FireCal is published at **https://mcanas-56.github.io/firecal/**. Every push to `main` (so every merged pull request) runs `.github/workflows/pages.yml`, which:

1. downloads the NASA FIRMS CSVs (cached between runs, so NASA is only asked for missing files),
2. runs the tests,
3. builds the data with our pipeline and copies the page and data into one folder (`python -m src.build_site`),
4. publishes that folder to GitHub Pages.

Pull requests run steps 1–3 only, so a change that breaks the site fails its check before it is merged. Progress is under the repo's **Actions** tab. The site is static files only: same page, same data as `python -m src.serve`, nothing running on a server.

Build the site yourself and preview it exactly as it will be published:

```bash
python -m src.build_site                         # -> _site/
python -m http.server --directory _site 8000     # http://localhost:8000
```

One-time setup by the repo owner: Settings → Pages → Build and deployment → Source: **GitHub Actions**. Until then Pages keeps publishing the raw `main` branch (the README), not the app.

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

From the repo root, with `.venv` activated and the data in `data/`:

```bash
python -m src.harmonize data/*.csv
```

This runs the US-01 loader, then turns MODIS Aqua and VIIRS Suomi-NPP detections into fire cell-days (each 0.1° grid cell counted once per day per sensor), sums them by month, finds days one satellite was not recording (e.g. Suomi NPP offline 27 Jul–10 Aug 2022), fits one VIIRS/MODIS factor per area on the overlap months without those days, fills VIIRS gap days with MODIS × factor, and writes `data/processed/harmonized_monthly.csv` (one row per area-month, local only). It prints the factor, R², Pearson r and median % difference per area, and the gap days it found. It also prints the factor fitted on each year alone and a single-factor vs power-law comparison, and writes them beside the output (`harmonized_monthly_factors_by_year.csv`, `harmonized_monthly_methods.csv`). Each CSV is read once into daily cell-days cached as Parquet in `data/processed/cells/`, so rebuilding 2012–2023 needs about 1.7 GB of memory the first time and 0.5 GB after (`--no-cache` loads everything at once instead). Options: `--grid 0.25`, `--include-terra`, `--out path.csv`, `--quiet`, `--cache-dir path`, `--no-cache`.

In Python:

```python
from pathlib import Path
from src.load_data import load_hotspots
from src.harmonize import harmonize

table, fits = harmonize(load_hotspots(sorted(Path('data').glob('*.csv')), verbose=False))
```

Method, results and limits: [docs/harmonization.md](docs/harmonization.md).

## Cell-month feature table (US-15)

The inputs for the fire outlook (US-16) and the fire-deficit test (US-17). Build it with:

```
python -m src.features
```

This reads the VIIRS Suomi-NPP cell-days from the US-14 cache (building it first if needed) and writes `data/processed/cell_month.parquet` (local only): one row per area, 0.1° cell and month, for every cell that had a detection in the record. On 2012–2023 that is 8.3 million rows (19,097 Argentina cells and 38,432 Canada cells × 144 months), about 23 MB, built in 5 seconds from a warm cache.

Each row holds what happened that month (`cell_days`, `burned`, `detections`, `frp_max`, `frp_mean`, `night_share`) and predictors that use **only earlier months**, so a model can't see the future: last month's and last year's cell-days, the share of earlier years the cell burned in this calendar month, months since it last burned, and the same activity in the 8 surrounding cells. `viirs_gap_days` flags months when VIIRS was offline, and `first_seen_year` says when the cell first burned. The full column list is at the top of `src/features.py`.

Rows only exist for cells that burned at some point, so evaluate on cells first seen in the training years (`first_seen_year <= 2019`). 25% of Canada's cells and 8% of Argentina's were first seen in 2020–2023, mostly in Canada's 2023 season. `--train-end` changes the year the summary reports against.

## Fire outlook models (US-16)

Fits and scores the outlook the app can show (US-18):

```
python -m src.predict
```

It needs `data/processed/cell_month.parquet` (`python -m src.features`) and `harmonized_monthly.csv` (`python -m src.harmonize`). It fits on 2012–2019, picks settings on 2020–2021, refits on 2012–2021 and scores once on 2022–2023 against a climatology baseline. Three outlooks:
- next month's burn probability per 0.1° cell (logistic regression);
- next month's fire cell-days per area (a nowcast that scales the monthly normal by last month's anomaly);
- the peak month.

All three beat the baseline in both areas. For example, the cell map's AUC rises from 0.72 to 0.85 in Canada and from 0.82 to 0.87 in Argentina. Results go to `data/processed/prediction/` (`metrics.json` with a `ship` flag per model, test predictions, monthly climatology). It takes about 20 seconds.

Method, results and limits (new fire areas are not scored; one month ahead; no weather): [docs/prediction.md](docs/prediction.md).

## Fire-season summary (US-05)

The page's **Fire season** cards show the start, peak and end month for the selected area. `python -m src.serve` (or `python -m src.web_data`) computes them from `data/processed/harmonized_monthly.csv` and writes them to `data/processed/web/monthly.json`.

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
The default data covers 2012–2023 (12 years), which is still short for a long-term climate
baseline. Teammate review and testing on a second laptop remain required.

## Month × year calendar (US-04)

The **Month by year** grid on the page shows the harmonized record from US-02: one row per year (newest first), one column per month, coloured by quartiles of the area's non-zero months (the same rule as the daily calendar). Months in the estimated season are underlined. Missing months are striped, never shown as zero. The data comes from `monthly.json` (see `src/web_data.py`); the drawing code is `web/js/monthly.js`. This replaces the US-04a sample calendar that ran in Streamlit.

## Area selection (US-03)

The area switch at the top of the page (Canada | Argentina) drives every section: daily calendar, season, month × year calendar, globe and stat cards. Canada is the default. The choice is kept in the page address, so `http://localhost:8000/?area=Argentina` opens straight on Argentina; an unknown area falls back to Canada. Areas come from the data, so downloading another country with `get_data.py --countries` adds it to the switch.

## Outlook mode (US-18)

The globe's third tab, **Outlook**, shows the US-16 fire outlook, labelled *Outlook from 2012–2023 patterns, not a forecast*. Pick a month in the sidebar:
- **Next-month outlook** (January 2024, the month after the record ends): every 0.1° cell with at least a 5% chance of a fire cell-day, coloured 5–20%, 20–50% and 50%+. The cards show how many cells reach 30%, the expected harmonized fire cell-days for the area (with the normal and the past low–high range), and the typical peak month.
- **Back-test** (any month of 2022–2023): what the tested model expected, with the fires that actually happened drawn as rings. The cards show the share of fires that landed on mapped cells (fires in places with no fire since 2012 count as misses) and the monthly estimate against the actual value. Months when VIIRS was offline are shown, flagged and left out of the scores.

The sidebar note gives each model's test score against its climatology baseline. If a model had not beaten its baseline, the map would show the baseline instead.

The page builds `outlook.json` with the rest of its data (`src/outlook.py`, run in its own process, about 30 extra seconds). It needs the full 2012–2023 download; with fewer years, the Outlook tab says which years are missing.
