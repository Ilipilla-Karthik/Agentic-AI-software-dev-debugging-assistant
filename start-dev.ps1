# Start the full stack in development mode (backend + frontend).
# Requires: python 3.10+, node 20+, npm.
# Add your OpenAI key in backend/.env (see backend/.env.example) to enable real
# LLM generation; leave it blank for the free mock-mode demo.

param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Set-Location $root

if (-not (Test-Path "backend\.venv\Scripts\python.exe")) {
    Write-Host "[1/4] Creating backend virtualenv..."
    python -m venv backend\.venv
}

if (-not $SkipInstall) {
    Write-Host "[2/4] Installing backend dependencies..."
    & "backend\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r backend\requirements.txt
    Write-Host "[3/4] Installing frontend dependencies..."
    Push-Location frontend
    npm install
    Pop-Location
}

Write-Host "[4/4] Starting services..."

# Refuse to start if the ports are already taken (stale processes cause WinError 10013)
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) { throw "Port 8000 is already in use. Stop the process on port 8000 first (Get-Process / taskkill)." }
$busy5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($busy5173) { throw "Port 5173 is already in use. Stop the process on port 5173 first." }

$backend = Start-Process -FilePath "backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--reload-dir", "app", "--port", "8000" `
    -WorkingDirectory (Join-Path $root "backend") -PassThru
$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory (Join-Path $root "frontend") -PassThru

Write-Host "Backend : http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:5173"
Write-Host "Press Enter to stop both services."

Read-Host | Out-Null
taskkill.exe /PID $backend.Id /T /F 2>$null
taskkill.exe /PID $frontend.Id /T /F 2>$null
Write-Host "Services stopped."