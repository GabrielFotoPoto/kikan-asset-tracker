# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Claude, Anthropic).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Faux fournisseur d'identite INTERACTIF pour essayer la connexion Microsoft 365 dans un navigateur (DEVELOPPEMENT).

Il propose une page de connexion simulee (identifiant, roles, MFA) puis renvoie vers Kikan avec un vrai code
d'autorisation ; la decouverte, les cles et l'echange de jeton (PKCE) suivent le protocole. Ne jamais l'utiliser
ailleurs qu'en developpement. Voir tests/sso-e2e.override.yml.

  docker exec -i kikan-api sh -c "cat > /tmp/mock.py" < tests/sso_mock_idp.py
  docker exec -d kikan-api python /tmp/mock.py
Pour un essai automatise, ecrire l'identite voulue dans /tmp/mock_identity.json du conteneur, par exemple
{"upn": "alice.test@exemple.test", "name": "Alice Test", "roles": ["Kikan.IT"], "mfa": true} : elle est alors approuvee
sans page de connexion (supprimer le fichier pour revenir a la page interactive).
"""
import base64
import hashlib
import html
import http.server
import json
import os
import secrets
import time
import urllib.parse
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT, SECRET = "kikan-test-client", "test-secret-for-mock-idp"
PORT = 9910
AUTH = f"http://127.0.0.1:{PORT}"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CODES = {}
AUTO_FILE = "/tmp/mock_identity.json"  # si ce fichier existe, l'identite qu'il decrit est approuvee sans page de connexion


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, status=200, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else json.dumps(body).encode())
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _approve(self, f):
        """Emet un code d'autorisation pour l'identite decrite par `f` et renvoie l'adresse de retour."""
        code = secrets.token_urlsafe(16)
        upn = f.get("upn", "").strip().lower()
        roles = [r for flag, r in (("role_it", "Kikan.IT"), ("role_rh", "Kikan.RH")) if f.get(flag)]
        CODES[code] = {"nonce": f.get("nonce", ""), "challenge": f.get("code_challenge", ""), "redirect_uri": f.get("redirect_uri", ""),
                       "claims": {"oid": str(uuid.uuid5(uuid.NAMESPACE_DNS, upn)), "upn": upn, "name": f.get("name", ""),
                                  "roles": roles, "amr": ["pwd", "mfa"] if f.get("mfa") else ["pwd"]}}
        return f.get("redirect_uri", "") + "?" + urllib.parse.urlencode({"code": code, "state": f.get("state", "")})

    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        if path.path == f"/{TENANT}/v2.0/.well-known/openid-configuration":
            return self._send({"issuer": f"{AUTH}/{TENANT}/v2.0", "authorization_endpoint": f"{AUTH}/{TENANT}/oauth2/v2.0/authorize",
                               "token_endpoint": f"{AUTH}/{TENANT}/oauth2/v2.0/token", "jwks_uri": f"{AUTH}/{TENANT}/discovery/v2.0/keys"})
        if path.path == f"/{TENANT}/discovery/v2.0/keys":
            jwk = json.loads(RSAAlgorithm.to_jwk(KEY.public_key()))
            jwk.update(kid="kid1", use="sig", alg="RS256")
            return self._send({"keys": [jwk]})
        if path.path == f"/{TENANT}/oauth2/v2.0/authorize":
            q = urllib.parse.parse_qs(path.query)
            if os.path.exists(AUTO_FILE):
                ident = json.load(open(AUTO_FILE, encoding="utf-8"))
                form = {k: v[0] for k, v in q.items()}
                form.update(upn=ident["upn"], name=ident.get("name", "Test"), mfa="1" if ident.get("mfa", True) else "")
                for flag, role in (("role_it", "Kikan.IT"), ("role_rh", "Kikan.RH")):
                    form[flag] = "1" if role in ident.get("roles", []) else ""
                return self._send(b"", 302, headers={"Location": self._approve(form)})
            hidden = "".join(f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v[0])}">' for k, v in q.items())
            page = f"""<!doctype html><meta charset="utf-8"><title>Microsoft (simulation)</title>
<body style="font-family:Segoe UI,Arial;max-width:420px;margin:60px auto"><h2>Connexion Microsoft 365 (simulation)</h2>
<p>Faux fournisseur d'identite de developpement.</p>
<form method="post" action="{path.path}">{hidden}
<p><label>Nom d'utilisateur<br><input name="upn" value="alice.test@exemple.test" style="width:100%"></label></p>
<p><label>Nom affiche<br><input name="name" value="Alice Test" style="width:100%"></label></p>
<p><label><input type="checkbox" name="role_it" value="1" checked> Role Kikan.IT</label><br>
<label><input type="checkbox" name="role_rh" value="1"> Role Kikan.RH</label><br>
<label><input type="checkbox" name="mfa" value="1" checked> MFA effectuee</label></p>
<button type="submit" style="padding:8px 18px">Se connecter</button></form></body>"""
            return self._send(page, ctype="text/html; charset=utf-8")
        self._send({"error": "inconnu"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        f = lambda k: form.get(k, [""])[0]  # noqa: E731
        if self.path.startswith(f"/{TENANT}/oauth2/v2.0/authorize"):
            return self._send(b"", 302, headers={"Location": self._approve({k: v[0] for k, v in form.items()})})
        if self.path == f"/{TENANT}/oauth2/v2.0/token":
            entry = CODES.pop(f("code"), None)
            if f("client_id") != CLIENT or f("client_secret") != SECRET or not entry or f("redirect_uri") != entry["redirect_uri"] \
                    or b64url(hashlib.sha256(f("code_verifier").encode()).digest()) != entry["challenge"]:
                return self._send({"error": "invalid_grant"}, 400)
            c, now = entry["claims"], int(time.time())
            claims = {"iss": f"{AUTH}/{TENANT}/v2.0", "aud": CLIENT, "tid": TENANT, "iat": now, "nbf": now, "exp": now + 3600, "sub": "sub-" + c["oid"],
                      "oid": c["oid"], "preferred_username": c["upn"], "name": c["name"], "email": c["upn"], "roles": c["roles"], "amr": c["amr"],
                      "nonce": entry["nonce"]}
            pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            return self._send({"id_token": jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "kid1"}), "token_type": "Bearer"})
        self._send({"error": "inconnu"}, 404)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Mock).serve_forever()
