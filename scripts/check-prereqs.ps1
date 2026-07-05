$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSScriptRoot
$Failures = 0

function Test-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$InstallHint,
        [string[]]$VersionArgs = @("--version"),
        [switch]$Optional
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        if ($Optional) {
            Write-Host "[optionnel] $Name absent. $InstallHint" -ForegroundColor Yellow
        } else {
            Write-Host "[manquant] $Name absent. $InstallHint" -ForegroundColor Red
            $script:Failures += 1
        }
        return
    }

    try {
        $version = & $Name @VersionArgs 2>$null | Select-Object -First 1
        Write-Host "[ok] $Name $version" -ForegroundColor Green
    } catch {
        Write-Host "[ok] $Name detecte" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Verification du poste pour ECUME" -ForegroundColor Cyan
Write-Host "Projet : $Root"
Write-Host ""

Test-Command -Name "git" -InstallHint "Installer Git for Windows : https://git-scm.com/download/win"
Test-Command -Name "python" -InstallHint "Installer Python 3.11+ et cocher 'Add python.exe to PATH'."
Test-Command -Name "node" -InstallHint "Installer Node.js LTS : https://nodejs.org/"
Test-Command -Name "npm" -InstallHint "npm est installe avec Node.js."
Test-Command -Name "ollama" -InstallHint "Installer Ollama si l'analyse LLM locale est souhaitee : https://ollama.com/" -Optional

Write-Host ""
if (Test-Path (Join-Path $Root ".env")) {
    Write-Host "[ok] Fichier .env present" -ForegroundColor Green
} else {
    Write-Host "[info] Fichier .env absent. Le script install-deps.ps1 le creera depuis .env.example." -ForegroundColor Yellow
}

if (Test-Path (Join-Path $Root "backend\.venv\Scripts\python.exe")) {
    Write-Host "[ok] Environnement Python backend present" -ForegroundColor Green
} else {
    Write-Host "[info] Environnement Python backend absent. Lancer scripts\install-deps.ps1." -ForegroundColor Yellow
}

if (Test-Path (Join-Path $Root "frontend\node_modules")) {
    Write-Host "[ok] Dependances frontend presentes" -ForegroundColor Green
} else {
    Write-Host "[info] Dependances frontend absentes. Lancer scripts\install-deps.ps1." -ForegroundColor Yellow
}

Write-Host ""
if ($Failures -gt 0) {
    Write-Host "$Failures prerequis obligatoire(s) manquant(s)." -ForegroundColor Red
    exit 1
}

Write-Host "Le poste semble pret pour ECUME." -ForegroundColor Green
exit 0
