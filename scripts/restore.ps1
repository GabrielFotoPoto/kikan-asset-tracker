# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
# Licence GPLv3 (voir LICENSE).
#
# Restauration guidee d'une sauvegarde Kikan (Windows / PowerShell). A lancer depuis la racine du projet.
#
#   .\scripts\restore.ps1 -Archive kikan-20261029-020000.tar.gz.age -Identity C:\cles\identity.txt
#
# Etapes : confirmation, arret de l'API et du web, sauvegarde de securite de l'etat actuel, restauration (base, PDF scelles, cles,
# certificat), redemarrage, verification des empreintes. Le fichier .env n'est jamais remplace : la copie contenue dans la
# sauvegarde est ecrite dans .\restore-output\env.restored.
param(
    [Parameter(Mandatory = $true)][string]$Archive,      # nom de l'archive (dans le dossier ou le partage de sauvegarde)
    [Parameter(Mandatory = $true)][string]$Identity,     # fichier de la cle PRIVEE
    [switch]$SansSauvegardeDeSecurite                    # a n'utiliser que sur un serveur neuf (rien a proteger)
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Identity)) { throw "Cle privee introuvable : $Identity" }
$Identity = (Resolve-Path $Identity).Path
New-Item -ItemType Directory -Force -Path ".\restore-output" | Out-Null

Write-Host "Restauration de $Archive : la base, les PDF scelles, les cles et le certificat actuels seront REMPLACES." -ForegroundColor Yellow
$confirm = Read-Host "Tapez RESTAURER pour continuer"
if ($confirm -ne "RESTAURER") { Write-Host "Annule."; exit 1 }

Write-Host "1/4 Arret de l'API et du web..."
docker compose stop api web

if (-not $SansSauvegardeDeSecurite) {
    Write-Host "2/4 Sauvegarde de securite de l'etat actuel..."
    docker compose --profile backup run --rm backup backup
    if ($LASTEXITCODE -ne 0) {
        docker compose up -d
        throw "La sauvegarde de securite a echoue : restauration annulee, Kikan redemarre. (Sur un serveur neuf : -SansSauvegardeDeSecurite)"
    }
}

Write-Host "3/4 Restauration..."
$env:KIKAN_BACKUP_IDENTITY = $Identity
docker compose --profile restore run --rm restore restore $Archive --identity /keys/identity.txt --force
$rc = $LASTEXITCODE

Write-Host "4/4 Redemarrage..."
docker compose up -d
if ($rc -ne 0) { throw "La restauration ou sa verification a echoue (voir ci-dessus). L'etat precedent est dans la sauvegarde de securite." }
Write-Host "Restauration terminee et verifiee. Comparez .\restore-output\env.restored avec votre .env si besoin." -ForegroundColor Green
