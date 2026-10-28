# Sauvegarde et restauration

Une sauvegarde que l'on n'a jamais restaurée n'est qu'une hypothèse. Cette procédure est **testée de bout en bout** (sauvegarde,
destruction, restauration dans une instance vierge, vérification des empreintes : `python tests/backup_check.py`) ; refaites-la
vous-même sur votre serveur avant d'en dépendre, puis **chaque trimestre**.

## Ce qui est sauvegardé

Une seule archive chiffrée, datée (`kikan-AAAAMMJJ-HHMMSS.tar.gz.age`), contenant :

| Élément | Pourquoi |
|---|---|
| **Base PostgreSQL** (export `pg_dump`, à chaud) | salariés, matériel, remises, signatures, journal d'audit, comptes, réglages |
| **PDF scellés locaux** (volume `kikan_archive`) | les preuves, tant que le stockage est local ou en attente de dépôt |
| **Clés et certificat de scellement** (volume `kikan_certs`) | continuer à sceller avec le même certificat |
| **Certificat HTTPS** (volume `kikan_webcerts`) | éviter de le régénérer |
| **Fichier `.env`** | les secrets : clé de session, mots de passe, jetons |
| **Manifeste** | empreinte SHA-256 de chaque fichier, vérifiée avant toute restauration |

**Hors sauvegarde** : les documents rangés sur un stockage externe (SMB, WebDAV, SharePoint, DocuWare), qui relèvent de la sauvegarde de
ces services (la page *Sauvegarde* de Kikan le rappelle) ; et les services tiers (GLPI, serveur de messagerie).

## Principe de sécurité : le chiffrement par clé publique

L'archive est chiffrée avec une **clé publique** (outil `age`). Le serveur ne contient donc que de quoi **chiffrer** : quelqu'un qui
vole le serveur ou le partage de sauvegarde ne peut **rien déchiffrer**. La **clé privée** sert uniquement à restaurer ; elle doit
vivre **hors du serveur** (coffre de mots de passe, clé USB dans un coffre).

> **Sans la clé privée, aucune sauvegarde ne peut être restaurée.** Faites-en deux copies, dans deux endroits différents, dès la
> génération. Kikan ne peut pas la régénérer.

## Mise en place (une fois)

1. **Générer la paire de clés** :
   ```bash
   docker compose --profile backup run --rm -v ./cles:/keys backup keygen --out /keys
   ```
   Le dossier `cles` contient `identity.txt` (**clé privée** : à mettre en lieu sûr puis à **supprimer du serveur**) et `recipient.txt`
   (clé publique).
2. **Renseigner `.env`** :
   ```
   KIKAN_BACKUP_RECIPIENT=age1...                      # contenu de recipient.txt
   KIKAN_BACKUP_SMB_SERVER=fichiers.societe.local      # le partage réseau
   KIKAN_BACKUP_SMB_SHARE=sauvegardes
   KIKAN_BACKUP_SMB_PATH=kikan
   KIKAN_BACKUP_SMB_USER=svc-sauvegarde
   KIKAN_BACKUP_SMB_PASSWORD=...
   KIKAN_BACKUP_SMB_DOMAIN=SOCIETE
   ```
   Le compte du partage a besoin de **lire, écrire, lister et supprimer** dans ce seul dossier (la suppression sert à la rétention).
   Sans partage SMB, `KIKAN_BACKUP_DIR` désigne un dossier (disque externe, lecteur monté).
3. **Première sauvegarde** :
   ```bash
   docker compose --profile backup run --rm backup backup
   ```
4. **Vérifier** : la page **Sauvegarde** de Kikan (informatique) affiche la date, la taille et la destination ; le tableau de bord alerte
   si la dernière sauvegarde a plus de 36 h (`KIKAN_BACKUP_ALERT_HOURS`) ou si la dernière tentative a échoué.

## Planification (toutes les nuits)

