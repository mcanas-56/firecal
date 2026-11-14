"""FireCal one-command setup engine (T-02).

Normally started by scripts/setup.sh (macOS / Linux) or scripts/setup.ps1 (Windows),
which find a Python 3.11+ and Git first. It can also be run directly:

    python3 scripts/setup_env.py   # Windows: py -3 scripts/setup_env.py

It checks Git and Python, creates .venv, installs requirements.txt, smoke-tests
the imports and starts the app (python -m src.serve) for a few seconds. Standard library
only, so it runs before anything is installed. Output is plain ASCII so it
prints the same on macOS and Windows terminals.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
MIN_PYTHON = (3, 11)
IMPORTS = ["pandas"]  # the page itself needs no Python packages; pandas builds its data

# step name -> Machine readiness column in the team doc
READINESS = {
    "Git": "Git",
    "Python 3.11+": "Python",
    "Virtual environment": "Repo + deps",
    "Install requirements": "Repo + deps",
    "Import smoke test": "Repo + deps",
    "App starts": "App runs",
}

results: list[tuple[str, str, str]] = []  # (step, PASS/FAIL/SKIP/WARN, detail)


def record(step: str, status: str, detail: str = "") -> None:
    results.append((step, status, detail))
    print(f"[{status}] {step}" + (f" - {detail}" if detail else ""), flush=True)


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def check_git() -> bool:
    git = shutil.which("git")
    if not git:
        record("Git", "FAIL", "git not found. Install from https://git-scm.com/downloads "
                              "(macOS: xcode-select --install or brew install git; Windows: winget install Git.Git)")
        return False
    out = subprocess.run([git, "--version"], capture_output=True, text=True).stdout.strip()
    record("Git", "PASS", out)
    return True


def check_python() -> bool:
    v = sys.version_info
    found = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < MIN_PYTHON:
        record("Python 3.11+", "FAIL", f"found {found}. Install 3.11+ from https://www.python.org/downloads/ "
                                       "(macOS: brew install python@3.12; Windows: winget install Python.Python.3.12)")
        return False
    record("Python 3.11+", "PASS", f"{found} at {sys.executable}")
    return True


def make_venv() -> bool:
    py = venv_python()
    if py.exists():
        record("Virtual environment", "PASS", f"reusing {VENV.name}/")
        return True
    proc = subprocess.run([sys.executable, "-m", "venv", str(VENV)], capture_output=True, text=True)
    if proc.returncode != 0 or not py.exists():
        hint = " On Debian/Ubuntu: sudo apt install python3-venv." if "ensurepip" in proc.stderr else ""
        record("Virtual environment", "FAIL", (proc.stderr.strip().splitlines() or ["unknown error"])[-1] + hint)
        return False
    record("Virtual environment", "PASS", f"created {VENV.name}/")
    return True


def install_requirements() -> bool:
    req = ROOT / "requirements.txt"
    print("    installing packages (first run can take a minute)...", flush=True)
    proc = subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        record("Install requirements", "FAIL", tail or "pip failed")
        return False
    record("Install requirements", "PASS", req.name)
    return True


def smoke_imports() -> bool:
    code = "import importlib\n" + "\n".join(
        f"m = importlib.import_module('{name}'); print('{name}', getattr(m, '__version__', '?'))" for name in IMPORTS
    )
    proc = subprocess.run([str(venv_python()), "-c", code], capture_output=True, text=True)
    if proc.returncode != 0:
        record("Import smoke test", "FAIL", proc.stderr.strip().splitlines()[-1])
        return False
    record("Import smoke test", "PASS", ", ".join(proc.stdout.split("\n")[:-1]))
    return True


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def app_starts(timeout: float = 20.0) -> bool:
    """Start `python -m src.serve` headless, fetch the page and its data, then stop it."""
    if not (ROOT / "src" / "serve.py").exists() or not (ROOT / "web" / "index.html").exists():
        record("App starts", "SKIP", "src/serve.py or web/index.html not found yet")
        return True
    port = free_port()
    cmd = [str(venv_python()), "-m", "src.serve", "--port", str(port), "--no-browser", "--skip-build"]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    ok, problem = False, ""
    deadline = time.time() + timeout
    try:
        while time.time() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(base + "/", timeout=2) as r:
                    page = r.read().decode("utf-8", "replace")
                if "FireCal" not in page:
                    problem = "the page did not look like FireCal"
                    break
                with urllib.request.urlopen(base + "/data/archive.json", timeout=5) as r:
                    r.read(1)
                ok = True
                break
            except OSError as exc:
                problem = str(exc)
                time.sleep(0.5)
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    if ok:
        record("App starts", "PASS", f"python -m src.serve answered on port {port}, then stopped")
    else:
        last = (out or "").strip().splitlines()[-3:]
        record("App starts", "FAIL", " | ".join(last) or problem or f"no answer on port {port} within {int(timeout)}s")
    return ok


def check_data() -> None:
    csvs = sorted(p.name for p in (ROOT / "data").glob("*.csv"))
    if csvs:
        record("Data files", "PASS", f"{len(csvs)} CSV(s) in data/")
    else:
        get = "py -3 scripts\\get_data.py" if sys.platform == "win32" else "python3 scripts/get_data.py"
        record("Data files", "WARN", f"data/ is empty. Download the practice set (~230 MB) with: {get}")


def summary() -> int:
    failed = [s for s, st, _ in results if st == "FAIL"]
    print("\n" + "=" * 60)
    print("FireCal setup summary")
    print("=" * 60)
    for step, status, _ in results:
        print(f"  {status:<5} {step}")
    status_of = {n: s for n, s, _ in results}
    done_cols, open_cols = [], []
    for col in dict.fromkeys(READINESS.values()):  # columns, in order
        steps = [step for step, c in READINESS.items() if c == col]
        # a column is Done only when every step behind it ran and passed
        (done_cols if all(status_of.get(s) == "PASS" for s in steps) else open_cols).append(col)
    print("\nMachine readiness (team doc): set these cells to Done in your row:")
    print("  " + (", ".join(done_cols) if done_cols else "(none yet)"))
    if open_cols:
        print("Leave these as Not yet (or Blocked) until fixed: " + ", ".join(open_cols))
    print("Also check by hand: VS Code, Claude Code, GitHub CLI (gh auth status).")
    if failed:
        print(f"\nRESULT: FAIL ({len(failed)} step(s)). Fix the first FAIL above and run again.")
        return 1
    print("\nRESULT: PASS. Start the app with:")
    if sys.platform == "win32":
        print("  .venv\\Scripts\\activate  then  python -m src.serve")
    else:
        print("  source .venv/bin/activate  then  python -m src.serve")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FireCal one-command setup")
    parser.add_argument("--skip-app", action="store_true", help="skip starting the app headless")
    args = parser.parse_args()

    print(f"FireCal setup in {ROOT}\n", flush=True)
    git_ok = check_git()
    py_ok = check_python()
    if py_ok and make_venv() and install_requirements() and smoke_imports():
        if args.skip_app:
            record("App starts", "SKIP", "--skip-app")
        else:
            app_starts()
    check_data()
    del git_ok  # reported in the summary; a missing git does not block the Python steps
    return summary()


if __name__ == "__main__":
    sys.exit(main())
