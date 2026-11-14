# FireCal

Team Lanesra's NASA Space Apps Challenge project (COM805): a locally run web app that harmonizes NASA FIRMS MODIS and VIIRS hotspot detections into one monthly record and shows it as daily and month x year fire-activity calendars, a fire-season summary and a hotspot globe for Canada and Argentina. Built in 48 hours; tasks are specced on the team task board and implemented with a coding agent (Claude Code or Codex), then reviewed by the task owner and one teammate. This file is the shared instructions for both agents; `CLAUDE.md` just imports it.

## Setting up a laptop

To set up, run scripts/setup:

- macOS / Linux: `bash scripts/setup.sh`
- Windows (PowerShell): `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`

When asked to "set up my environment" (or `/setup` in Claude Code), run the script for this OS from the repo root, show the summary it prints, explain the first FAIL in plain words with its fix, and list the Machine readiness cells it says to mark Done. Do not install packages another way or change repo files while setting up.

If `data/` has no CSVs after setup, offer to download the NASA FIRMS practice set (about 230 MB, a minute or two) and run it if they agree: `python3 scripts/get_data.py` (Windows: `py -3 scripts\get_data.py`). Re-running skips files already downloaded. `--list` shows the files; `--years`, `--countries` and `--sensors` change the set.

## Layout

- `web/` the FireCal page: `index.html`, `styles.css`, `js/` split by feature (`state` shared state and actions, `calendar` daily calendar, `monthly` season + month x year calendar, `globe`, `timeline`, `theme`, `nav`, `main` wiring and data loading), bundled `vendor/d3.min.js` and `data/land.geojson`. Keep it offline apart from the web fonts
- `design/prototype/` the firecal-demo prototype and `design/screenshots/`: the design source of truth. Port its CSS, markup and D3 code rather than redrawing from screenshots
- `src/serve.py` the one-command start: prepares the data, then serves `web/` on localhost (standard library only). `/data/archive.json` and `/data/monthly.json` are served from `data/processed/web/`
- `src/web_data.py` builds the page data from `data/*.csv` with the pipeline below: `archive.json` (date -> area -> {total, frp, points: [[lat, lon, frp]]}, daily VIIRS S-NPP, MODIS where no VIIRS) and `monthly.json` (per area: harmonized months, MODIS->VIIRS fit, season, daily sensor)
- `src/load_data.py` loads and cleans FIRMS CSVs (US-01), `src/harmonize.py` builds the harmonized monthly record (US-02), `src/season_summary.py` estimates the fire season (US-05), `src/app_data.py` data folder and staleness helpers (US-09), `src/palette.py` the T-03 palette notes
- `docs/harmonization.md` method note for US-02: read before changing the harmonization
- `data/` raw NASA FIRMS CSVs, local only (gitignored)
- `notebooks/` exploration
- `tests/` tests
- `scripts/setup.sh`, `scripts/setup.ps1` setup entry points; both find Python 3.11+ and Git, then run `scripts/setup_env.py` (venv, install, smoke test, summary)
- `scripts/get_data.py` downloads the FIRMS practice CSVs into `data/` (default: MODIS + VIIRS Suomi-NPP, 2022-2023, Canada + Argentina)
- `requirements.txt` Python dependencies (pandas only; the page needs no Python packages)

## Running

- App: `python -m src.serve` (rebuilds the data when a CSV changed, serves http://localhost:8000, opens the browser; next free port if taken). `python -m src.web_data` rebuilds the data only.
- Everything runs locally. No cloud hosting, no external API calls from the app.

## Data notes

- FIRMS columns: latitude, longitude, acq_date, acq_time, satellite, instrument, confidence, version, frp, daynight, type.
- MODIS `confidence` is 0-100; VIIRS is `l` / `n` / `h`. MODIS brightness is `brightness`/`bright_t31`; VIIRS is `bright_ti4`/`bright_ti5`.
- `type`: 0 vegetation fire, 1 volcano, 2 other static land source, 3 offshore.
- MODIS covers 2000-present, VIIRS 2012-present; harmonization is calibrated on the overlap.

## Rules

- Never commit to `main`. One branch per task, named by task ID: `t-02-setup-command`, `us-04-heatmap`.
- Never commit anything in `data/`, or `.env` / secrets.
- Open a pull request into `main`; the task owner tests it against the acceptance criteria and one other teammate reviews before merge.
- Code must work on macOS and Windows (use `pathlib`, no shell-specific commands in Python code).
- Run tests with `python -m unittest discover -s tests` before opening a PR.
- Keep the README current when setup or run steps change.