**Windows** (Docker Desktop doit être démarré ; la tâche s'exécute sous un compte autorisé à utiliser Docker) :

```powershell
schtasks /Create /TN "Kikan sauvegarde" /SC DAILY /ST 02:00 /RL HIGHEST `
  /TR "powershell -NoProfile -Command \"Set-Location 'C:\kikan'; docker compose --profile backup run --rm backup backup >> sauvegarde.log 2>&1\""
```

**Linux** (`crontab -e`) :

```
0 2 * * * cd /opt/kikan && docker compose --profile backup run --rm backup backup >> sauvegarde.log 2>&1
```

Kikan **ne lance pas lui-même** les sauvegardes (il n'a pas, et ne doit pas avoir, accès à tous les volumes) : il lit l'état qu'elles
écrivent et alerte quand elles manquent.

## Rétention

Par défaut (`KIKAN_BACKUP_KEEP_DAYS=30`, `KIKAN_BACKUP_KEEP_MONTHS=12`), après chaque sauvegarde réussie :

- **toutes** les sauvegardes de moins de **30 jours** sont conservées ;
- au-delà, seule la **première sauvegarde de chaque mois** est conservée, pendant **12 mois** ;
- la plus récente n'est **jamais** supprimée ; les fichiers étrangers au dossier ne sont jamais touchés.

Soit environ 30 + 12 = 42 archives. Une sauvegarde échouée ne supprime rien.

## Restaurer

### Cas courant : revenir à une sauvegarde sur le serveur

```powershell
.\scripts\restore.ps1 -Archive kikan-20261029-020000.tar.gz.age -Identity C:\cles\identity.txt        # Windows
```
```bash
scripts/restore.sh kikan-20261029-020000.tar.gz.age /chemin/identity.txt                              # Linux
```

Le script demande de taper `RESTAURER`, arrête l'API et le web, fait une **sauvegarde de sécurité de l'état actuel**, restaure la base,
les PDF scellés, les clés et le certificat, redémarre, puis **vérifie** chaque PDF scellé (empreinte relue et comparée à celle enregistrée).
`docker compose --profile backup run --rm backup list` liste les archives disponibles.

La restauration **refuse d'écraser** une base ou des volumes non vides sans `--force` (que le script ajoute après la sauvegarde de sécurité).

### Reprise après sinistre : serveur perdu

1. Installer Docker et récupérer le projet Kikan (`git clone`).
2. Recréer le `.env` : si vous avez une copie, la remettre. **Sinon**, restaurer d'abord (étape 4) : la copie du `.env` contenue dans la
   sauvegarde est écrite dans `restore-output/env.restored` (jamais appliquée automatiquement). Il faut au minimum `POSTGRES_PASSWORD`
   (nouveau mot de passe possible sur un serveur neuf) et les paramètres de partage de sauvegarde.
3. Démarrer la base seule : `docker compose up -d db`.
4. `scripts/restore.sh <archive> <cle-privee> --sans-sauvegarde-de-securite` (serveur neuf : rien à protéger).
5. Copier `restore-output/env.restored` vers `.env` si le `.env` a été perdu, puis `docker compose up -d`.
6. Se connecter, contrôler la page **Stockage** (test de connexion) et la page **Sauvegarde** ; relancer une sauvegarde.

### Si le `.env` est perdu

L'archive en contient une copie : voir ci-dessus. Sans `.env` **ni** archive, les secrets (clé de session, jetons, mots de passe de
services) sont perdus : les sessions sont invalidées, les comptes locaux restent utilisables (les mots de passe sont en base), mais
les jetons GLPI, les secrets SharePoint ou DocuWare et le mot de passe SMTP doivent être ressaisis.

### Si la clé privée est perdue

Les sauvegardes existantes **ne sont plus restaurables**. Générez une nouvelle paire de clés, mettez à jour `KIKAN_BACKUP_RECIPIENT`
et refaites une sauvegarde : les suivantes seront utilisables.

## Vérifications

- `docker compose --profile restore run --rm restore verify` (ou automatiquement en fin de restauration) contrôle la base (migrations,
  comptages) et **relit chaque PDF scellé local pour comparer son empreinte** à celle enregistrée à la signature ; il signale les
  documents manquants ou altérés et le nombre de documents sur stockage externe (non couverts par cette sauvegarde).
- La suite `tests/backup_check.py` rejoue tout le parcours dans des conteneurs jetables ; `backup/test_retention.py` teste la rétention.

## Objectifs réalistes

- **Perte de données maximale** : l'intervalle entre deux sauvegardes (24 h avec la planification ci-dessus).
- **Durée de reprise** : de l'ordre de la demi-heure pour un parc de quelques milliers de documents (temps de transfert du partage compris),
  plus la réinstallation du serveur en cas de sinistre.
- Les documents signés **après** la dernière sauvegarde et stockés sur un moteur externe restent disponibles sur ce moteur.

## Liste de contrôle trimestrielle

- [ ] La page *Sauvegarde* est « à jour » et la taille est cohérente.
- [ ] Les deux copies de la clé privée sont lisibles.
- [ ] Une restauration d'essai dans une instance vierge (`python tests/backup_check.py`, ou à la main sur une machine de test) réussit.
- [ ] Le mot de passe du compte de partage n'a pas expiré.
- [ ] Les sauvegardes des stockages externes (SharePoint, DocuWare, SMB) sont en place.
