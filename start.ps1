#Requires -Version 5.1
<#
Bootstraps and runs the Agent Ops Console: Postgres (pgvector via Docker),
the FastAPI backend venv, and the Vite frontend — then starts both dev servers.

Usage:
  .\start.ps1                # first run: sets up everything, then starts the app
  .\start.ps1 -SkipInstall    # reuse existing venv / node_modules, just start services
#>

param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

function Write-Step($msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Require-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "'$name' was not found on PATH. $hint"
    }
}

# 1. Prereqs -----------------------------------------------------------
Require-Command "docker" "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
Require-Command "node" "Install Node.js 18+: https://nodejs.org/"
Require-Command "npm" "Install Node.js 18+ (npm ships with it)."

$pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" }
             elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" }
             else { throw "Python 3.11+ was not found on PATH. Install it from https://www.python.org/downloads/" }

# 2. .env ----------------------------------------------------------------
$envFile = Join-Path $RepoRoot ".env"
$envExample = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "Created .env from .env.example. Server boots fine without API keys;" -ForegroundColor Yellow
    Write-Host "add ANTHROPIC_API_KEY / OPENAI_API_KEY later for real chat + RAG." -ForegroundColor Yellow
}

# 3. Postgres (pgvector) via Docker --------------------------------------
Write-Step "Starting Postgres (pgvector) via Docker Compose"
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed to start Postgres. Is Docker Desktop running?"
}

Write-Step "Waiting for Postgres to accept connections"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U postgres -d agent_ops 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    throw "Postgres did not become ready in time. Check 'docker compose logs postgres'."
}

# 4. Backend Python venv ---------------------------------------------------
$venvDir = Join-Path $RepoRoot "backend\.venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not $SkipInstall -or -not (Test-Path $venvPython)) {
    if (-not (Test-Path $venvPython)) {
        Write-Step "Creating Python virtual environment (backend\.venv)"
        & $pythonCmd -m venv $venvDir
    }
    Write-Step "Installing backend Python dependencies"
    & $venvPython -m pip install --upgrade pip | Out-Null
    & $venvPython -m pip install -r (Join-Path $RepoRoot "backend\requirements.txt")
}

# 5. Frontend deps ----------------------------------------------------------
if (-not $SkipInstall -or -not (Test-Path (Join-Path $RepoRoot "node_modules"))) {
    Write-Step "Installing frontend dependencies (npm install)"
    npm install
}

# 6. Run client + server ------------------------------------------------
Write-Step "Starting client (http://localhost:5173) and server (http://localhost:8787)"
npm run dev
