# FireCal

A fire-season calendar built from NASA FIRMS MODIS and VIIRS hotspot data — Team Lanesra, NASA Space Apps Challenge (COM805).

## Project structure

```
firecal/
├── data/        Raw NASA FIRMS CSVs (gitignored — download locally, never commit)
├── src/         App and data-processing code (entry point: src/app.py)
├── notebooks/   Exploration notebooks
├── tests/       Tests
└── requirements.txt
```

## Setup (once per laptop)

You need Git, Python 3.11+, and an editor (VS Code recommended).

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

4. Put the NASA FIRMS archive CSVs (MODIS and VIIRS, Canada and Argentina) in `data/`. They stay on your laptop only.

## Run the app

With the virtual environment active, from the repo root:

```bash
streamlit run src/app.py
```

The app opens in your browser at http://localhost:8501.

## How we work

- **Never commit straight to `main`.** One feature branch per task, named by task ID:

  ```bash
  git checkout main && git pull
  git checkout -b us-04-heatmap
  ```

- Hand the task spec to Claude Code on your branch, then review and test the output against the acceptance criteria.
- Push your branch and open a pull request. One other teammate reviews it before it merges to `main`.
- **Definition of Done:** acceptance criteria pass on Canada and Argentina, tested on a second laptop, reviewed and merged, README updated.
