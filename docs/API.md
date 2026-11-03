# API d'import de Kikan (`/api/v1`)

Cette API permet à un **outil externe** (inventaire, script, connecteur maison) d'envoyer du matériel et des salariés vers
Kikan, **sans compte humain**. Elle s'authentifie par **jeton**, ne supprime jamais rien et ne crée pas de remises signées.

## Principes

- **Jetons** : créés par l'informatique dans *Paramétrage, onglet Intégrations*. Chaque jeton a un **nom**, un **système
  d'origine** (identifiant court, ex. `inventaire`), des **droits** (`assets_lecture`, `assets_ecriture`, `users_lecture`,
  `users_ecriture`), un **périmètre** (toute l'organisation ou des entités et leurs sous-entités) et une **date d'expiration**
  (730 jours au plus). Il est affiché **une seule fois** ; Kikan n'en conserve que l'empreinte SHA-256. Il est révocable à tout moment.
- **Un jeton n'ouvre que `/api/v1`.** Les pages de l'application, les comptes, les documents signés et les paramètres lui sont
  fermés ; inversement, un jeton de session n'est pas accepté ici.
- **Idempotence** : chaque élément porte un `id_externe` (son identifiant dans le système d'origine). Renvoyer le même élément
  ne crée jamais de doublon.
- **Jamais de suppression**, jamais de changement du statut d'un matériel ni du statut d'un salarié. Un matériel importé arrive
  **en stock** ; l'affectation passe par une remise signée dans Kikan.
- **Jamais d'écrasement** :
  - un **matériel** ou un **salarié** déjà connu (même numéro de série, même matricule ou même e-mail) est **lié** au lieu d'être
    dupliqué, sans être modifié ;
  - un matériel lié n'est mis à jour que s'il n'a pas été **modifié à la main dans Kikan** depuis la dernière synchronisation
    (sinon : `conflit`) ;
  - une fiche salarié n'est jamais écrasée : seuls ses champs **vides** sont complétés, les différences sont signalées
    (`champs_ignores`) ;
  - un **homonyme** (même nom et prénom qu'un salarié existant) n'est ni lié ni dupliqué sans décision : ajoutez
    `"homonyme": "lier"` ou `"homonyme": "creer"`.
- **Périmètre** : un jeton limité à des entités doit préciser `entite_code` pour chaque élément ; un élément hors périmètre est refusé
  sans rien révéler.
- **Débit** : 300 requêtes par minute et par jeton (réponse `429` au-delà) ; 100 éléments au plus par lot.
- Toute utilisation est tracée dans le journal d'audit (nom du jeton, compteurs), jamais le contenu des messages ni le jeton.

## Authentification

```
Authorization: Bearer kik_...
```

## Résultat par élément

| `resultat` | Signification |
|---|---|
| `cree` | Nouvel élément créé |
| `lie` | Élément déjà connu dans Kikan : lié à l'identifiant externe, sans modification (ou champs vides complétés pour un salarié) |
| `modifie` | Élément lié mis à jour (matériel non modifié localement) |
| `inchange` | Rien à faire |
| `conflit` | Non appliqué : modifié dans Kikan depuis la dernière synchronisation, numéro de série ou salarié déjà lié à un autre identifiant externe, homonyme sans décision |
| `refuse` | Non appliqué : donnée invalide, entité inconnue ou hors périmètre, identifiant interne déjà utilisé… |

## Points d'entrée

| Méthode et chemin | Droit | Rôle |
|---|---|---|
| `GET /v1/me` | tout jeton | Nom, système, droits, expiration et périmètre du jeton |
| `GET /v1/assets?limit=100&offset=0` | `assets_lecture` | Matériel du périmètre (500 par page au plus) |
| `PUT /v1/assets/{id_externe}` | `assets_ecriture` | Crée, lie ou met à jour un matériel |
| `POST /v1/assets/_batch` | `assets_ecriture` | Idem, jusqu'à 100 matériels |
| `GET /v1/users?limit=100&offset=0` | `users_lecture` | Salariés du périmètre |
| `PUT /v1/users/{id_externe}` | `users_ecriture` | Crée ou lie un salarié, complète ses champs vides |
| `POST /v1/users/_batch` | `users_ecriture` | Idem, jusqu'à 100 salariés |

Ajoutez `?dry_run=1` à une écriture pour une **simulation** : le résultat annonce ce qui serait fait, rien n'est écrit.

### Champs d'un matériel

`type` (obligatoire, la liste des types s'enrichit comme à l'import), `marque`, `modele`, `numero_serie`, `identifiant_interne`,
`date_achat`, `fin_garantie`, `echeance_renouvellement` (AAAA-MM-JJ), `entite_code`, `notes`. Tout autre champ est refusé (`422`).

### Champs d'un salarié

`matricule`, `nom`, `prenom` (obligatoires pour créer), `email`, `service`, `date_arrivee` (une date future donne le statut
« prévu »), `entite_code`, `homonyme` (`lier` ou `creer`).

### Unicité et longueurs maximales

- **Unicité** garantie par la base de données : le `matricule` d'un salarié, le `numero_serie` et l'`identifiant_interne` d'un matériel (sans tenir compte de la casse, valeurs vides ignorées) et le `code` d'une entité ne peuvent pas être utilisés deux fois. Un doublon, y compris issu de deux requêtes simultanées, reçoit un `409`.
- **Longueurs maximales** (caractères) : salarié `matricule` 50, `nom` 200, `prenom` 200, `email` 200, `service` 100 ; matériel `type`, `marque`, `modele`, `numero_serie`, `identifiant_interne` 100 et `notes` 2 000 ; entité `code` 50 et `nom` 200 ; application `nom` 200 et `description` 2 000. Un champ trop long est refusé (`422`).

## Exemples

```bash
TOKEN=kik_xxxxxxxx
URL=https://kikan.entreprise.local/api

# Qui suis-je ?
curl -s -H "Authorization: Bearer $TOKEN" $URL/v1/me

# Simulation puis import d'un lot de matériels
curl -s -X POST "$URL/v1/assets/_batch?dry_run=1" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
  "items": [
    {"id_externe": "INV-1001", "type": "PC portable", "marque": "Dell", "modele": "Latitude 5540",
     "numero_serie": "ABC123", "entite_code": "SICA"},
    {"id_externe": "INV-1002", "type": "Smartphone", "marque": "Samsung", "modele": "Galaxy A55",
     "numero_serie": "XYZ789", "entite_code": "SICA"}
  ]}'

# Un salarié
curl -s -X PUT "$URL/v1/users/RH-42" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"matricule": "00042", "nom": "Martin", "prenom": "Camille", "email": "camille.martin@entreprise.local", "entite_code": "SICA"}'
```

Réponse d'un lot :

```json
{"simulation": true, "resume": {"cree": 2},
 "resultats": [{"id_externe": "INV-1001", "resultat": "cree", "id": null},
               {"id_externe": "INV-1002", "resultat": "cree", "id": null}]}
```

## Documentation interactive

En développement, l'API expose sa documentation OpenAPI (`/docs`). Elle est **désactivée en production** ; ce fichier fait alors foi.
