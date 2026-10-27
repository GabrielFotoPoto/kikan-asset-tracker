# Modèles d'import Kikan

Fichiers CSV pour la reprise de l'existant. Même structure possible en Excel (.xlsx).

## Règles de format
- **Encodage** : UTF-8.
- **Séparateur** : `;` (ouverture directe dans Excel FR). L'import acceptera aussi `,` (détection auto).
- **Dates** : format ISO `AAAA-MM-JJ` (ex. 2026-09-15).
- **Booléens** : `oui` / `non`.
- **Liens entre fichiers** : on relie les lignes par des **codes** (code entité, matricule,
  identifiant matériel), pas par les libellés. Remplir d'abord `entites.csv` et `applications.csv`.

## Ordre d'import conseillé
1. `entites.csv`        - les filiales / entités
2. `applications.csv`   - le catalogue d'applications
3. `utilisateurs.csv`   - les salariés (référencent une entité)
4. `materiel.csv`       - les actifs
5. `affectations.csv`   - qui détient quoi aujourd'hui
6. `acces_applicatifs.csv` - les accès applicatifs par salarié

Priorité pour une première reprise : 1, 3, 4, 5. Les applications et accès peuvent aussi se
saisir ensuite dans l'interface.

## Validation
À l'import, chaque fichier est prévisualisé ; les lignes en erreur (code inconnu, date invalide,
doublon de n° de série...) sont signalées et rejetées sans bloquer les lignes valides.
