param(
    [string]$RemoteUrl = "https://github.com/Toinus83/Ecume.git",
    [string]$Message = "Initial commit ECUME"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root

try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git est introuvable. Installe Git for Windows puis rouvre le terminal."
    }

    $sensitivePaths = @(
        ".env",
        "data/ecume.db",
        "data/uploads",
        "data/exports",
        "backend/.venv",
        "frontend/node_modules"
    )

    Write-Host ""
    Write-Host "Controle de securite avant publication..." -ForegroundColor Cyan
    foreach ($path in $sensitivePaths) {
        if (Test-Path $path) {
            git check-ignore -q $path
            if ($LASTEXITCODE -ne 0) {
                throw "Le chemin '$path' existe mais n'est pas ignore par Git. Publication stoppee."
            }
            Write-Host "[ignore] $path" -ForegroundColor Green
        }
    }

    if (-not (Test-Path ".git")) {
        Write-Host "Initialisation du depot Git local..." -ForegroundColor Cyan
        git init
    }

    git branch -M main

    $remoteExists = git remote 2>$null | Select-String -SimpleMatch "origin"
    if ($remoteExists) {
        git remote set-url origin $RemoteUrl
    } else {
        git remote add origin $RemoteUrl
    }

    Write-Host ""
    Write-Host "Fichiers qui seront ajoutes au commit :" -ForegroundColor Cyan
    git add .
    git status --short

    Write-Host ""
    $confirm = Read-Host "Si la liste ne contient pas .env, data/, node_modules ou .venv, tape OUI pour publier"
    if ($confirm -ne "OUI") {
        throw "Publication annulee."
    }

    git commit -m $Message
    git push -u origin main

    Write-Host ""
    Write-Host "Publication terminee : $RemoteUrl" -ForegroundColor Green
} finally {
    Pop-Location
}
