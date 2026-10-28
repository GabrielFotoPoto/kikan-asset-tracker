# Connexion Microsoft 365 (SSO) : procédure d'installation

La connexion Microsoft 365 est **facultative**. Tant qu'elle n'est pas activée, Kikan fonctionne en connexion locale.
Cette procédure s'adresse à la personne qui administre Entra ID (anciennement Azure AD) et à l'administrateur de Kikan.

Kikan utilise **OpenID Connect** (code d'autorisation avec PKCE), côté serveur, pour **un seul tenant**. Le rôle de
chaque personne vient de **rôles d'application** Entra (`Kikan.IT`, `Kikan.RH`). La MFA est celle de votre tenant.

## 1. Prérequis

- Un administrateur Entra pouvant créer une inscription d'application (rôle « Administrateur d'application » ou plus).
- L'**adresse publique HTTPS** de Kikan, par exemple `https://kikan.exemple.fr` (le nom d'hôte que les utilisateurs
  tapent dans leur navigateur). Entra n'accepte une adresse de retour HTTP que pour `localhost`.
- Le serveur Kikan doit pouvoir joindre **`login.microsoftonline.com` en HTTPS** (sortant). Si votre réseau passe par
  un proxy ou inspecte le trafic HTTPS, voir « Réseau » plus bas.
- L'horloge du serveur doit être à l'heure (NTP) : les jetons Microsoft ont une durée de validité courte (tolérance de 60 s).

## 2. Inscrire l'application dans Entra

1. Centre d'administration Entra, **Applications**, **Inscriptions d'applications**, **Nouvelle inscription**.
2. Nom : `Kikan`. Types de comptes pris en charge : **Comptes dans cet annuaire organisationnel uniquement** (locataire unique).
3. URI de redirection : plateforme **Web**, valeur `https://<votre-hôte>/api/auth/sso/callback`
   (la valeur exacte est affichée dans Kikan, Paramétrage, onglet Authentification).
4. Sur la page de présentation, notez l'**ID d'application (client)** et l'**ID de l'annuaire (locataire)**.

## 3. Créer le secret du client

