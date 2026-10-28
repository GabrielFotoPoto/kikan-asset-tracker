# Modèles d'import Kikan

Fichiers CSV pour la reprise de l'existant. L'import Excel (.xlsx) est prévu en v0.2 ; en attendant, enregistrer le classeur en CSV.

## Règles de format
- **Encodage** : UTF-8 ou Windows-1252 (export Excel), détecté automatiquement.
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

Depuis l'interface (page **Import**), chaque fichier est d'abord **simule** : rien n'est ecrit tant que le
rapport n'est pas propre. Les lignes en erreur (code inconnu, date invalide, doublon de n° de serie...)
sont localisees par numero de ligne ; l'import reel est refuse tant qu'il reste une erreur (tout ou rien).
L'import ne fait que **creer** : un element deja present (meme code, matricule, application ou acces) est ignore.
Ces modeles sont aussi telechargeables depuis la page Import.
