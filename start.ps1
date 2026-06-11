param(
    [switch]$Tests,
    [switch]$FullCheck
)

# MindCare -- zero-to-run startup script
# Usage:
#   .\start.ps1              -- normal start (no tests, fastest path)
#   .\start.ps1 -Tests       -- quick preflight: compileall + test_change_password, then start
#   .\start.ps1 -FullCheck   -- full preflight: compileall + all tests + lint + build, then start
#
# Startup order:
#   1. Validate tools (python, npm)
#   2. Create venv at mindcare_api/.venv
#   3. Install backend deps (pip)
#   4. Install frontend deps (npm)
#   5. Preflight checks  [only with -Tests or -FullCheck]
#   6. alembic upgrade head  <- MUST run before uvicorn
#   7. Verify alembic revision
#   8. Start backend  (new window)
#   9. Start frontend (new window)
#  10. Health-check poll (60 s)
#
# WHY alembic runs before uvicorn:
#   FastAPI lifespan only reads alembic_version (read-only check).
#   It never applies migrations. Migrations must be applied here first.
#   NEVER call alembic.command.upgrade() from FastAPI lifespan -- deadlock.
#   NEVER call Base.metadata.create_all() -- schema owned solely by Alembic.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- Paths -------------------------------------------------------------------
$root            = Split-Path -Parent $MyInvocation.MyCommand.Definition
$apiDir          = Join-Path $root "mindcare_api"
$webDir          = Join-Path $root "mindcare_web"
$venvDir         = Join-Path $apiDir ".venv"
$venvPip         = Join-Path $venvDir "Scripts\pip.exe"
$venvPython      = Join-Path $venvDir "Scripts\python.exe"
$venvUvicorn     = Join-Path $venvDir "Scripts\uvicorn.exe"
$venvAlembic     = Join-Path $venvDir "Scripts\alembic.exe"
$nodeModules     = Join-Path $webDir  "node_modules"
$requirements    = Join-Path $apiDir  "requirements.txt"
$requirementsDev = Join-Path $apiDir  "requirements-dev.txt"

# --- Helpers -----------------------------------------------------------------
function Log-Section  { param($m) Write-Host ""; Write-Host "--- $m" -ForegroundColor DarkCyan }
function Log-DB       { param($m) Write-Host "[DB]       $m" -ForegroundColor Blue }
function Log-Alembic  { param($m) Write-Host "[ALEMBIC]  $m" -ForegroundColor Cyan }
function Log-Backend  { param($m) Write-Host "[BACKEND]  $m" -ForegroundColor Green }
function Log-Frontend { param($m) Write-Host "[FRONTEND] $m" -ForegroundColor Magenta }
function Write-TestStep { param($m) Write-Host "[TEST]     $m" -ForegroundColor Yellow }
function Log-Ok       { param($m) Write-Host "  [OK]   $m" -ForegroundColor DarkGreen }
function Log-Warn     { param($m) Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Log-Fail     { param($m) Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

function Require-Command {
    param([string]$cmd, [string]$hint)
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Log-Fail "'$cmd' not found. $hint"
    }
    Log-Ok "$cmd  $(& $cmd --version 2>&1 | Select-Object -First 1)"
}

# --- Banner ------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "         MindCare  --  Dev Launcher       " -ForegroundColor Magenta
if ($Tests)     { Write-Host "              [ -Tests mode ]             " -ForegroundColor Yellow }
if ($FullCheck) { Write-Host "           [ -FullCheck mode ]            " -ForegroundColor Yellow }
Write-Host "==========================================" -ForegroundColor Magenta

# --- Step 1: tools -----------------------------------------------------------
Log-Section "Step 1: required tools"
Require-Command "python" "Install Python 3.10+ from https://python.org and add to PATH."
Require-Command "npm"    "Install Node.js 18+ from https://nodejs.org and add to PATH."

# --- Step 2: venv ------------------------------------------------------------
Log-Section "Step 2: Python virtual environment"
if (-not (Test-Path $venvDir)) {
    Write-Host "  Creating venv at $venvDir ..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Log-Fail "Failed to create virtual environment." }
    Log-Ok "venv created."
} else {
    Log-Ok "venv already exists."
}

# --- Step 3: backend deps ----------------------------------------------------
Log-Section "Step 3: backend dependencies"
if (-not (Test-Path $venvUvicorn)) {
    Write-Host "  pip install -r requirements.txt (may take a minute)..."
    & $venvPip install -r $requirements --quiet
    if ($LASTEXITCODE -ne 0) { Log-Fail "pip install failed. Check $requirements." }
    Log-Ok "Backend dependencies installed."
} else {
    Log-Ok "Backend dependencies already installed."
}

# --- Step 4: frontend deps ---------------------------------------------------
Log-Section "Step 4: frontend dependencies"
if (-not (Test-Path $nodeModules)) {
    Write-Host "  npm install (may take a minute)..."
    Push-Location $webDir
    npm install --silent
    $npmExit = $LASTEXITCODE
    Pop-Location
    if ($npmExit -ne 0) { Log-Fail "npm install failed. Check mindcare_web/package.json." }
    Log-Ok "Frontend dependencies installed."
} else {
    Log-Ok "node_modules already exists."
}

# --- Step 5: preflight checks (only with -Tests or -FullCheck) ---------------
if ($Tests -or $FullCheck) {
    Log-Section "Step 5: preflight checks"

    # Verify pytest is available in venv
    $pytestVersion = & $venvPython -m pytest --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  pytest не установлен." -ForegroundColor Red
        Write-Host "  Выполните: .venv\Scripts\python.exe -m pip install -r $requirementsDev" -ForegroundColor Yellow
        exit 1
    }
    Log-Ok "pytest: $($pytestVersion | Select-Object -First 1)"

    # compileall (both -Tests and -FullCheck)
    Write-TestStep "python -m compileall app ..."
    Push-Location $apiDir
    & $venvPython -m compileall app -q
    $compileExit = $LASTEXITCODE
    Pop-Location
    if ($compileExit -ne 0) { Log-Fail "Preflight failed: compileall нашёл синтаксические ошибки в app/." }
    Log-Ok "compileall: нет ошибок."

    if ($Tests) {
        # Quick: only test_change_password.py
        Write-TestStep "pytest tests/test_change_password.py -v ..."
        Push-Location $apiDir
        & $venvPython -m pytest tests/test_change_password.py -v
        $pytestExit = $LASTEXITCODE
        Pop-Location
        if ($pytestExit -ne 0) { Log-Fail "Preflight failed: тесты test_change_password.py упали. Исправьте тесты перед запуском." }
        Log-Ok "test_change_password.py: все тесты прошли."
    }

    if ($FullCheck) {
        # Full: all tests
        Write-TestStep "pytest tests/ -v ..."
        Push-Location $apiDir
        & $venvPython -m pytest tests/ -v
        $pytestExit = $LASTEXITCODE
        Pop-Location
        if ($pytestExit -ne 0) { Log-Fail "Preflight failed: pytest tests/ упал. Исправьте тесты перед запуском." }
        Log-Ok "Все backend-тесты прошли."

        # Frontend lint (script verified present in package.json)
        Write-TestStep "npm run lint ..."
        Push-Location $webDir
        npm run lint
        $lintExit = $LASTEXITCODE
        Pop-Location
        if ($lintExit -ne 0) { Log-Fail "Preflight failed: npm run lint нашёл ошибки. Исправьте перед запуском." }
        Log-Ok "npm lint: нет ошибок."

        # Frontend build
        Write-TestStep "npm run build ..."
        Push-Location $webDir
        $env:CI = 'false'
        npm run build
        $buildExit = $LASTEXITCODE
        Pop-Location
        if ($buildExit -ne 0) { Log-Fail "Preflight failed: npm run build завершился с ошибками." }
        Log-Ok "npm build: успешно."
    }

    Write-Host ""
    Write-Host "  Все preflight-проверки пройдены." -ForegroundColor DarkGreen
}

