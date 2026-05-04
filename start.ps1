# MindCare — zero-to-run startup script
# Usage: .\start.ps1
# Works after a fresh clone with no prior setup.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── Paths ───────────────────────────────────────────────────────────────────
$root        = Split-Path -Parent $MyInvocation.MyCommand.Definition
$apiDir      = Join-Path $root "mindcare_api"
$webDir      = Join-Path $root "mindcare_web"
$venvDir     = Join-Path $root ".venv"
$venvPip     = Join-Path $venvDir "Scripts\pip.exe"
$venvUvicorn = Join-Path $venvDir "Scripts\uvicorn.exe"
$nodeModules = Join-Path $webDir  "node_modules"
$requirements= Join-Path $apiDir  "requirements.txt"

# ─── Helpers ─────────────────────────────────────────────────────────────────
function Log-Setup  { param($msg) Write-Host "[SETUP] $msg" -ForegroundColor Cyan    }
function Log-Start  { param($msg) Write-Host "[START] $msg" -ForegroundColor Green   }
function Log-Info   { param($msg) Write-Host "        $msg" -ForegroundColor Gray    }
function Log-Ok     { param($msg) Write-Host "  [OK] $msg"  -ForegroundColor DarkGreen }
function Log-Error  {
    param($msg)
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

function Require-Command {
    param([string]$cmd, [string]$hint)
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Log-Error "'$cmd' is not installed or not on PATH. $hint"
    }
    Log-Ok "$cmd found: $(& $cmd --version 2>&1 | Select-Object -First 1)"
}

# ─── Banner ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "         MindCare -- Dev Launcher         " -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

# ─── Step 1: Validate required tools ─────────────────────────────────────────
Log-Setup "Checking required tools..."
Require-Command "python" "Install Python 3.10+ from https://python.org and add it to PATH."
Require-Command "npm"    "Install Node.js 18+ from https://nodejs.org and add it to PATH."
Write-Host ""

# ─── Step 2: Python virtual environment ──────────────────────────────────────
if (-not (Test-Path $venvDir)) {
    Log-Setup "Creating Python virtual environment at .venv ..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Log-Error "Failed to create virtual environment." }
    Log-Ok "Virtual environment created."
} else {
    Log-Ok "Virtual environment already exists."
}

# ─── Step 3: Backend dependencies ────────────────────────────────────────────
if (-not (Test-Path $venvUvicorn)) {
    Log-Setup "Installing backend dependencies (this may take a minute)..."
    Log-Info  "Source: $requirements"
    & $venvPip install -r $requirements --quiet
    if ($LASTEXITCODE -ne 0) { Log-Error "pip install failed. Check $requirements for errors." }
    Log-Ok "Backend dependencies installed."
} else {
    Log-Ok "Backend dependencies already installed."
}

# ─── Step 4: Frontend dependencies ───────────────────────────────────────────
if (-not (Test-Path $nodeModules)) {
    Log-Setup "Installing frontend dependencies (this may take a minute)..."
    Log-Info  "Running: npm install inside mindcare_web/"
    Push-Location $webDir
    npm install --silent
    $npmExit = $LASTEXITCODE
    Pop-Location
    if ($npmExit -ne 0) { Log-Error "npm install failed. Check mindcare_web/package.json." }
    Log-Ok "Frontend dependencies installed."
} else {
    Log-Ok "Frontend dependencies already installed."
}

Write-Host ""

# ─── Step 5: Start backend ────────────────────────────────────────────────────
Log-Start "Launching backend  → http://localhost:8000"
$backendCmd = "Write-Host '[BACKEND] Starting...' -ForegroundColor Cyan; " +
              "Set-Location '$apiDir'; " +
              "& '$venvUvicorn' app.main:app --reload"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $backendCmd
) -WindowStyle Normal

Start-Sleep -Seconds 2

# ─── Step 6: Start frontend ───────────────────────────────────────────────────
Log-Start "Launching frontend → http://localhost:3000"
$frontendCmd = "Write-Host '[FRONTEND] Starting...' -ForegroundColor Green; " +
               "Set-Location '$webDir'; " +
               "npm start"

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    $frontendCmd
) -WindowStyle Normal

# ─── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Both servers are starting in new windows." -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Backend API:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Frontend:     http://localhost:3000" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
