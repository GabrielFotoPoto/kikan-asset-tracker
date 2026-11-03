# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Mise a jour guidee de Kikan (Windows / PowerShell). A lancer depuis la racine du projet.
#
#   .\scripts\update.ps1 [-Version 0.5.0] [-Sources] [-SansSauvegarde]
#
# Etapes : controle des variables .env par rapport a .env.example, sauvegarde de securite (si configuree),
# telechargement des nouvelles images (ou compilation), redemarrage et controle de /health.
param(
    [string]$Version = "",
    [switch]$Sources,
    [switch]$SansSauvegarde
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".env")) { throw "Fichier .env introuvable a la racine du projet." }
$envLines = Get-Content ".env"

$mode = if ($Sources) { "sources" } elseif ($Version -or ($envLines -match '^KIKAN_VERSION=') -or (-not (Test-Path ".git"))) { "ghcr" } else { "sources" }
if ($Version.StartsWith("v")) { $Version = $Version.Substring(1) }

if ($mode -eq "ghcr" -and -not $Version) {
    Write-Host "Recherche de la derniere version publiee sur GitHub..."
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/GabrielFotoPoto/kikan-asset-tracker/releases/latest" -TimeoutSec 10
    $Version = ($rel.tag_name -replace '^v', '')
    if (-not $Version) { throw "Impossible de determiner la derniere version. Indiquez -Version X.Y.Z" }
}

Write-Host "== 1/4 Controle du fichier .env =="
$modelFile = if (Test-Path ".env.example") { ".env.example" } elseif (Test-Path "default.env.example") { "default.env.example" } else { "" }
if ($modelFile) {
    $missing = @()
    foreach ($line in (Get-Content $modelFile)) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=') {
            $k = $Matches[1]
            if (-not ($envLines -match "^[ \t]*#?[ \t]*$k=")) { $missing += $k }
        }
    }
    if ($missing.Count -gt 0) {
        Write-Host "Attention : variables presentes dans $modelFile mais absentes de .env : $($missing -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "Fichier .env conforme aux variables obligatoires de $modelFile."
    }
}

Write-Host "== 2/4 Sauvegarde prealable =="
$backupLine = $envLines | Where-Object { $_ -match '^KIKAN_BACKUP_RECIPIENT=(.+)$' } | Select-Object -First 1
if ($SansSauvegarde) {
    Write-Host "Sauvegarde ignoree (-SansSauvegarde)."
} elseif ($backupLine) {
    if ($mode -eq "ghcr" -and (Test-Path "docker-compose.ghcr.yml")) {
        docker compose -f docker-compose.yml -f docker-compose.ghcr.yml --profile backup run --rm backup backup
    } else {
        docker compose --profile backup run --rm backup backup
    }
    if ($LASTEXITCODE -ne 0) { throw "La sauvegarde prealable a echoue : mise a jour annulee." }
} else {
    Write-Host "KIKAN_BACKUP_RECIPIENT non renseigne dans .env : sauvegarde ignoree (voir docs/SAUVEGARDE.md)."
}

Write-Host "== 3/4 Mise a jour ($mode) =="
if ($mode -eq "ghcr") {
    if (-not (Test-Path "docker-compose.ghcr.yml")) { throw "docker-compose.ghcr.yml introuvable." }
    Write-Host "Version cible : $Version"
    $env:KIKAN_VERSION = $Version
    docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
    if ($LASTEXITCODE -ne 0) { throw "Echec du telechargement des images." }
    if ($envLines -match '^KIKAN_VERSION=') {
        $envLines = $envLines -replace '^KIKAN_VERSION=.*', "KIKAN_VERSION=$Version"
        Set-Content -Path ".env" -Value $envLines -Encoding UTF8
    } else {
        Add-Content -Path ".env" -Value "`nKIKAN_VERSION=$Version" -Encoding UTF8
    }
    docker compose -f docker-compose.yml -f docker-compose.ghcr.yml up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw "Echec du redemarrage des conteneurs." }
} else {
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "Echec de git pull." }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "Echec de la compilation / redemarrage." }
}

Write-Host "== 4/4 Verification du demarrage =="
$portLine = $envLines | Where-Object { $_ -match '^KIKAN_API_PORT=(\d+)' } | Select-Object -First 1
$apiPort = if ($portLine -match '=(\d+)') { $Matches[1] } else { "8080" }
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            $ok = $true
            Write-Host "API operationnelle : version $($health.version)" -ForegroundColor Green
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ok) { throw "L'API ne repond pas sur http://127.0.0.1:$apiPort/health apres 60 secondes. Verifiez : docker compose logs api" }
Write-Host "Mise a jour terminee avec succes." -ForegroundColor Green
