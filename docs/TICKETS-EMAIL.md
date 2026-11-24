# Passerelle e-mail vers tickets (exemple externe n8n)

Kikan n'embarque pas de client IMAP/POP3 afin de conserver une surface d'attaque minimale. Pour transformer les messages d'une boite de support (ex. `support@entreprise.fr`) en tickets Kikan, utilisez un orchestrateur externe (comme **n8n**) qui appelle l'API `/api/v1/tickets/{id_externe}`.

> **Statut de verification** : ce flux d'exemple est documente a titre de modele et **n'a pas ete teste de bout en bout sur une vraie boite aux lettres de production**. Testez-le d'abord avec `?dry_run=1` puis sur une boite de recette.

## Principes de securite et d'idempotence

1. **Jeton dedie a droits minimaux** : creez dans *Parametrage > Integrations* un jeton avec le systeme `mail_bridge` et uniquement le droit `tickets_ecriture` (aucun droit `tickets_lecture` ni `tickets_interne` n'est necessaire pour creer des tickets).
2. **Idempotence par `Message-ID`** : passez un identifiant derive du `Message-ID` de l'e-mail (tronque ou hache SHA-256 a 64 caracteres) comme `id_externe` dans `PUT /api/v1/tickets/{id_externe}`. Si n8n rejoue le meme message, Kikan ne cree aucun doublon.
3. **Expediteur non verifie** : envoyez toujours `"canal": "email"`. Kikan positionne automatiquement `demandeur_verifie = false` pour signaler a l'equipe IT que l'identite de l'expediteur provient d'un en-tete e-mail (a verifier avant toute action sensible comme une reinitialisation de mot de passe ou un changement de droits).
4. **Correspondance salarie stricte** : passez `"demandeur_email": "<adresse expediteur>"`. Si 0 ou plusieurs fiches actives correspondent, Kikan renvoie `422` : le workflow peut alors retenter sans `demandeur_email` (avec `entite_code` par defaut) ou diriger le message vers une file de triage.
5. **Etape IA facultative** : si vous intercalez un modele IA local (ex. Ollama) pour proposer `nature_code` et `criticite`, validez sa sortie sur la liste fermee des codes de Kikan (`panne_materiel`, `perte_vol_materiel`, `incident_logiciel`, `reseau`, `acces_compte`, `message_suspect`, `demande_service`, `autre`) et n'envoyez jamais de donnees personnelles vers un service cloud non autorise.

## Exemple d'appel `curl`

```bash
TOKEN=kik_xxxxxxxx
URL=https://kikan.entreprise.local/api
MSG_HASH="mail-9f86d081884c7d659a2feaa0c55ad015"

curl -s -X PUT "$URL/v1/tickets/$MSG_HASH" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nature_code": "panne_materiel",
    "criticite": "moyenne",
    "titre": "Ecran externe noir au branchement USB-C",
    "description": "Bonjour, mon ecran ne s allume plus depuis ce matin.",
    "canal": "email",
    "demandeur_email": "camille.martin@entreprise.local"
  }'
```

## Squelette de workflow n8n (importable)

Enregistrez le JSON ci-dessous dans un fichier `.json`, importez-le dans n8n, puis renseignez vos identifiants IMAP/Microsoft 365 et le jeton `KIKAN_API_TOKEN` :

```json
{
  "name": "Kikan - Boite support vers tickets",
  "nodes": [
    {
      "name": "Email Trigger (IMAP)",
      "type": "n8n-nodes-base.emailReadImap",
      "typeVersion": 2,
      "position": [240, 300],
      "parameters": {
        "mailbox": "INBOX",
        "postProcessAction": "read"
      }
    },
    {
      "name": "Normaliser et hacher Message-ID",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [480, 300],
      "parameters": {
        "jsCode": "const crypto = require('crypto');\nreturn items.map(item => {\n  const msgId = String(item.json.messageId || item.json.uid || Date.now());\n  const idExterne = 'mail-' + crypto.createHash('sha256').update(msgId).digest('hex').slice(0, 40);\n  const from = String(item.json.from?.value?.[0]?.address || '').trim().toLowerCase();\n  const titre = String(item.json.subject || 'Demande par e-mail').slice(0, 200);\n  const desc = String(item.json.text || '').slice(0, 5000);\n  return { json: { idExterne, from, titre, desc, nature_code: 'autre', criticite: 'moyenne' } };\n});"
      }
    },
    {
      "name": "Creer ticket Kikan",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4,
      "position": [740, 300],
      "parameters": {
        "method": "PUT",
        "url": "={{ 'https://kikan.entreprise.local/api/v1/tickets/' + $json.idExterne }}",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            { "name": "Authorization", "value": "={{ 'Bearer ' + $env.KIKAN_API_TOKEN }}" }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ nature_code: $json.nature_code, criticite: $json.criticite, titre: $json.titre, description: $json.desc, canal: 'email', demandeur_email: $json.from || null }) }}"
      }
    }
  ],
  "connections": {
    "Email Trigger (IMAP)": { "main": [[{ "node": "Normaliser et hacher Message-ID", "type": "main", "index": 0 }]] },
    "Normaliser et hacher Message-ID": { "main": [[{ "node": "Creer ticket Kikan", "type": "main", "index": 0 }]] }
  }
}
```
