# Connecteur Active Directory local (LDAP / LDAPS)

Le connecteur Active Directory local est **facultatif** et strictement **reserve au role `demandeur`** (portail salarie *Mes tickets* et *Mon materiel*). Il est concu pour les structures qui disposent d'un Active Directory sur site sans Microsoft 365 / Entra ID.

> **Statut de verification** : ce connecteur a ete valide automatiquement contre un annuaire LDAP simule (`tests/ldap_check.py`), mais **n'a pas ete teste contre un controleur de domaine Active Directory reel**. Testez-le en recette avant toute mise en production.

## 1. Principes de securite

- **Role `demandeur` uniquement** : aucun groupe Active Directory ne permet d'obtenir les roles `informatique`, `rh` ou `lecture`.
- **Variables d'environnement uniquement** : les adresses de serveurs, le port, le mode TLS, le certificat CA, le DN de base, le compte de service (`KIKAN_LDAP_BIND_DN`) et son mot de passe (`KIKAN_LDAP_BIND_PASSWORD`) sont configures uniquement dans `.env` (jamais modifiables depuis l'interface, jamais affiches ni stockes en base).
- **Chiffrement obligatoire en production** : seul `ldaps` (port 636) ou `starttls` (port 389) est accepte. Le certificat serveur est toujours verifie (`ssl.CERT_REQUIRED`).
- **Bind en deux temps** : compte de service en lecture seule -> recherche du DN exact (avec echappement strict RFC 4515) -> bind simple avec le DN utilisateur et le mot de passe saisi -> fermeture immediate. Les mots de passe vides sont systematiquement refuses.
- **Aiguillage strict dans `/auth/login`** : un compte Kikan `local` (y compris les comptes `informatique`, `rh` et secours) est verifie uniquement en local par `bcrypt` ; son mot de passe n'est **jamais** envoye a l'annuaire AD.
- **Liaison stable par `external_uid`** : a la premiere connexion uniquement, Kikan rattache l'utilisateur a sa fiche salarie active unique selon l'attribut de correspondance configure (`mail` ou `userPrincipalName` rapproches de `users.email`, ou `sAMAccountName` rapproche de `users.matricule`), avec conversion sans doublon si un compte local `demandeur` existait deja. Aux connexions suivantes, seul `objectGUID` (`accounts.external_uid`) fait foi.
  - **Attention (`sAMAccountName`)** : ne choisissez `sAMAccountName` que si votre organisation garantit l'egalite stricte et l'unicite `sAMAccountName = matricule` dans Kikan. Si un identifiant AD (par exemple `1234`) coincide avec le matricule d'un autre salarie, le compte AD serait lie a la mauvaise fiche (acces aux tickets et au materiel de cette personne). En cas de doute, utilisez `mail` ou `userPrincipalName`.

## 2. Configuration dans `.env`

Deposez le certificat de l'autorite interne de votre domaine (format PEM) dans `./ca/ad-ca.pem`, puis renseignez `.env` :

```env
KIKAN_LDAP_HOSTS=dc1.exemple.local,dc2.exemple.local
KIKAN_LDAP_PORT=636
KIKAN_LDAP_TLS=ldaps
KIKAN_LDAP_CA_BUNDLE=/ca/ad-ca.pem
KIKAN_LDAP_BASE_DN=DC=exemple,DC=local
KIKAN_LDAP_BIND_DN=CN=svc-kikan-ro,OU=ServiceAccounts,DC=exemple,DC=local
KIKAN_LDAP_BIND_PASSWORD=<mot de passe fort du compte lecture seule>
KIKAN_LDAP_TIMEOUT_SEC=5
```

Puis rechargez : `docker compose up -d`.

## 3. Activation dans Kikan

Connectez-vous avec un compte `informatique`, puis ouvrez **Parametrage > Authentification > Annuaire Active Directory (LDAP / LDAPS)** :

1. Verifiez que la configuration d'environnement est complete.
2. Cliquez sur **Tester la connexion LDAP** (verifie le bind du compte de service et l'acces a `KIKAN_LDAP_BASE_DN`).
3. Choisissez l'**attribut de correspondance** (`mail` par defaut, `userPrincipalName` ou `sAMAccountName`) et, si souhaite, le **DN du groupe AD autorise** (ex. `CN=Kikan-Demandeurs,OU=Groupes,DC=exemple,DC=local`).
4. Cochez **Activer l'authentification AD/LDAP** et enregistrez.

## 4. Seuil de verrouillage Active Directory

Kikan limite les tentatives de connexion a **5 echecs** par couple (adresse IP, identifiant) avant de bloquer temporairement la saisie (`429`). Verifiez que votre strategie de verrouillage de compte Active Directory (GPO *Account Lockout Threshold*) est **strictement superieure** a 5 (par exemple 10 tentatives), afin qu'une erreur de frappe repetee sur Kikan ne verrouille pas la session Windows du salarie.

## 5. Depannage

| Symptôme | Cause probable |
|---|---|
| `401 Identifiants invalides` | Mot de passe incorrect, utilisateur hors `KIKAN_LDAP_BASE_DN`, absent du groupe AD autorise, compte LDAP desactive, aucune fiche salarie active correspondante, plusieurs fiches actives avec le meme attribut, ou salarie passe `sorti` (refus uniforme pour ne jamais confirmer un mot de passe AD valide). |
| `502 Annuaire LDAP injoignable` au test | Pare-feu, port `636`/`389`, certificat CA manquant dans `./ca`, ou identifiants du compte de service invalides. |
