# MindCare -- backend test runner
# Runs compileall + pytest tests/ without starting any servers.
# Usage: .\test.ps1

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

# pytest
Write-Step "pytest tests/ -v ..."
Push-Location $apiDir
& $venvPython -m pytest tests/ -v
$pytestExit = $LASTEXITCODE
Pop-Location
if ($pytestExit -ne 0) { Write-Fail "Tests failed. Fix errors before starting the project." }
Write-Ok "All backend tests passed."

Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGreen
Write-Host "          All checks passed  [OK]         " -ForegroundColor DarkGreen
Write-Host "==========================================" -ForegroundColor DarkGreen
Write-Host ""
