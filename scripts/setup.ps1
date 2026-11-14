# FireCal setup for Windows (T-02). Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Checks Git and Python 3.11+, then hands off to scripts\setup_env.py, which creates
# .venv, installs requirements.txt, smoke-tests imports and the app, and prints a summary.
# Extra arguments are passed through (e.g. -- --skip-app).

$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")

function Fail($msg) {
    Write-Host "[FAIL] $msg"
    Write-Host ""
    Write-Host "RESULT: FAIL. Fix the step above and run scripts\setup.ps1 again."
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git - not found. Install with: winget install Git.Git   (then open a new terminal)"
}

# Candidates: the py launcher first (avoids the Microsoft Store 'python' stub), then python / python3.
$candidates = @(@("py", "-3"), @("python"), @("python3"))
$py = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $pre = @()
    if ($c.Length -gt 1) { $pre = $c[1..($c.Length - 1)] }
    & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}

if (-not $py) {
    Fail "Python 3.11+ - not found. Install with: winget install Python.Python.3.12   (or python.org, tick 'Add python.exe to PATH'), then open a new terminal"
}

$exe = $py[0]
$pre = @()
if ($py.Length -gt 1) { $pre = $py[1..($py.Length - 1)] }
& $exe @pre "scripts\setup_env.py" @args
exit $LASTEXITCODE
