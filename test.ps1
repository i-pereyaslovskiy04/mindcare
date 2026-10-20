# MindCare -- backend test runner
# Runs compileall, then the FULL suite on an isolated one-off test DB
# (scripts/isolated_test_db.py). Never touches the dev DB.
# Usage:
#   .\test.ps1             full isolated suite (needs TEST_DATABASE_URL; ENV=test set here)
#   .\test.ps1 -UnitOnly   unit tests only (integration excluded, sentinel DB)

param([switch]$UnitOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root       = Split-Path -Parent $MyInvocation.MyCommand.Definition
$apiDir     = Join-Path $root "mindcare_api"
$venvDir    = Join-Path $apiDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Write-Step { param($m) Write-Host "[TEST]  $m" -ForegroundColor Yellow }
function Write-Ok   { param($m) Write-Host "  [OK]  $m" -ForegroundColor DarkGreen }
function Write-Fail { param($m) Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "       MindCare  --  Backend Tests        " -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow

# Check venv exists
if (-not (Test-Path $venvPython)) {
    Write-Host ""
    Write-Host "  Python venv not found. Run .\start.ps1 once to create it." -ForegroundColor Red
    exit 1
}

# Check pytest is installed
$pytestCheck = & $venvPython -m pytest --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  pytest is not installed." -ForegroundColor Red
    Write-Host "  Run: .venv\Scripts\python.exe -m pip install -r mindcare_api\requirements-dev.txt" -ForegroundColor Yellow
    exit 1
}
Write-Ok "pytest: $($pytestCheck | Select-Object -First 1)"

# compileall
Write-Step "python -m compileall app ..."
Push-Location $apiDir
& $venvPython -m compileall app -q
$compileExit = $LASTEXITCODE
Pop-Location
if ($compileExit -ne 0) { Write-Fail "compileall found syntax errors in app/." }
Write-Ok "compileall: no errors."

# tests
if ($UnitOnly) {
    Write-Step "pytest tests/ (unit-only, integration excluded) ..."
    Push-Location $apiDir
    $prevUnit = $env:MINDCARE_UNIT_ONLY
    $env:MINDCARE_UNIT_ONLY = "1"
    try {
        & $venvPython -m pytest tests/ --ignore=tests/integration -v
        $pytestExit = $LASTEXITCODE
    } finally {
        if ($null -eq $prevUnit) {
            Remove-Item Env:\MINDCARE_UNIT_ONLY -ErrorAction SilentlyContinue
        } else { $env:MINDCARE_UNIT_ONLY = $prevUnit }
        Pop-Location
    }
    Write-Host "  [UNIT-ONLY] integration tests were NOT run." -ForegroundColor Yellow
    Write-Host "  Set TEST_DATABASE_URL and run .\test.ps1 for the full suite." -ForegroundColor Yellow
} else {
    Write-Step "isolated integration suite (scripts/isolated_test_db.py) ..."
    Push-Location $apiDir
    $prevEnv = $env:ENV
    $env:ENV = "test"
    try {
        & $venvPython scripts/isolated_test_db.py -v
        $pytestExit = $LASTEXITCODE
    } finally {
        if ($null -eq $prevEnv) {
            Remove-Item Env:\ENV -ErrorAction SilentlyContinue
        } else { $env:ENV = $prevEnv }
        Pop-Location
    }
}
if ($pytestExit -ne 0) {
    Write-Host "  [FAIL] Tests failed (exit $pytestExit)." -ForegroundColor Red
    exit $pytestExit
}
if ($UnitOnly) {
    Write-Ok "All selected unit tests passed (integration NOT run)."
} else {
    Write-Ok "Full isolated suite passed (temporary test DB created and dropped)."
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGreen
Write-Host "          All checks passed  [OK]         " -ForegroundColor DarkGreen
Write-Host "==========================================" -ForegroundColor DarkGreen
Write-Host ""
