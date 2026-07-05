$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "L'environnement backend est absent. Lance d'abord scripts\install-deps.ps1."
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    throw "Les dependances frontend sont absentes. Lance d'abord scripts\install-deps.ps1."
}

Write-Host ""
Write-Host "Demarrage d'ECUME..." -ForegroundColor Cyan
Write-Host "Backend : http://127.0.0.1:8000"
Write-Host "Frontend : http://127.0.0.1:5173"
Write-Host ""

$backendCommand = "cd `"$Backend`"; `"$Python`" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
$frontendCommand = "cd `"$Frontend`"; npm run dev"

Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)

Write-Host "Deux fenetres se sont ouvertes : une pour le backend, une pour le frontend." -ForegroundColor Green
Write-Host "Ouvre http://127.0.0.1:5173 dans ton navigateur."