1. **Certificats et secrets**, **Nouveau secret client** : choisissez une durée (24 mois au maximum).
2. **Copiez la valeur immédiatement** (elle n'est plus affichée ensuite) et notez la **date d'expiration**.
3. Aucune autorisation d'API supplémentaire n'est nécessaire (Kikan ne lit que l'identité de la personne : `openid`, `profile`, `email`).

## 4. Créer les rôles d'application

Dans l'inscription : **Rôles d'application**, **Créer un rôle d'application** (deux fois) :

| Nom d'affichage | Types de membres autorisés | Valeur | Description |
|---|---|---|---|
| Kikan informatique | Utilisateurs/Groupes | `Kikan.IT` | Administration de Kikan (équipe informatique) |
| Kikan RH | Utilisateurs/Groupes | `Kikan.RH` | Gestion des salariés (équipe RH) |

Les valeurs doivent correspondre aux noms de rôles configurés dans Kikan (par défaut `Kikan.IT` et `Kikan.RH`).
Le rôle **lecture seule** n'existe que pour les comptes locaux.

## 5. Réserver l'accès aux deux équipes

1. **Applications d'entreprise**, **Kikan**, **Propriétés** : **Affectation requise ?** sur **Oui**.
   Seules les personnes affectées peuvent alors obtenir un jeton pour Kikan (deuxième verrou, en plus de Kikan).
2. **Utilisateurs et groupes**, **Ajouter** : affectez le groupe `Kikan-IT` au rôle *Kikan informatique* et le groupe
   `Kikan-RH` au rôle *Kikan RH*. L'affectation par **groupe** demande en principe une licence Entra ID P1 ou supérieure
   (incluse dans plusieurs offres Microsoft 365) : à vérifier selon votre licence. Sans elle, affectez les personnes une par une.

## 6. Exiger la MFA

Par **Accès conditionnel** (stratégie ciblant l'application Kikan et exigeant l'authentification multifacteur) ou par les
valeurs de sécurité par défaut du tenant. Kikan peut **refuser** toute connexion dont le jeton ne prouve pas la MFA
(réglage « Exiger que la MFA apparaisse dans le jeton », activé par défaut). Si votre accès conditionnel ne la fait pas
apparaître (certains cas d'appareil de confiance), désactivez ce réglage dans Kikan.

## 7. Configurer Kikan

Dans le fichier `.env` du serveur (jamais ailleurs : le secret n'est ni stocké en base ni affiché) :

```
KIKAN_PUBLIC_URL=https://kikan.exemple.fr
KIKAN_SSO_TENANT_ID=<ID de l'annuaire>
KIKAN_SSO_CLIENT_ID=<ID d'application (client)>
KIKAN_SSO_CLIENT_SECRET=<valeur du secret>
```

Puis `docker compose up -d` pour recharger. Dans Kikan (compte informatique), **Paramétrage, Authentification** :

1. Vérifiez que l'environnement est « configuré » et que l'**adresse de retour** affichée est bien celle déclarée dans Entra.
2. Renseignez la **date d'expiration du secret** (Kikan avertit 30 jours avant).
3. **Tester la configuration** : vérifie que Microsoft est joignable et que ses clés de signature sont lues.
4. **Tester ma connexion Microsoft 365** : vous êtes renvoyé vers Microsoft, puis vers Kikan avec le résultat (identité et
   rôle reçus). Le test exige que **votre** identité Microsoft ait le rôle informatique.
5. Vérifiez qu'au moins un **compte local de secours** existe (page Comptes, case « Secours »).
6. **Activer le SSO**. La page de connexion propose alors le bouton « Se connecter avec Microsoft 365 », et la connexion
   par mot de passe est réservée aux comptes de secours (réglage modifiable).

## 8. Comptes

- Un membre autorisé obtient son **compte nominatif** à sa première connexion (nom et e-mail repris de Microsoft). Son rôle
  est **resynchronisé à chaque connexion** : retiré du groupe, il est déclassé (ou refusé s'il n'a plus aucun rôle).
- Un **compte local existant** n'est jamais rapproché automatiquement par e-mail. Pour le conserver, utilisez
  « Lier à Microsoft 365 » (page Comptes) en indiquant le nom d'utilisateur Microsoft : la première connexion SSO de cette
  personne est rattachée à ce compte.
- Un compte **désactivé dans Kikan** reste refusé même si Microsoft accepte la personne.

## 9. Dépannage

| Message à la connexion | Cause probable |
|---|---|
| « n'a pas de rôle Kikan » | La personne n'est pas dans un groupe affecté à `Kikan.IT` ou `Kikan.RH` (ou les noms de rôles diffèrent). |
| « authentification multifacteur requise » | Le jeton ne contient pas la MFA : accès conditionnel manquant, ou désactivez le réglage. |
| « réponse de Microsoft... vérifiée » | Mauvais tenant ou identifiant client, secret expiré ou erroné, horloge du serveur décalée. |
| « Microsoft est injoignable » | Pare-feu, proxy ou inspection TLS : voir ci-dessous. |
| « compte désactivé... ou déjà utilisé » | Compte désactivé dans Kikan, ou identifiant local identique à celui de la personne : lier le compte. |

Le **journal d'audit** (informatique) contient chaque refus avec son motif (jamais de jeton ni de secret).

## 10. Réseau

Variables facultatives du `.env` : `KIKAN_SSO_PROXY` (proxy HTTPS sortant) et `KIKAN_SSO_CA_BUNDLE` (autorité de
certification interne si votre réseau inspecte le trafic, comme pour WebDAV : déposer le PEM dans `./ca`).

## 11. Renouvellement du secret

Créez un nouveau secret dans Entra **avant** l'expiration de l'ancien, mettez à jour `KIKAN_SSO_CLIENT_SECRET`, redémarrez
l'API, puis testez la configuration. Mettez à jour la date d'expiration dans Kikan.

## 12. Retour arrière

**Paramétrage, Authentification, Désactiver le SSO** : la connexion par mot de passe est immédiatement rendue à tous les
comptes locaux. Si l'interface est inaccessible, connectez-vous avec un compte de secours.

## 13. Limites à connaître

- Retirer une personne d'Entra **n'interrompt pas** sa session Kikan déjà ouverte : elle dure jusqu'à son expiration
  (4 h par défaut, réglable de 30 minutes à 12 heures). Désactiver le compte dans Kikan coupe immédiatement.
- Les comptes créés par Microsoft 365 n'ont pas de mot de passe local ; ils ne peuvent pas être des comptes de secours.
- Tests : `tests/sso_check.py` joue tout le protocole contre un faux fournisseur d'identité (voir
  `tests/sso-test.override.yml`) ; il ne remplace pas la validation sur votre vrai tenant.
