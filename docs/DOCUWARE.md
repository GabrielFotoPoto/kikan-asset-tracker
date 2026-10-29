# Stockage des PDF scellés dans DocuWare

Kikan peut déposer les **PDF scellés** (remises et restitutions) dans une **armoire DocuWare**, par l'API REST de la plateforme
(DocuWare Cloud ou serveur interne), avec des **champs d'index** pour retrouver les documents. Un seul moteur de stockage est actif
à la fois (`KIKAN_STORAGE_BACKEND=docuware`). Seuls les PDF scellés partent dans DocuWare : les chartes restent dans le volume
local de Kikan.

Comme pour SMB, WebDAV et SharePoint, le PDF est d'abord écrit dans le tampon local, puis déposé, **relu et comparé par
empreinte SHA-256** avant que le tampon soit purgé ; si DocuWare est indisponible, la signature n'échoue pas et le document est
déposé plus tard.

> **Statut de validation** : le moteur est testé automatiquement contre un faux serveur DocuWare (authentification, armoire,
> dépôt avec index, relecture, intégrité, jeton expiré, panne). **Il n'a pas été essayé sur un vrai DocuWare** : les détails
> du format d'index dépendent de votre armoire. Le bouton *Tester la connexion* de la page Stockage (dépôt d'un PDF d'essai,
> relecture, suppression) valide l'ensemble ; en cas d'erreur, le message reprend le code HTTP et le texte renvoyé par DocuWare.

## 1. Compte de service

Créez dans DocuWare un utilisateur dédié (par exemple `svc-kikan`) **avec mot de passe** (le jeton est obtenu par le service
d'identité de DocuWare, « password grant »), appartenant à un profil qui permet, sur l'armoire cible : **stocker** des documents,
les **télécharger** et les **supprimer** (la suppression ne sert qu'au document d'essai : la purge RGPD ne supprime rien dans DocuWare, voir [RGPD.md](RGPD.md)). Évitez un compte
administrateur. Si votre organisation n'autorise que l'authentification Windows ou SSO, demandez à votre partenaire DocuWare un
compte de service local.

## 2. Armoire et champs d'index

Choisissez (ou créez) une **armoire** dédiée, par exemple `Kikan`. Kikan sait renseigner ces **champs logiques**, que vous associez
aux champs de VOTRE armoire :

| Champ logique | Contenu | Donnée nominative ? |
|---|---|---|
| `type` | `Remise` ou `Restitution` | non |
| `annee` | année du document | non |
| `numero` | numéro de la remise | non |
| `entite` | nom de l'entité du salarié | non |
| `cle` | clé de rangement Kikan sans nom ni prénom (`2026/2026_11_02_GCH_003.pdf`) | non |
| `date` | date de signature | non |
| `matricule` | matricule du salarié | **oui** |
| `salarie` | prénom et nom du salarié | **oui** |

**Un champ non associé n'est jamais envoyé.** Les champs nominatifs ne partent donc que si vous les associez explicitement.

L'association se fait dans `KIKAN_DOCUWARE_FIELDS` (JSON). Une valeur texte désigne un champ de type texte ; pour un champ
numérique ou date, donnez le type :

```
KIKAN_DOCUWARE_FIELDS={"type":"TYPE_DOC","annee":{"champ":"ANNEE","type":"Int"},"numero":{"champ":"NUMERO","type":"Int"},"entite":"ENTITE","date":{"champ":"DATE_SIGNATURE","type":"Date"}}
```

Types acceptés : `String` (par défaut), `Int`, `Date`. **Tout champ obligatoire de l'armoire doit être associé**, sinon DocuWare
refuse le dépôt (le test de connexion le signale). Sans aucune association, le PDF est déposé sans index.

## 3. Configurer Kikan

Dans le fichier `.env` (jamais dans l'interface) :

```
KIKAN_STORAGE_BACKEND=docuware
KIKAN_DOCUWARE_URL=https://societe.docuware.cloud/DocuWare/Platform
KIKAN_DOCUWARE_USER=svc-kikan
KIKAN_DOCUWARE_PASSWORD=<mot de passe>
KIKAN_DOCUWARE_CABINET=Kikan
KIKAN_DOCUWARE_FIELDS={"type":"TYPE_DOC","annee":{"champ":"ANNEE","type":"Int"}}
# KIKAN_DOCUWARE_CA_BUNDLE=   # autorité de certification interne (serveur interne), facultatif
# KIKAN_DOCUWARE_PROXY=       # facultatif
```

L'adresse se termine par `/DocuWare/Platform` (serveur interne : `https://docuware.societe.local/DocuWare/Platform`). Puis
`docker compose up -d api`, et **Stockage, Tester la connexion**.

Messages d'erreur courants : *service d'identité introuvable* (adresse), *authentification refusée* (compte ou mot de passe),
*armoire introuvable* (nom ou identifiant exact), *droits insuffisants* (profil du compte de service), *POST refuse (HTTP 400 : ...)*
(un champ d'index obligatoire ou de mauvais type : corrigez `KIKAN_DOCUWARE_FIELDS`).

## Références

Kikan conserve pour chaque document la référence `docuware:<identifiant du document>/<clé>` : l'identifiant DocuWare sert à relire
et à supprimer le document ; la clé garde le rangement par année. Les documents restent retrouvables dans DocuWare par leurs champs
d'index.

## Sécurité

- Identifiants uniquement dans l'environnement (jamais en base, jamais affichés ni journalisés) ; certificat toujours vérifié ;
  HTTPS obligatoire.
- Jeton renouvelé automatiquement s'il expire ou est rejeté ; nouvelle tentative après une limitation de débit.
- Kikan ne supprime jamais un PDF scellé dans DocuWare (sauf le document d'essai) : la purge RGPD liste les documents, l'équipe DocuWare les supprime.

## Changer de moteur

*Stockage, Copier vers le stockage actif* copie les documents rangés sur un autre emplacement distant (SMB, WebDAV, SharePoint...)
vers DocuWare : simulation d'abord, puis copie relue et comparée à l'empreinte ; les champs d'index sont reconstitués depuis la
base ; **rien n'est supprimé de l'ancien emplacement**.
