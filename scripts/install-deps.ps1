param(
    [switch]$Force,
    [switch]$WithDev
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Require-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw $Message
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "La commande a echoue : $FilePath $($Arguments -join ' ')"
    }
}

Write-Host ""
Write-Host "Installation des dependances ECUME" -ForegroundColor Cyan
Write-Host "Projet : $Root"
if ($Force) {
    Write-Host "Mode force : les dependances seront reinstallees ou mises a jour." -ForegroundColor Yellow
} else {
    Write-Host "Mode rapide : les dependances deja presentes sont conservees." -ForegroundColor Green
}
if ($WithDev) {
    Write-Host "Mode dev : les dependances de test seront aussi installees." -ForegroundColor Yellow
}
Write-Host ""

Require-Command -Name "python" -Message "Python est introuvable. Installe Python 3.11+ puis relance ce script."
Require-Command -Name "node" -Message "Node.js est introuvable. Installe Node.js LTS puis relance ce script."
Require-Command -Name "npm" -Message "npm est introuvable. Installe Node.js LTS puis relance ce script."

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data\uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data\exports") | Out-Null

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Host ".env cree depuis .env.example" -ForegroundColor Green
}

Push-Location $Backend
try {
    $createdVenv = $false
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Creation de l'environnement Python backend..." -ForegroundColor Cyan
        Invoke-Native "python" "-m" "venv" ".venv"
        $createdVenv = $true
    }

    if ($Force -or $createdVenv) {
        Write-Host "Installation des dependances Python..." -ForegroundColor Cyan
        Invoke-Native ".\.venv\Scripts\python.exe" "-m" "pip" "install" "--upgrade" "pip"
        Invoke-Native ".\.venv\Scripts\python.exe" "-m" "pip" "install" "-r" "requirements.txt"
        if ($WithDev -and (Test-Path "requirements-dev.txt")) {
            Invoke-Native ".\.venv\Scripts\python.exe" "-m" "pip" "install" "-r" "requirements-dev.txt"
        }
    } else {
        Write-Host "Environnement Python deja present. Passage ignore." -ForegroundColor Green
        if ($WithDev) {
            Write-Host "Pour ajouter les dependances de test a un environnement existant, relance avec -Force -WithDev." -ForegroundColor Yellow
        }
    }
} finally {
    Pop-Location
}

Push-Location $Frontend
try {
    if ($Force -or -not (Test-Path "node_modules")) {
        Write-Host "Installation des dependances frontend..." -ForegroundColor Cyan
        Invoke-Native "npm" "install"
    } else {
        Write-Host "Dependances frontend deja presentes. Passage ignore." -ForegroundColor Green
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Installation terminee. Lance ensuite scripts\start-ecume.ps1." -ForegroundColor Green