# --- Step 6: alembic upgrade head --------------------------------------------
Log-Section "Step 6: alembic upgrade head"
Log-Alembic "Applying migrations..."
Push-Location $apiDir
$env:PGCLIENTENCODING = "UTF8"
& $venvAlembic upgrade head
$alembicExit = $LASTEXITCODE
Pop-Location
if ($alembicExit -ne 0) {
    Log-Fail "alembic upgrade head failed. Check DB connection and .env (DATABASE_URL)."
}
Log-Ok "Migrations applied."

# --- Step 7: verify revision -------------------------------------------------
Log-Section "Step 7: verify DB revision"
Log-Alembic "Current revision:"
Push-Location $apiDir
& $venvAlembic current
$revExit = $LASTEXITCODE
Pop-Location
if ($revExit -ne 0) { Log-Warn "Could not read alembic revision." }

# --- Step 8: start backend ---------------------------------------------------
Log-Section "Step 8: start backend"
Log-Backend "Launching -> http://localhost:8000"

$backendCmd = "& { " +
    "`$host.UI.RawUI.WindowTitle = 'MindCare | Backend :8000'; " +
    "Set-Location '$apiDir'; " +
    "`$env:PGCLIENTENCODING = 'UTF8'; " +
    "& '$venvUvicorn' app.main:app --reload }"

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCmd) -WindowStyle Normal

# --- Step 9: start frontend --------------------------------------------------
Log-Section "Step 9: start frontend"
Log-Frontend "Launching -> http://localhost:3000"

$frontendCmd = "& { " +
    "`$host.UI.RawUI.WindowTitle = 'MindCare | Frontend :3000'; " +
    "Set-Location '$webDir'; " +
    "`$env:CI = 'false'; " +
    "npm start }"

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCmd) -WindowStyle Normal

# --- Step 10: health-check poll ----------------------------------------------
Log-Section "Step 10: waiting for backend to be ready"
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest "http://localhost:8000/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            Log-Ok "Backend ready (${i}s): $($resp.Content)"
            $ready = $true
            break
        }
    } catch {}
    if ($i % 5 -eq 0) { Write-Host "  ... waiting ($i / 60 s)" }
}
if (-not $ready) { Log-Warn "Backend did not respond in 60 s. Check the Backend window." }

# --- Done --------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Both servers launched in separate windows" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Backend API : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Frontend    : http://localhost:3000"      -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
