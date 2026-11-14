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
