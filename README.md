# Kikan

**Kikan** (機器管理, *kiki-kanri*, « gestion des équipements ») est une application de
**suivi des actifs** (PC, smartphones...) par utilisateur et par entité, avec **remise et
restitution de matériel signées et scellées** (sans papier), import de l'existant, reporting
et gestion des accès applicatifs.

Elle soutient plusieurs contrôles de l'ISO/IEC 27001:2022 :
A.5.9 (inventaire des actifs), A.5.10 (usage acceptable), A.5.11 (restitution des actifs)
et A.5.18 (droits d'accès).

> Remarque : un logiciel n'est pas « certifié ISO 27001 ». Kikan *facilite* la conformité du
> SMSI d'une organisation, il ne la remplace pas.

## Fonctionnalités (v0.1)

- **Cycle de vie du salarié** : formulaire d'entrée (RH), départ avec génération automatique de
  la liste du matériel à récupérer, passage automatique en « sorti » une fois tout rendu.
- **Remise signée** : génération d'un accusé PDF (matériel + charte informatique annexée),
  signature sur tablette, puis **scellement PAdES** (certificat auto-signé de l'organisation,
  horodatage RFC 3161 optionnel). Document infalsifiable et vérifiable.
- **Restitution signée** (A.5.11), conduite par l'informatique ou les RH.
- **Multi-entités / filiales** : rattachement des salariés, données filtrables par entité.
- **Accès applicatifs** (A.5.18) : catalogue d'applications, attribution par salarié avec note
  de niveau (ex. administrateur, « mêmes droits que... »).
- **Import CSV** de l'existant (entités, applications, utilisateurs, matériel, affectations,
  accès), avec prévisualisation et rapport d'erreurs par ligne.
- **Reporting** « qui détient quoi » à l'instant T, export **CSV** et **PDF**.
- **Statistiques** de parc (modèles les plus distribués, répartition, taux d'équipement,
  renouvellements à venir, âge moyen).
- **Rétention RGPD** paramétrable, avec prévisualisation des suppressions avant validation.
- **Authentification et rôles** : RH, informatique, lecture seule.

## Pile technique

- **Front** : React (Vite), servi par Nginx (reverse-proxy `/api`).
- **Back** : FastAPI (Python), SQLModel.
- **Base** : PostgreSQL.
- **Signature PDF** : pyHanko (PAdES) ; **génération PDF** : ReportLab.
- Déploiement **on-premise**, entièrement conteneurisé (`docker compose`).

## Démarrage rapide

Prérequis : Docker et Docker Compose.

```bash
cp .env.example .env        # puis editer les secrets (voir ci-dessous)
docker compose up --build
```

- Interface : http://localhost:3000
- API : http://localhost:8080 (documentation interactive : http://localhost:8080/docs)

### Identifiants par défaut

Au premier démarrage, un compte **informatique** est créé : `admin` / `admin`.

> **Sécurité : à changer avant toute mise en production.** Définissez dans `.env` :
> `KIKAN_ADMIN_PASSWORD` (mot de passe initial), `KIKAN_ADMIN_USER`, et surtout
> `KIKAN_SECRET_KEY` (clé de signature des jetons JWT). Ne committez jamais le fichier `.env`.

## Rôles

| Rôle | Droits |
|---|---|
| **informatique** | Tout : matériel, remises, restitutions, signatures, entités, import, paramétrage, RGPD. |
| **rh** | Cycle de vie des salariés (entrées, départs), restitutions, accès applicatifs. Lecture du reste. |
| **lecture** | Consultation et export uniquement. |

> Cible v0.2 : authentification **SSO Microsoft 365 (Entra ID)** avec comptes nominatifs,
> réservée aux groupes `Kikan-IT` (informatique) et `Kikan-RH` (rh).

## Import de l'existant

Des modèles CSV sont fournis dans [`import-modeles/`](import-modeles/) (un fichier par type,
reliés par des codes). Format : UTF-8, séparateur `;`, dates `AAAA-MM-JJ`, booléens `oui/non`.
Ordre conseillé : entités, applications, utilisateurs, matériel, affectations, accès.

## Structure du projet

```
backend/            API FastAPI
  app/
    models.py       modele de donnees (SQLModel)
    auth.py         authentification JWT + roles
    signing.py      scellement PAdES
    pdfgen.py       generation des PDF
    routers/        endpoints (entites, users, assets, assignments,
                    lifecycle, import, reports, rgpd, stats, acces, auth)
frontend/           application React (Vite + Nginx)
import-modeles/     modeles CSV pour la reprise de l'existant
SPEC.md             cahier des charges detaille
docker-compose.yml
```

## Feuille de route

- **v0.2** : SSO Microsoft 365 (Entra ID), dépôt des PDF dans une GED réelle
  (SharePoint / DocuWare), synchro GLPI, rappels e-mail.
- Durcissement production : migrations Alembic, secrets, certificat reconnu.

## Licence

Ce projet est distribué sous licence **GNU General Public License v3.0** (voir [LICENSE](LICENSE)).

Copyright (C) 2026 Gabriel Chollet.

Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier selon les
termes de la GPLv3. Il est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE GARANTIE.
