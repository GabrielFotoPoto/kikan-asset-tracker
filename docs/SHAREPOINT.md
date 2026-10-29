# Stockage des PDF scellés dans SharePoint Online

Kikan peut déposer les **PDF scellés** (remises et restitutions) dans une **bibliothèque de documents SharePoint Online**, par
l'API Microsoft Graph. Un seul moteur de stockage est actif à la fois (`KIKAN_STORAGE_BACKEND=sharepoint`). Seuls les PDF
scellés partent dans SharePoint : les chartes restent dans le volume local de Kikan.

Comme pour SMB et WebDAV, le PDF est d'abord écrit dans le tampon local de Kikan, puis déposé, **relu et comparé par empreinte
SHA-256** avant que le tampon soit purgé. Si SharePoint est indisponible, la signature n'échoue pas : le document reste en local
et est déposé plus tard (au démarrage ou par *Reprendre les dépôts en attente*).

> **Statut de validation** : le moteur est testé automatiquement contre un faux service Microsoft Graph (dépôt, relecture,
> fichiers de plus de 4 Mio, redirection de téléchargement, jeton expiré, limitation de débit, panne, droits). **Il n'a pas été
> essayé sur un vrai tenant** : suivez la procédure ci-dessous, puis le bouton *Tester la connexion* de la page Stockage
> (dépôt, relecture, suppression d'un fichier d'essai) valide l'ensemble en quelques secondes.

## Arborescence

```
<bibliothèque>/<dossier>/<année>/AAAA_MM_JJ_NOM_PRENOM_ACR_NNN.pdf
```

## 1. Application Entra ID

Dans le centre d'administration Entra (le même tenant que pour le SSO) :

1. **Inscriptions d'applications, Nouvelle inscription** : nom `Kikan stockage`, un seul locataire. Notez l'**identifiant de
   l'application (client)** et l'**identifiant du locataire (tenant)**.
2. **Certificats et secrets, Nouveau secret client** : notez la **valeur** (affichée une seule fois) et sa date d'expiration.
3. **Autorisations d'API, Ajouter, Microsoft Graph, Autorisations de l'application** : ajoutez **`Sites.Selected`** (et rien
   d'autre), puis **Accorder le consentement administrateur**.

`Sites.Selected` ne donne **aucun accès** tant qu'un administrateur n'a pas accordé l'application à un site précis : Kikan ne peut
donc jamais lire ni écrire ailleurs dans SharePoint.

## 2. Donner à l'application l'accès au seul site voulu

Avec un compte administrateur SharePoint, au choix :

**PnP PowerShell**

```powershell
Connect-PnPOnline -Url https://societe-admin.sharepoint.com -Interactive
Grant-PnPAzureADAppSitePermission -AppId <client-id> -DisplayName "Kikan stockage" `
    -Site https://societe.sharepoint.com/sites/Kikan -Permissions Write
```

**Ou Microsoft Graph** (application disposant de `Sites.FullControl.All`) :

```
POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions
{"roles": ["write"], "grantedToIdentities": [{"application": {"id": "<client-id>", "displayName": "Kikan stockage"}}]}
```

Le rôle `write` suffit (dépôt, relecture, suppression de l'essai).

## 3. Configurer Kikan

Dans le fichier `.env` (jamais dans l'interface) :

```
KIKAN_STORAGE_BACKEND=sharepoint
KIKAN_SHAREPOINT_TENANT_ID=<tenant>
KIKAN_SHAREPOINT_CLIENT_ID=<client>
KIKAN_SHAREPOINT_CLIENT_SECRET=<valeur du secret>
KIKAN_SHAREPOINT_SITE=societe.sharepoint.com:/sites/Kikan
KIKAN_SHAREPOINT_LIBRARY=Documents
KIKAN_SHAREPOINT_FOLDER=Kikan
# KIKAN_SHAREPOINT_CA_BUNDLE=   # autorité de certification interne (proxy d'inspection TLS), facultatif
# KIKAN_SHAREPOINT_PROXY=       # facultatif
```

Puis `docker compose up -d api`, et **Stockage, Tester la connexion** : le message doit être *« écriture, lecture et suppression
réussies »*.

Messages d'erreur courants : *authentification refusée* (identifiant, secret ou consentement), *droits insuffisants*
(permission `Sites.Selected` non accordée au site, ou rôle en lecture seule), *site introuvable* (`KIKAN_SHAREPOINT_SITE`),
*bibliothèque introuvable* (nom exact de la bibliothèque, souvent `Documents`).

## Sécurité

- Secret client uniquement dans l'environnement (jamais en base, jamais affiché ni journalisé). **Pensez à son expiration** :
  renouvelez-le avant la date.
- Certificat du serveur toujours vérifié ; HTTPS obligatoire (HTTP n'existe que pour les essais).
- L'adresse de téléchargement fournie par Graph est appelée **sans** en-tête d'autorisation (le jeton ne part jamais vers un autre
  serveur) ; les redirections inattendues sont refusées.
- Fichiers de plus de 4 Mio : session de téléversement par blocs de 10 Mio ; jeton renouvelé automatiquement s'il expire ou est
  rejeté ; nouvelle tentative après une limitation de débit (429).
- Dans SharePoint, activez le **versionnage** et une **étiquette de rétention** adaptée à la durée de conservation des remises :
  Kikan ne supprime jamais un PDF scellé dans SharePoint : la purge RGPD liste les documents à supprimer, l'équipe de la GED les supprime ([RGPD.md](RGPD.md)).

## Changer de moteur

*Stockage, Copier vers le stockage actif* copie les documents rangés sur un autre emplacement distant (SMB, WebDAV...) vers
SharePoint : simulation d'abord, puis copie ; chaque copie est relue et comparée à l'empreinte enregistrée avant que la référence
change, et **rien n'est supprimé de l'ancien emplacement**. Les anciens emplacements doivent rester configurés pendant la copie.
Les documents encore dans le tampon local sont repris par *Reprendre les dépôts en attente*.
