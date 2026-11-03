# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Mise a jour guidee de Kikan (Windows / PowerShell). A lancer depuis la racine du projet.
#
#   .\scripts\update.ps1 [-Version 0.5.0] [-Sources] [-Oui] [-SansSauvegarde] [-ForcerVersion]
#
# Etapes : validation de la version cible, confirmation, controle des variables .env par rapport a .env.example,
# sauvegarde de securite obligatoire (sauf -SansSauvegarde), telechargement des nouvelles images (ou compilation),
# redemarrage et controle de la version renvoyee par /health.
param(
    [string]$Version = "",
    [switch]$Sources,
    [switch]$Oui,
    [switch]$SansSauvegarde,
    [switch]$ForcerVersion
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".env")) { throw "Fichier .env introuvable a la racine du projet." }
$envLines = Get-Content ".env"

function Get-EnvValue([string]$Key) {
    $line = $envLines | Where-Object { $_ -match "^$Key=(.*)$" } | Select-Object -Last 1
    if ($line -match "^$Key=(.*)$") { return $Matches[1].Trim() }
    return ""
}

function Compare-Semver([string]$v1, [string]$v2) {
    $v1 = $v1 -replace '^v', ''
    $v2 = $v2 -replace '^v', ''
    if ($v1 -eq $v2) { return 0 }
    $parts1 = $v1.Split('-', 2)
    $parts2 = $v2.Split('-', 2)
    $nums1 = $parts1[0].Split('.') | ForEach-Object { [int]$_ }
    $nums2 = $parts2[0].Split('.') | ForEach-Object { [int]$_ }
    for ($i = 0; $i -lt 3; $i++) {
        if ($nums1[$i] -gt $nums2[$i]) { return 1 }
        if ($nums1[$i] -lt $nums2[$i]) { return -1 }
    }
    $pre1 = if ($parts1.Count -gt 1) { $parts1[1] } else { "" }
    $pre2 = if ($parts2.Count -gt 1) { $parts2[1] } else { "" }
    if (-not $pre1 -and $pre2) { return 1 }
    if ($pre1 -and -not $pre2) { return -1 }
    return [string]::CompareOrdinal($pre1, $pre2)
}

$currentVersion = (Get-EnvValue "KIKAN_VERSION") -replace '^v', ''
$mode = if ($Sources) { "sources" } elseif ($Version -or $currentVersion -or (-not (Test-Path ".git"))) { "ghcr" } else { "sources" }
if ($Version.StartsWith("v")) { $Version = $Version.Substring(1) }

$semverRegex = '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'

if ($mode -eq "ghcr") {
    if (-not $Version) {
        Write-Host "Recherche de la derniere version publiee sur GitHub..."
        $checkUrl = Get-EnvValue "KIKAN_UPDATE_CHECK_URL"
        if (-not $checkUrl) { $checkUrl = "https://api.github.com/repos/GabrielFotoPoto/kikan-asset-tracker/releases/latest" }
        $proxy = Get-EnvValue "KIKAN_UPDATE_PROXY"
        if (-not $proxy) { $proxy = Get-EnvValue "KIKAN_SSO_PROXY" }
        $irmParams = @{ Uri = $checkUrl; TimeoutSec = 10 }
        if ($proxy) { $irmParams["Proxy"] = $proxy }
        $rel = Invoke-RestMethod @irmParams
        $Version = ($rel.tag_name -replace '^v', '')
        if (-not $Version) { throw "Impossible de determiner la derniere version. Indiquez -Version X.Y.Z" }
    }
    if ($Version -notmatch $semverRegex) {
        throw "Numero de version invalide : '$Version' (format attendu : X.Y.Z ou X.Y.Z-rc.N)."
    }
    if ($currentVersion -and ($currentVersion -match $semverRegex) -and (-not $ForcerVersion)) {
        $cmp = Compare-Semver $Version $currentVersion
        if ($cmp -eq 0) {
            Write-Host "Kikan est deja en version $Version (utilisez -ForcerVersion pour reinstaller)."
            exit 0
        } elseif ($cmp -lt 0) {
            throw "Refus du retour arriere de $currentVersion vers $Version : la base de donnees peut avoir migre. Restaurez la sauvegarde (scripts\restore.ps1) ou passez -ForcerVersion."
        }
    }
}

Write-Host "================================================================"
Write-Host "Mise a jour de Kikan (mode : $mode)"
if ($mode -eq "ghcr") {
    Write-Host "  Version actuelle : $(if ($currentVersion) { $currentVersion } else { 'non definie' })"
    Write-Host "  Version cible    : $Version"
} else {
    Write-Host "  Mode sources     : git pull --ff-only de la branche courante"
}
Write-Host "  Important        : lisez la section 'Mise a jour depuis' de CHANGELOG.md avant de continuer."
Write-Host "================================================================"

if (-not $Oui) {
    $confirm = Read-Host "Continuer la mise a jour ? [o/N]"
    if ($confirm -notmatch '^(o|oui|y|yes)$') { Write-Host "Annule."; exit 1 }
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
$backupRecipient = Get-EnvValue "KIKAN_BACKUP_RECIPIENT"
if ($SansSauvegarde) {
    Write-Host "Sauvegarde ignoree (-SansSauvegarde)."
} elseif ($backupRecipient) {
    if ($mode -eq "ghcr" -and (Test-Path "docker-compose.ghcr.yml")) {
        docker compose -f docker-compose.yml -f docker-compose.ghcr.yml --profile backup run --rm backup backup
    } else {
        docker compose --profile backup run --rm backup backup
    }
    if ($LASTEXITCODE -ne 0) { throw "La sauvegarde prealable a echoue : mise a jour annulee." }
} else {
    throw "Aucune sauvegarde n'est configuree (KIKAN_BACKUP_RECIPIENT absent de .env). Configurez la sauvegarde (docs/SAUVEGARDE.md) ou passez explicitement -SansSauvegarde."
}

Write-Host "== 3/4 Mise a jour ($mode) =="
if ($mode -eq "ghcr") {
    if (-not (Test-Path "docker-compose.ghcr.yml")) { throw "docker-compose.ghcr.yml introuvable." }
    $env:KIKAN_VERSION = $Version
    docker compose -f docker-compose.yml -f docker-compose.ghcr.yml pull
    if ($LASTEXITCODE -ne 0) { throw "Echec du telechargement des images." }
    if ($envLines -match '^KIKAN_VERSION=') {
        $envLines = $envLines | ForEach-Object { if ($_ -match '^KIKAN_VERSION=') { "KIKAN_VERSION=$Version" } else { $_ } }
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
$apiPort = Get-EnvValue "KIKAN_API_PORT"
if (-not $apiPort) { $apiPort = "8080" }
$ok = $false
$reportedVer = ""
for ($i = 0; $i -lt 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$apiPort/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            $reportedVer = ($health.version -replace '^v', '')
            if ($mode -eq "ghcr" -and $Version -and ($reportedVer -ne $Version)) {
                Start-Sleep -Seconds 2
                continue
            }
            $ok = $true
            Write-Host "API operationnelle : version $($health.version)" -ForegroundColor Green
            break
        }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ok) {
    throw "Echec : l'API ne repond pas avec la version attendue sur http://127.0.0.1:$apiPort/health apres 60 secondes (version recue : '$reportedVer'). Consultez 'docker compose logs --tail 80 api'. Si une migration a echoue, restaurez la sauvegarde avec scripts\restore.ps1."
}
Write-Host "Mise a jour terminee avec succes." -ForegroundColor Green
