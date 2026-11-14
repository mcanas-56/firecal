#!/usr/bin/env bash
# FireCal setup for macOS / Linux (T-02). Run from anywhere:  bash scripts/setup.sh
# Checks Git and Python 3.11+, then hands off to scripts/setup_env.py, which creates
# .venv, installs requirements.txt, smoke-tests imports and the app, and prints a summary.
# Extra arguments are passed through (e.g. --skip-app).
set -u

cd "$(dirname "$0")/.." || exit 1

fail() { echo "[FAIL] $1"; echo; echo "RESULT: FAIL. Fix the step above and run scripts/setup.sh again."; exit 1; }

if ! command -v git >/dev/null 2>&1; then
  fail "Git - not found. Install with: xcode-select --install   (or: brew install git)"
fi

PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && \
     "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done

if [ -z "$PY" ]; then
  found="$(python3 --version 2>&1 || echo 'none')"
  fail "Python 3.11+ - not found (python3: $found). Install with: brew install python@3.12   (or https://www.python.org/downloads/)"
fi

exec "$PY" scripts/setup_env.py "$@"
