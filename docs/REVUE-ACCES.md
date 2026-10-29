# Revue périodique des droits d'accès

Page **Revue des accès** (menu de gauche). Elle répond à l'exigence de **revue périodique des droits d'accès** de l'ISO 27001 (A.5.18) :
repérer les accès qui ne devraient plus exister, les faire valider par les RH de chaque entité, et conserver une **preuve scellée**.

Tous les rôles consultent la page **dans leur périmètre** (comptes limités à des entités : voir [Cloisonnement par entité](../README.md#cloisonnement-par-entité)).

![Anomalies d'accès détectées](captures/revue-anomalies.png)

## Les quatre onglets

| Onglet | Pour qui | Contenu |
|---|---|---|
| **Anomalies** | tous | accès actifs d'un salarié **sorti**, d'un salarié dont la **date de sortie est dépassée**, ou vers une **application désactivée**. Le nombre apparaît aussi sur le tableau de bord. |
| **Qui a accès à quoi** | tous | tous les accès, avec filtres par entité et par application ; export **Excel** et **CSV** (les cellules sont protégées contre l'injection de formules). |
| **Revues** | tous (lancer : informatique) | les campagnes de validation. |
| **Retraits à confirmer** | informatique | les accès retirés dans Kikan et qui restent à retirer dans l'application concernée. |

## Déroulement d'une revue

1. **Lancer** (informatique) : titre, date limite facultative, entités et applications concernées (rien de coché = tout). Une ligne est créée pour
   **chaque accès actif**, avec son éventuelle anomalie. Une seule revue peut être en cours à la fois.
2. **Décider** (RH dans leur périmètre, informatique) : cocher des lignes puis **Maintenir** ou **À retirer**, avec un commentaire facultatif.
   Un RH ne voit et ne décide que sur les accès des salariés de ses entités ; hors périmètre, la ligne n'existe pas (404). Le rôle *lecture* consulte seulement.
   Une décision se corrige tant que la revue est en cours (*Remettre à traiter*).
3. **Clôturer** (informatique) : possible uniquement quand **toutes** les lignes sont décidées. À la clôture :
   - les accès « à retirer » passent à **non** dans Kikan (la ligne et son historique sont conservés) ;
   - un **rapport PDF scellé** (signature PAdES, comme les remises) est enregistré dans le stockage actif, avec son empreinte SHA-256 ;
   - les retraits deviennent des tâches.
4. **Confirmer les retraits** (informatique) : Kikan est un **registre**, il ne coupe pas le droit dans l'application. Une fois l'action faite dans l'application
   (annuaire, ERP...), cocher *Retiré dans le système*. La confirmation est journalisée.

Le rapport scellé reprend le périmètre, les dates, les relecteurs et chaque décision. Il désigne les personnes **par leur matricule** (jamais le nom).
Il se télécharge depuis la revue clôturée (informatique) ; Kikan vérifie son empreinte à chaque téléchargement.

![Une revue en cours : les accès à retirer sont décidés](captures/revue-campagne.png)

*Captures réalisées avec le jeu de données de démonstration.*

## Rappels par e-mail

Réglage *Paramétrage, E-mails* (actif par défaut, relance hebdomadaire, informatique, nombres seulement) :
- une revue en cours dont **l'échéance approche** (7 jours) ou est dépassée avec des accès à traiter ;
- des **retraits non confirmés** depuis plus d'une semaine ;
- **aucune revue clôturée depuis plus d'un an** : la revue annuelle est à lancer.

## Traçabilité

Le journal d'audit enregistre le lancement, les décisions (nombre et choix), la clôture (empreinte du rapport) et les confirmations de retrait, sans nom
ni commentaire.

## Limites à connaître

- Le rapport scellé est une **preuve** : il est conservé avec les autres PDF scellés (stockage choisi, sauvegardes). Il ne contient que des matricules, mais un matricule
  reste un identifiant : à mentionner dans le registre des traitements.
- La purge RGPD d'un salarié supprime ses lignes de revue en base ; elle n'efface pas les rapports scellés déjà produits (pièces d'audit).
- Les relecteurs sont des **comptes Kikan** (RH, informatique). Un responsable d'équipe sans compte ne peut pas relire : les RH valident pour son entité.

## Tests

`tests/revue_check.py` (anomalies, rapport, droits, cloisonnement, décisions, clôture scellée, retraits, rappels, purge RGPD) ; voir [SECURITY.md](../SECURITY.md).
