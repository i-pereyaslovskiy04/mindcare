# MindCare -- zero-to-run startup script
# Startup order:
#   1. Validate tools (python, npm)
#   2. Create venv at mindcare_api/.venv
#   3. Install backend deps (pip)
#   4. Install frontend deps (npm)
#   5. Backend tests  (.\test.ps1; skipped with -SkipTests)
#   6. alembic upgrade head  <- MUST run before uvicorn
#   7. Verify alembic revision
#   8. Start backend  (new window) + DEV-only VK ID callback listener on :80
#      in the SAME window (only when the local .env asks for it, see below)
#   9. Start frontend (new window)
#  10. Health-check poll (60 s)
#
# WHY alembic runs before uvicorn:
#   FastAPI lifespan only reads alembic_version (read-only check).
#   It never applies migrations. Migrations must be applied here first.
#   NEVER call alembic.command.upgrade() from FastAPI lifespan -- deadlock.
#   NEVER call Base.metadata.create_all() -- schema owned solely by Alembic.
#
# WHY a second listener on port 80 (local development only):
#   VK ID accepts a localhost Redirect URL only on the standard ports:
#   http://localhost (port 80) or https://localhost (port 443). Other localhost
#   ports are not supported by VK ID, so the DEV app is registered with
#   http://localhost/api/auth/oauth/vk/callback while the main backend listens
#   on :8000. When the local .env has VK_OAUTH_ENABLED=true and
#   VK_OAUTH_CALLBACK_BASE_URL=http://localhost, this launcher starts a second
#   instance of the SAME app (same .env, same DB) on 127.0.0.1:80.
#   - It lives in the backend window and shares its console: Ctrl+C or closing
#     the window stops both instances; if the main backend exits on its own,
#     the listener is stopped too.
#   - The decision is made by mindcare_api/scripts/dev_oauth_callback_port.py.
#   - The app itself never spawns it (no subprocess in FastAPI lifespan).
#   - Production is not affected: deploy.sh / systemd do not use this script;
#     there the callback is served by the HTTPS reverse proxy.
#
# Usage:
#   .\start.ps1              full startup, backend tests gate the launch
#   .\start.ps1 -SkipTests   quick launch without step 5 (run .\test.ps1 separately)

param([switch]$SkipTests)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- Paths -------------------------------------------------------------------
$root        = Split-Path -Parent $MyInvocation.MyCommand.Definition
$apiDir      = Join-Path $root "mindcare_api"
$webDir      = Join-Path $root "mindcare_web"
$venvDir     = Join-Path $apiDir ".venv"
$venvPip     = Join-Path $venvDir "Scripts\pip.exe"
$venvPython  = Join-Path $venvDir "Scripts\python.exe"
$venvUvicorn = Join-Path $venvDir "Scripts\uvicorn.exe"
$venvAlembic = Join-Path $venvDir "Scripts\alembic.exe"
$nodeModules = Join-Path $webDir  "node_modules"
$requirementsDev = Join-Path $apiDir "requirements-dev.txt"
$backendPort = 8000

# --- Helpers -----------------------------------------------------------------
function Log-Section  { param($m) Write-Host ""; Write-Host "--- $m" -ForegroundColor DarkCyan }
function Log-Alembic  { param($m) Write-Host "[ALEMBIC]  $m" -ForegroundColor Cyan }
function Log-Backend  { param($m) Write-Host "[BACKEND]  $m" -ForegroundColor Green }
function Log-Frontend { param($m) Write-Host "[FRONTEND] $m" -ForegroundColor Magenta }
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

# Port of the DEV-only OAuth callback listener (VK ID), or 0 when not needed.
# The helper prints a port number or nothing; it never prints settings.
function Get-DevCallbackPort {
    $out = $null
    Push-Location $apiDir
    try {
        $out = & $venvPython "scripts\dev_oauth_callback_port.py" --main-port $backendPort
    } catch {
        $out = $null
    } finally {
        Pop-Location
    }
    $port = 0
    if ([int]::TryParse(("$out").Trim(), [ref]$port) -and $port -gt 0 -and $port -lt 65536) {
        return $port
    }
    return 0
}

