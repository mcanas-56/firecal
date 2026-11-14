---
description: Set up the FireCal dev environment on this laptop (Git, Python, .venv, packages, smoke test)
---

Set up this FireCal clone so the teammate can run the app. From the repo root, run the setup script for this OS:

- macOS / Linux: `bash scripts/setup.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`

The script checks Git and Python 3.11+ (and stops with install instructions if either is missing), creates `.venv`, installs `requirements.txt`, imports pandas, Streamlit and pydeck, starts the app headless for a few seconds, and prints a PASS/FAIL line per step plus a summary. Pass `--skip-app` only if the teammate asks to skip starting the app. Do not install packages any other way and do not modify repo files.

Then report:

- The summary block the script printed, as is.
- If anything FAILed: the first failure in plain words and its exact fix, then offer to run `/setup` again once it's fixed.
- If it PASSed: the Machine readiness cells to set to Done in their row of the team doc, a reminder to check VS Code, their coding agent and GitHub CLI (`gh auth status`) by hand, and how to start the app (`python -m src.serve` from the repo root; Windows: `py -3 -m src.serve`).
- If `data/` is empty: ask whether to download the NASA FIRMS practice set now (about 230 MB, a minute or two). If yes, run `python3 scripts/get_data.py` (Windows: `py -3 scripts\get_data.py`), show its result, and remind them to mark Data Done. The files stay in `data/` and are never committed.