function Test-LoopbackPortFree {
    param([int]$port)
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

# Command line for the backend window. With $callbackPort > 0 the same window
# also hosts the DEV-only callback listener:
#   - Start-Process -NoNewWindow keeps it attached to this console, so Ctrl+C
#     and closing the window reach both uvicorn instances;
#   - finally{} covers the case when the main backend exits on its own: the
#     listener gets 5 s to stop gracefully, then its process tree is killed
#     (uvicorn --reload runs the server in a child process).
function New-BackendCommand {
    param([int]$callbackPort = 0)

    if ($callbackPort -le 0) {
        return "& { " +
            "`$host.UI.RawUI.WindowTitle = 'MindCare | Backend :$backendPort'; " +
            "Set-Location '$apiDir'; " +
            "`$env:PGCLIENTENCODING = 'UTF8'; " +
            "& '$venvUvicorn' app.main:app --port $backendPort --reload }"
    }

    return "& { " +
        "`$host.UI.RawUI.WindowTitle = 'MindCare | Backend :$backendPort + VK callback :$callbackPort (dev)'; " +
        "Set-Location '$apiDir'; " +
        "`$env:PGCLIENTENCODING = 'UTF8'; " +
        "`$callback = Start-Process -FilePath '$venvUvicorn' " +
            "-ArgumentList 'app.main:app','--host','127.0.0.1','--port','$callbackPort','--reload' " +
            "-WorkingDirectory '$apiDir' -NoNewWindow -PassThru; " +
        "try { & '$venvUvicorn' app.main:app --port $backendPort --reload } " +
        "finally { " +
            "if (`$callback -and -not `$callback.WaitForExit(5000)) { " +
                "& taskkill.exe /PID `$callback.Id /T /F | Out-Null } } }"
}

# --- Banner ------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "         MindCare  --  Dev Launcher       " -ForegroundColor Magenta
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
# requirements-dev.txt pulls in requirements.txt (-r) plus test deps (pytest, httpx).
# Gate on pytest rather than uvicorn: test.ps1 (Step 5) needs the dev deps, so a venv
# that only has prod deps must still trigger an install.
Log-Section "Step 3: backend dependencies"
& $venvPython -m pytest --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip install -r requirements-dev.txt (may take a minute)..."
    & $venvPip install -r $requirementsDev --quiet
    if ($LASTEXITCODE -ne 0) { Log-Fail "pip install failed. Check $requirementsDev." }
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

# --- Step 5: backend tests ---------------------------------------------------
Log-Section "Step 5: backend tests"
if ($SkipTests) {
    Log-Warn "Skipped (-SkipTests). Run .\test.ps1 before pushing."
} else {
    & "$root\test.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  Project not started: tests failed." -ForegroundColor Red
        Write-Host "  Fix the errors and re-run: .\start.ps1  (or .\start.ps1 -SkipTests)" -ForegroundColor Yellow
        exit 1
    }
    Log-Ok "All tests passed."
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
Log-Backend "Launching -> http://localhost:$backendPort"

# DEV-only VK ID callback listener (see the header: VK ID needs localhost:80).
$callbackPort = Get-DevCallbackPort
if ($callbackPort -gt 0) {
    if (Test-LoopbackPortFree $callbackPort) {
        Log-Backend "VK ID callback listener (dev only) -> http://localhost:$callbackPort (same window)"
    } else {
        Log-Warn "Port $callbackPort is already in use: the VK ID callback listener is NOT started."
        Log-Warn "Stop the process that holds port $callbackPort (an old manual uvicorn, IIS) and re-run."
        $callbackPort = 0
    }
} else {
    Log-Ok "VK ID callback listener not needed (VK is off or its callback is not http://localhost)."
}

$backendCmd = New-BackendCommand $callbackPort

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCmd) -WindowStyle Normal

# --- Step 9: start frontend --------------------------------------------------
Log-Section "Step 9: start frontend"
Log-Frontend "Launching -> http://localhost:3000"

$frontendCmd = "& { " +
    "`$host.UI.RawUI.WindowTitle = 'MindCare | Frontend :3000'; " +
    "Set-Location '$webDir'; " +
    "`$env:CI = 'false'; " +
    "Remove-Item Env:\HOST -ErrorAction SilentlyContinue; " +
    "npm start }"

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCmd) -WindowStyle Normal

# --- Step 10: health-check poll ----------------------------------------------
Log-Section "Step 10: waiting for backend to be ready"
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest "http://localhost:$backendPort/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            Log-Ok "Backend ready (${i}s): $($resp.Content)"
            $ready = $true
            break
        }
    } catch {}
    if ($i % 5 -eq 0) { Write-Host "  ... waiting ($i / 60 s)" }
}
if (-not $ready) { Log-Warn "Backend did not respond in 60 s. Check the Backend window." }

if ($callbackPort -gt 0) {
    $callbackReady = $false
    for ($i = 1; $i -le 20; $i++) {
        try {
            $resp = Invoke-WebRequest "http://127.0.0.1:$callbackPort/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { $callbackReady = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if ($callbackReady) {
        Log-Ok "VK ID callback listener ready on :$callbackPort."
    } else {
        Log-Warn "VK ID callback listener did not respond on :$callbackPort. Check the Backend window."
    }
}

# --- Done --------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Both servers launched in separate windows" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Backend API : http://localhost:$backendPort/docs" -ForegroundColor White
Write-Host "  Frontend    : http://localhost:3000"      -ForegroundColor White
if ($callbackPort -gt 0) {
    Write-Host "  VK callback : http://localhost:$callbackPort  (dev only, lives in the Backend window)" -ForegroundColor White
}
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
