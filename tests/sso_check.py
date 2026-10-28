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

"""Tests de la connexion Microsoft 365 (SSO) contre un FAUX fournisseur d'identite local (instance de DEVELOPPEMENT).

Prerequis : l'API doit tourner avec tests/sso-test.override.yml (voir ce fichier). Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/sso_check.py

Le test joue le role du navigateur et du fournisseur d'identite (decouverte, cles, jeton signe, PKCE) ; il ne remplace
pas la validation avec le vrai tenant (procedure : docs/SSO.md). Fichier ASCII uniquement. Code de sortie 1 si echec.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT, SECRET = "kikan-test-client", "test-secret-for-mock-idp"
PORT = 9910
AUTH = f"http://127.0.0.1:{PORT}"
ISS = f"{AUTH}/{TENANT}/v2.0"
PUBLIC = "https://kikan.test"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


# ------------------------------------------------------------------ faux fournisseur d'identite
KEYS = {"kid1": rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "kid2": rsa.generate_private_key(public_exponent=65537, key_size=2048)}
PUBLISHED = ["kid1"]
CODES = {}
MODE = {"discovery_issuer": None, "token_host": None, "redirect": False, "slow": False, "big": False}


def pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_token(spec, nonce, kid="kid1", alg="RS256", key=None):
    now = int(time.time())
    claims = {"iss": ISS, "aud": CLIENT, "tid": TENANT, "iat": now, "nbf": now, "exp": now + 3600, "sub": "sub-" + spec["oid"],
              "oid": spec["oid"], "preferred_username": spec["upn"], "name": spec.get("name", "Test User"),
              "email": spec["upn"], "roles": spec.get("roles", ["Kikan.IT"]), "amr": spec.get("amr", ["pwd", "mfa"]), "nonce": nonce}
    for k, v in (spec.get("over") or {}).items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    if alg == "none":
        return b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode()) + "." + b64url(json.dumps(claims).encode()) + "."
    if alg == "HS256":  # confusion de cle : jeton signe avec la cle publique comme secret
        public_pem = KEYS["kid1"].public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        return b64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "kid1"}).encode()) + "." + b64url(json.dumps(claims).encode()) + "." + \
            b64url(__import__("hmac").new(public_pem, (b64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "kid1"}).encode()) + "." + b64url(json.dumps(claims).encode())).encode(), hashlib.sha256).digest())
    return jwt.encode(claims, pem(key or KEYS[kid]), algorithm="RS256", headers={"kid": kid})


class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, status=200):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == f"/{TENANT}/v2.0/.well-known/openid-configuration":
            if MODE["redirect"]:
                self.send_response(302)
                self.send_header("Location", f"{AUTH}/ailleurs")
                self.end_headers()
                return
            if MODE["slow"]:
                time.sleep(15)
            if MODE["big"]:
                return self._send(b"{" + b'"x":"' + b"a" * 2_000_000 + b'"}')
            host = MODE["token_host"] or AUTH
            return self._send({"issuer": MODE["discovery_issuer"] or ISS, "authorization_endpoint": f"{AUTH}/{TENANT}/oauth2/v2.0/authorize",
                               "token_endpoint": f"{host}/{TENANT}/oauth2/v2.0/token", "jwks_uri": f"{AUTH}/{TENANT}/discovery/v2.0/keys"})
        if self.path == f"/{TENANT}/discovery/v2.0/keys":
            keys = []
            for kid in PUBLISHED:
                jwk = json.loads(RSAAlgorithm.to_jwk(KEYS[kid].public_key()))
                jwk.update(kid=kid, use="sig", alg="RS256")
                keys.append(jwk)
            return self._send({"keys": keys})
        self._send({"error": "inconnu"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        f = lambda k: form.get(k, [""])[0]  # noqa: E731
        if self.path != f"/{TENANT}/oauth2/v2.0/token":
            return self._send({"error": "inconnu"}, 404)
        if f("client_id") != CLIENT or f("client_secret") != SECRET or f("grant_type") != "authorization_code":
            return self._send({"error": "invalid_client"}, 401)
        entry = CODES.pop(f("code"), None)  # un code ne sert qu'une fois
        if not entry:
            return self._send({"error": "invalid_grant"}, 400)
        if f("redirect_uri") != entry["redirect_uri"] or b64url(hashlib.sha256(f("code_verifier").encode()).digest()) != entry["challenge"]:
            return self._send({"error": "invalid_grant"}, 400)  # PKCE ou adresse de retour incorrects
        spec = entry["spec"]
        token = spec["raw"] if spec.get("raw") else make_token(spec, entry["nonce"], kid=spec.get("kid", "kid1"), alg=spec.get("alg", "RS256"))
        return self._send({"id_token": token, "token_type": "Bearer"})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


srv = Server(("127.0.0.1", PORT), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()


# ------------------------------------------------------------------ navigateur simule
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def raw(method, path, body=None, headers=None, token=None):
    h = dict(headers or {})
    if body is not None:
        h.setdefault("Content-Type", "application/json")
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        r = OPENER.open(req, timeout=60)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def j(method, path, body=None, token=None):
    s, h, b = raw(method, path, body, token=token)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def login(user, pw):
    s, r = j("POST", "/auth/login", {"username": user, "password": pw})
    return (r["access_token"], r) if s == 200 else (None, (s, r))


def cookie_of(headers):
    for c in headers.get_all("Set-Cookie") or []:
        if c.startswith("kikan_sso_state="):
            return c
    return ""


def authorize(location, spec):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    code = secrets.token_urlsafe(16)
    CODES[code] = {"nonce": q["nonce"][0], "challenge": q["code_challenge"][0], "redirect_uri": q["redirect_uri"][0], "spec": spec}
    return code, q["state"][0], q


def sso_login(spec, extra_headers=None):
    """Parcours complet (navigateur + fournisseur) : renvoie ('ticket', valeur) ou ('erreur', code)."""
    s, h, _ = raw("GET", "/auth/sso/login")
    if s != 303:
        return "http", s
    code, state, _q = authorize(h["Location"], spec)
    ck = cookie_of(h).split(";")[0].split("=", 1)[1]
    hdrs = {"Cookie": "kikan_sso_state=" + ck, **(extra_headers or {})}
    s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers=hdrs)
    loc = h2.get("Location", "")
    if loc.startswith(PUBLIC + "/sso?ticket="):
        return "ticket", urllib.parse.unquote(loc.split("ticket=", 1)[1])
    if "sso_erreur=" in loc:
        return "erreur", loc.split("sso_erreur=", 1)[1]
    return "autre", loc


def exchange(ticket):
    return j("POST", "/auth/sso/exchange", {"ticket": ticket})


def sso_session(spec):
    kind, val = sso_login(spec)
    if kind != "ticket":
        return None, (kind, val)
    s, r = exchange(val)
    return (r["access_token"], r) if s == 200 else (None, (s, r))


# ------------------------------------------------------------------ preparation
ADM, _ = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")
s, me = j("GET", "/auth/me", token=ADM)
ADMIN_ID = me["id"]
j("PUT", f"/auth/accounts/{ADMIN_ID}", {"secours": True}, ADM)


def acct(username):
    return next((a for a in j("GET", "/auth/accounts", token=ADM)[1] if a["username"] == username), None)


def mk_local(name, role, secours=False):
    s, r = j("POST", "/auth/accounts", {"username": name, "role": role, "password": PW}, ADM)
    if s == 409:
        a = acct(name)
        j("PUT", f"/auth/accounts/{a['id']}", {"actif": True, "role": role, "password": PW}, ADM)
        r = a
    if secours:
        j("PUT", f"/auth/accounts/{r['id']}", {"secours": True}, ADM)
    return r["id"]


print("== Configuration et activation ==")
s, pub = j("GET", "/auth/sso/config")
show("page de connexion : SSO inactif tant que non active (sans jeton)", s == 200 and pub["actif"] is False)
s, st = j("GET", "/auth/sso/admin/etat", token=ADM)
show("etat : environnement configure, secret jamais renvoye", s == 200 and st["config"]["configure"] is True and st["config"]["secret_present"] is True
     and SECRET not in json.dumps(st) and TENANT not in json.dumps(st) and st["config"]["redirect_uri"] == PUBLIC + "/api/auth/sso/callback", st["config"])
show("etat : activation bloquee tant qu'aucun test de connexion", st["actif"] is False and any("test de connexion" in b for b in st["blocages"]), st["blocages"])
s, r = j("POST", "/auth/sso/admin/activer", None, ADM)
show("activation sans test refusee (409)", s == 409 and "test de connexion" in str(r), r)
show("connexion SSO refusee tant que non active (404)", raw("GET", "/auth/sso/login")[0] == 404)
for name, role in (("sec_ssorh", "rh"), ("sec_ssolect", "lecture")):
    mk_local(name, role)
RH, _ = login("sec_ssorh", PW)
LECT, _ = login("sec_ssolect", PW)
for path, method in (("/auth/sso/admin/etat", "GET"), ("/auth/sso/admin/tester-config", "POST"), ("/auth/sso/admin/test-start", "POST"),
                     ("/auth/sso/admin/activer", "POST"), ("/auth/sso/admin/desactiver", "POST")):
    ok = all(j(method, path, None, t)[0] == 403 for t in (RH, LECT)) and j(method, path)[0] == 401
    show(f"administration reservee a l'informatique : {method} {path}", ok)
s, r = j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours"}, RH)
show("reglages : RH refuse (403)", s == 403)
s, r = j("POST", "/auth/sso/admin/tester-config", None, ADM)
show("test de configuration : decouverte et cles de signature joignables", s == 200 and r["ok"] and r["cles"] == 1 and r["emetteur"] == ISS, r)

# test de connexion de l'administrateur (mode test)
s, r = j("POST", "/auth/sso/admin/test-start", None, ADM)
code, state, q = authorize(r["url"], {"oid": "00000000-0000-0000-0000-0000000000a1", "upn": "admin.test@exemple.test", "roles": ["Kikan.IT"]})
show("adresse d'autorisation : PKCE S256, etat, nonce, adresse de retour fixee par la configuration",
     q["code_challenge_method"] == ["S256"] and len(q["state"][0]) >= 40 and len(q["nonce"][0]) >= 40 and q["redirect_uri"] == [PUBLIC + "/api/auth/sso/callback"]
     and q["scope"] == ["openid profile email"] and q["response_type"] == ["code"] and q["client_id"] == [CLIENT], q)
s_, h_, _ = raw("POST", "/auth/sso/admin/test-start", {}, token=ADM)
ck = cookie_of(h_)
show("cookie d'etat : HttpOnly, SameSite=Lax, Secure, chemin restreint", all(x in ck for x in ("HttpOnly", "SameSite=lax", "Secure", "Path=/api/auth/sso")), ck)
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=" + state})
show("test de connexion reussi : retour vers Parametrage", h2.get("Location") == PUBLIC + "/parametres?sso_test=ok", h2.get("Location"))
s, st = j("GET", "/auth/sso/admin/etat", token=ADM)
show("etat : resultat du test enregistre (identite, role)", st["test"]["par"] == ADMIN and st["test"]["role"] == "informatique" and st["test"]["upn"] == "admin.test@exemple.test", st["test"])
show("etat : plus aucun blocage (compte de secours present)", st["blocages"] == [] and st["comptes_secours"] >= 1, st["blocages"])
s, r = j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "ttl": 29}, ADM)
show("reglages : duree de session < 30 min refusee (422)", s == 422)
show("reglages : duree de session > 12 h refusee (422)", j("PUT", "/auth/sso/admin/reglages", {"ttl": 721}, ADM)[0] == 422)
show("reglages : mode inconnu refuse (422)", j("PUT", "/auth/sso/admin/reglages", {"mode_local": "aucun"}, ADM)[0] == 422)
show("reglages : nom de role invalide refuse (422)", j("PUT", "/auth/sso/admin/reglages", {"role_it": "<script>"}, ADM)[0] == 422)
show("reglages : date d'expiration invalide refusee (422)", j("PUT", "/auth/sso/admin/reglages", {"secret_expire": "demain"}, ADM)[0] == 422)
s, r = j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "ttl": 60, "secret_expire": "2020-01-01"}, ADM)
show("reglages enregistres ; secret expire : avertissement", s == 200 and r["reglages"]["ttl"] == 60 and "expire" in (r["avertissement"] or ""), r.get("avertissement"))
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "ttl": 240, "secret_expire": ""}, ADM)
s, r = j("POST", "/auth/sso/admin/activer", None, ADM)
show("activation apres test reussi", s == 200 and r["actif"] is True, r)
s, pub = j("GET", "/auth/sso/config")
show("page de connexion : SSO actif, mode secours", pub == {"actif": True, "mode_local": "secours"}, pub)

print("== Connexion SSO : cas nominal ==")
IT = {"oid": "00000000-0000-0000-0000-0000000000b1", "upn": "alice.it@exemple.test", "name": "Alice IT", "roles": ["Kikan.IT"]}
tok, r = sso_session(IT)
show("membre informatique : session ouverte", tok is not None, r if tok is None else "")
a = acct("alice.it@exemple.test")
show("compte nominatif cree (origine Microsoft 365, nom, e-mail, role)", a and a["source_auth"] == "sso" and a["role"] == "informatique" and a["nom_affiche"] == "Alice IT"
     and a["email"] == "alice.it@exemple.test" and a["sso_lie"] is True and a["secours"] is False and a["derniere_connexion"], a)
show("la session donne les droits du role (liste des comptes)", j("GET", "/auth/accounts", token=tok)[0] == 200)
show("ticket a usage unique : rejouer le meme ticket est refuse", True)
kind, tk = sso_login({**IT, "oid": IT["oid"]})
s1, _r = exchange(tk)
s2, _r2 = exchange(tk)
show("ticket : second echange refuse (401)", s1 == 200 and s2 == 401, (s1, s2))
show("ticket inconnu ou forge refuse (401)", exchange("x" * 43)[0] == 401 and exchange("")[0] == 401)
show("le compte SSO ne peut pas se connecter par mot de passe", login("alice.it@exemple.test", PW)[0] is None and login("alice.it@exemple.test", "")[0] is None)
s, r = j("POST", "/auth/login", {"username": "alice.it@exemple.test", "password": "n-importe-quoi-123"})
show("... et un mauvais mot de passe reste un simple 401 (rien ne fuite)", s == 401)
RHSPEC = {"oid": "00000000-0000-0000-0000-0000000000b2", "upn": "bob.rh@exemple.test", "name": "Bob RH", "roles": ["Kikan.RH"]}
tok_rh, r = sso_session(RHSPEC)
show("membre RH : session avec le role RH", tok_rh is not None and j("GET", "/users", token=tok_rh)[0] == 200 and j("GET", "/auth/accounts", token=tok_rh)[0] == 403)
both, r = sso_session({"oid": "00000000-0000-0000-0000-0000000000b3", "upn": "carl.both@exemple.test", "roles": ["Kikan.RH", "Kikan.IT"]})
show("deux roles : informatique l'emporte", acct("carl.both@exemple.test")["role"] == "informatique")

print("== Role resynchronise a chaque connexion ==")
ALICE_TOK = tok
tok2, r = sso_session({**IT, "roles": ["Kikan.RH"]})
show("role retire cote Microsoft : devient RH a la connexion suivante", acct("alice.it@exemple.test")["role"] == "rh" and tok2 is not None)
show("... et l'ancienne session informatique est revoquee (401)", j("GET", "/auth/me", token=ALICE_TOK)[0] == 401)
show("... la nouvelle session n'a plus les droits informatique", j("GET", "/auth/accounts", token=tok2)[0] == 403)
kind, val = sso_login({**IT, "roles": []})
show("plus aucun role Kikan : connexion refusee (role)", (kind, val) == ("erreur", "role"), (kind, val))
sso_session({**IT, "roles": ["Kikan.IT"]})
s, r = j("PUT", f"/auth/accounts/{acct('alice.it@exemple.test')['id']}", {"role": "rh"}, ADM)
show("role d'un compte Microsoft 365 non modifiable dans Kikan (409)", s == 409 and "Microsoft 365" in str(r), r)
al = acct("alice.it@exemple.test")
show("pas de reinitialisation ni de mot de passe local pour un compte Microsoft 365",
     j("POST", f"/auth/accounts/{al['id']}/reset-password", None, ADM)[0] == 409 and j("PUT", f"/auth/accounts/{al['id']}", {"password": PW + "x1"}, ADM)[0] == 409)
show("pas de compte de secours pour un compte Microsoft 365 (409)", j("PUT", f"/auth/accounts/{al['id']}", {"secours": True}, ADM)[0] == 409)

print("== Refus : identite, jeton, MFA ==")
def refused(name, spec, expected, **kw):
    n_before = len(j("GET", "/auth/accounts", token=ADM)[1])
    kind, val = sso_login(spec)
    n_after = len(j("GET", "/auth/accounts", token=ADM)[1])
    show(name, (kind, val) == ("erreur", expected) and n_after == n_before, (kind, val, n_after - n_before))

N = lambda i: "00000000-0000-0000-0000-0000000001%02d" % i  # noqa: E731
refused("role inconnu (aucun role Kikan) : refuse, aucun compte cree", {"oid": N(1), "upn": "x1@exemple.test", "roles": ["Autre"]}, "role")
refused("aucune revendication de role : refuse", {"oid": N(2), "upn": "x2@exemple.test", "over": {"roles": None}}, "role")
refused("roles de forme invalide (chaine) : refuse", {"oid": N(3), "upn": "x3@exemple.test", "over": {"roles": "Kikan.IT"}}, "role")
refused("MFA absente du jeton (exigee) : refuse", {"oid": N(4), "upn": "x4@exemple.test", "amr": ["pwd"]}, "mfa")
refused("mauvais public (aud) : refuse", {"oid": N(5), "upn": "x5@exemple.test", "over": {"aud": "autre-client"}}, "jeton")
refused("mauvais emetteur (iss) : refuse", {"oid": N(6), "upn": "x6@exemple.test", "over": {"iss": "https://evil.example/" + TENANT + "/v2.0"}}, "jeton")
refused("autre tenant (tid) : refuse", {"oid": N(7), "upn": "x7@exemple.test", "over": {"tid": "99999999-9999-9999-9999-999999999999"}}, "jeton")
refused("jeton expire : refuse", {"oid": N(8), "upn": "x8@exemple.test", "over": {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200, "nbf": int(time.time()) - 7200}}, "jeton")
refused("jeton pas encore valide (nbf futur) : refuse", {"oid": N(9), "upn": "x9@exemple.test", "over": {"nbf": int(time.time()) + 3600}}, "jeton")
refused("identifiant oid absent : refuse", {"oid": N(10), "upn": "x10@exemple.test", "over": {"oid": None}}, "jeton")
refused("signature par une cle non publiee : refuse", {"oid": N(11), "upn": "x11@exemple.test", "kid": "kid2"}, "jeton")
refused("algorithme 'none' : refuse", {"oid": N(12), "upn": "x12@exemple.test", "alg": "none"}, "jeton")
refused("confusion de cle (HS256 signe avec la cle publique) : refuse", {"oid": N(13), "upn": "x13@exemple.test", "alg": "HS256"}, "jeton")
refused("jeton absurde : refuse", {"oid": N(14), "upn": "x14@exemple.test", "raw": "pas.un.jeton"}, "jeton")
refused("jeton demesure (> 16 Ko) : refuse", {"oid": N(15), "upn": "x15@exemple.test", "raw": "a" * 17000}, "jeton")
s, h, _ = raw("GET", "/auth/sso/login")
code, state, q = authorize(h["Location"], {"oid": N(16), "upn": "x16@exemple.test"})
ck = cookie_of(h).split(";")[0].split("=", 1)[1]
CODES[code]["nonce"] = "nonce-different"
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=" + ck})
show("nonce different de celui de la demande : refuse", h2.get("Location", "").endswith("sso_erreur=jeton"), h2.get("Location"))

print("== Les refus d'acces ne bloquent pas les autres utilisateurs ==")
for i in range(8):  # reseau partage : plusieurs personnes sans role Kikan se presentent depuis la meme adresse
    sso_login({"oid": N(40 + i), "upn": f"sans.role{i}@exemple.test", "roles": []})
show("apres 8 refus d'acces (role), un membre autorise se connecte toujours", sso_login({"oid": N(50), "upn": "autorise@exemple.test", "roles": ["Kikan.RH"]})[0] == "ticket")

print("== Refus : etat, cookie, rejeu ==")
s, h, _ = raw("GET", "/auth/sso/login")
code, state, q = authorize(h["Location"], IT)
ck = cookie_of(h).split(";")[0].split("=", 1)[1]
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}")
show("sans cookie d'etat (connexion forcee depuis un autre navigateur) : refuse", h2.get("Location", "").endswith("sso_erreur=session"), h2.get("Location"))
CODES[code] = CODES.get(code) or {"nonce": q["nonce"][0], "challenge": q["code_challenge"][0], "redirect_uri": q["redirect_uri"][0], "spec": IT}
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=autre-valeur"})
show("cookie different de l'etat : refuse", h2.get("Location", "").endswith("sso_erreur=session"))
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state=etat-invente", headers={"Cookie": "kikan_sso_state=etat-invente"})
show("etat inconnu : refuse", h2.get("Location", "").endswith("sso_erreur=session"))
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=" + ck})
show("etat valide : accepte une fois", h2.get("Location", "").startswith(PUBLIC + "/sso?ticket="), h2.get("Location"))
CODES[code] = {"nonce": q["nonce"][0], "challenge": q["code_challenge"][0], "redirect_uri": q["redirect_uri"][0], "spec": IT}
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=" + ck})
show("rejeu de l'etat : refuse", h2.get("Location", "").endswith("sso_erreur=session"))
show("le cookie d'etat est supprime a chaque retour", "Max-Age=0" in str(h2.get_all("Set-Cookie")) or "expires=" in str(h2.get_all("Set-Cookie")).lower(), h2.get_all("Set-Cookie"))
s, h, _ = raw("GET", "/auth/sso/login")
_c, st2, _q = authorize(h["Location"], IT)
ck = cookie_of(h).split(";")[0].split("=", 1)[1]
s2, h2, _ = raw("GET", f"/auth/sso/callback?error=access_denied&state={st2}", headers={"Cookie": "kikan_sso_state=" + ck})
show("erreur renvoyee par Microsoft : refuse (idp)", h2.get("Location", "").endswith("sso_erreur=idp"), h2.get("Location"))
s, h, _ = raw("GET", "/auth/sso/login")
code, state, q = authorize(h["Location"], IT)
ck = cookie_of(h).split(";")[0].split("=", 1)[1]
CODES.pop(code)
s2, h2, _ = raw("GET", f"/auth/sso/callback?code={code}&state={state}", headers={"Cookie": "kikan_sso_state=" + ck})
show("code d'autorisation rejoue / invalide cote Microsoft : refuse", h2.get("Location", "").endswith("sso_erreur=echange"), h2.get("Location"))
kind, val = sso_login(IT, extra_headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example", "Origin": "https://evil.example"})
show("redirections toujours vers l'adresse configuree (en-tete Host falsifie ignore)", kind == "ticket")
s2, h2, _ = raw("GET", "/auth/sso/callback?code=x&state=y", headers={"Host": "evil.example"})
show("... y compris pour un refus", h2.get("Location", "").startswith(PUBLIC + "/"), h2.get("Location"))

print("== Comptes : desactive, creation automatique, conflit ==")
al = acct("alice.it@exemple.test")
j("PUT", f"/auth/accounts/{al['id']}", {"actif": False}, ADM)
show("compte desactive dans Kikan : refuse meme si Microsoft accepte (compte)", sso_login(IT) == ("erreur", "compte"))
j("PUT", f"/auth/accounts/{al['id']}", {"actif": True}, ADM)
show("compte reactive : connexion de nouveau possible", sso_login(IT)[0] == "ticket")
kind, tk = sso_login(IT)
j("PUT", f"/auth/accounts/{al['id']}", {"actif": False}, ADM)
show("ticket d'un compte desactive entre-temps : refuse (401)", exchange(tk)[0] == 401)
j("PUT", f"/auth/accounts/{al['id']}", {"actif": True}, ADM)
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "creation_auto": False}, ADM)
refused("creation automatique desactivee : compte inconnu refuse", {"oid": N(20), "upn": "inconnu@exemple.test"}, "compte")
show("... mais un compte deja existant se connecte toujours", sso_login(IT)[0] == "ticket")
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "creation_auto": True}, ADM)
mk_local("conflit@exemple.test", "rh")
refused("identifiant deja pris par un compte local : refuse (pas de rapprochement automatique)", {"oid": N(21), "upn": "conflit@exemple.test"}, "compte")
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "exiger_mfa": False}, ADM)
show("MFA non exigee (reglage) : connexion sans MFA acceptee", sso_login({"oid": N(22), "upn": "nomfa@exemple.test", "amr": ["pwd"]})[0] == "ticket")
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "exiger_mfa": True}, ADM)
show("MFA de nouveau exigee", sso_login({"oid": N(23), "upn": "nomfa2@exemple.test", "amr": ["pwd"]}) == ("erreur", "mfa"))
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "role_it": "Autre.IT", "role_rh": "Autre.RH"}, ADM)
show("noms de roles personnalises", sso_login({"oid": N(24), "upn": "perso@exemple.test", "roles": ["Autre.RH"]})[0] == "ticket" and acct("perso@exemple.test")["role"] == "rh"
     and sso_login({"oid": N(25), "upn": "perso2@exemple.test", "roles": ["Kikan.IT"]}) == ("erreur", "role"))
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours"}, ADM)

print("== Liaison d'un compte local existant ==")
lid = mk_local("sec_ssolie", "rh")
s, r = j("POST", f"/auth/accounts/{lid}/lier-sso", {"upn": "pas-une-adresse"}, ADM)
show("liaison : nom d'utilisateur Microsoft invalide (422)", s == 422)
s, r = j("POST", f"/auth/accounts/{lid}/lier-sso", {"upn": "lie.rh@exemple.test"}, ADM)
show("liaison preparee par l'administrateur", s == 200 and r["sso_upn"] == "lie.rh@exemple.test" and r["sso_lie"] is False, r)
show("liaison : meme nom d'utilisateur sur un autre compte refuse (409)", j("POST", f"/auth/accounts/{mk_local('sec_ssolie2', 'rh')}/lier-sso", {"upn": "lie.rh@exemple.test"}, ADM)[0] == 409)
n_before = len(j("GET", "/auth/accounts", token=ADM)[1])
tok_l, r = sso_session({"oid": N(30), "upn": "lie.rh@exemple.test", "roles": ["Kikan.RH"], "name": "Lie RH"})
a = acct("sec_ssolie")
show("premiere connexion SSO : rattachee au compte existant (pas de doublon)", tok_l is not None and len(j("GET", "/auth/accounts", token=ADM)[1]) == n_before
     and a["sso_lie"] is True and a["username"] == "sec_ssolie" and a["source_auth"] == "local", a)
show("compte lie : role gere par Microsoft 365 (409)", j("PUT", f"/auth/accounts/{lid}", {"role": "lecture"}, ADM)[0] == 409)
show("compte lie, non secours : mot de passe refuse en mode secours (403)", j("POST", "/auth/login", {"username": "sec_ssolie", "password": PW})[0] == 403)
j("PUT", f"/auth/accounts/{lid}", {"secours": True}, ADM)
show("... autorise une fois marque 'secours'", login("sec_ssolie", PW)[0] is not None)
s, r = j("POST", f"/auth/accounts/{lid}/delier-sso", None, ADM)
show("liaison supprimee", s == 200 and r["sso_lie"] is False and r["sso_upn"] is None)
show("... et la session SSO precedente est revoquee", j("GET", "/auth/me", token=tok_l)[0] == 401)
show("delier un compte cree par Microsoft 365 refuse (409)", j("POST", f"/auth/accounts/{acct('alice.it@exemple.test')['id']}/delier-sso", None, ADM)[0] == 409)
show("delier un compte non lie refuse (409)", j("POST", f"/auth/accounts/{mk_local('sec_ssonolink', 'rh')}/delier-sso", None, ADM)[0] == 409)

print("== Connexion locale pendant que le SSO est actif ==")
show("mode secours : compte de secours (administrateur) connecte par mot de passe", login(ADMIN, ADMIN_PW)[0] is not None)
s, r = j("POST", "/auth/login", {"username": "sec_ssorh", "password": PW})
show("mode secours : compte local ordinaire refuse (403, message clair)", s == 403 and "Microsoft 365" in str(r), r)
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "autorise"}, ADM)
show("mode 'autorise' : compte local ordinaire de nouveau accepte", login("sec_ssorh", PW)[0] is not None)
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours"}, ADM)
s, r = j("PUT", f"/auth/accounts/{ADMIN_ID}", {"secours": False}, ADM)
show("on ne retire pas le dernier compte de secours (409)", s == 409 and "dernier compte de secours" in str(r), r)

print("== Duree de session reglable ==")
def lifetime(token):
    c = jwt.decode(token, options={"verify_signature": False})
    return c["exp"] - c["iat"]

j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "ttl": 45}, ADM)
t_local, _ = login(ADMIN, ADMIN_PW)
t_sso, _ = sso_session(IT)
show("nouvelles sessions : 45 minutes (connexion locale et SSO)", lifetime(t_local) == 2700 and lifetime(t_sso) == 2700, (lifetime(t_local), lifetime(t_sso)))
j("PUT", "/auth/sso/admin/reglages", {"mode_local": "secours", "ttl": 240}, ADM)
t_local, _ = login(ADMIN, ADMIN_PW)
show("retour a 4 heures", lifetime(t_local) == 14400, lifetime(t_local))

print("== Desactivation ==")
s, r = j("POST", "/auth/sso/admin/desactiver", None, ADM)
show("desactivation du SSO", s == 200 and r["actif"] is False)
show("connexion SSO impossible une fois desactive (404)", raw("GET", "/auth/sso/login")[0] == 404)
show("page de connexion : SSO inactif, connexion locale ouverte a tous", j("GET", "/auth/sso/config")[1] == {"actif": False, "mode_local": "autorise"})
show("connexion locale ordinaire de nouveau possible", login("sec_ssorh", PW)[0] is not None)
show("compte Microsoft 365 existant : toujours impossible par mot de passe (aucun mot de passe utilisable)", login("alice.it@exemple.test", PW)[0] is None)

print("== Verifications du module (sans passer par l'API) ==")
from app import sso  # noqa: E402

os.environ["KIKAN_SSO_AUTHORITY"] = "http://evil.example"
show("autorite HTTP hors machine locale refusee", sso.authority_ok() is False)
os.environ["KIKAN_SSO_AUTHORITY"] = "https://login.microsoftonline.com"
show("autorite Microsoft acceptee", sso.authority_ok() is True)
os.environ["KIKAN_SSO_AUTHORITY"] = AUTH
show("autorite locale HTTP acceptee seulement hors production", sso.authority_ok() is True and sso.IS_PROD is False)
sso.reset_caches()
MODE["discovery_issuer"] = "https://evil.example/x/v2.0"
try:
    sso.discovery(force=True)
    ok = False
except sso.SsoError as exc:
    ok = exc.code == "config"
MODE["discovery_issuer"] = None
show("decouverte : emetteur inattendu refuse", ok)
MODE["token_host"] = "http://127.0.0.1:9999"
try:
    sso.discovery(force=True)
    ok = False
except sso.SsoError as exc:
    ok = exc.code == "config"
MODE["token_host"] = None
show("decouverte : point de terminaison hors de l'autorite refuse (pas de detournement)", ok)
MODE["redirect"] = True
try:
    sso.discovery(force=True)
    ok = False
except sso.SsoError as exc:
    ok = exc.code in ("echange", "reseau")
MODE["redirect"] = False
show("redirection inattendue lors d'un appel sortant : jamais suivie", ok)
MODE["big"] = True
try:
    sso._fetch(f"{AUTH}/{TENANT}/v2.0/.well-known/openid-configuration")
    ok = False
except sso.SsoError as exc:
    ok = exc.code == "echange"
MODE["big"] = False
show("reponse demesuree refusee", ok)
MODE["slow"] = True
t0 = time.time()
try:
    sso._fetch(f"{AUTH}/{TENANT}/v2.0/.well-known/openid-configuration", timeout=2)
    ok = False
except sso.SsoError as exc:
    ok = exc.code == "reseau"
MODE["slow"] = False
show("delai d'attente respecte (pas de blocage)", ok and time.time() - t0 < 6, f"{time.time() - t0:.1f} s")
sso.reset_caches()
try:
    sso.validate_id_token(make_token({"oid": "x", "upn": "u@e.test"}, "n", kid="inconnu", key=KEYS["kid1"]), "n")
    ok = False
except sso.SsoError as exc:
    ok = exc.code == "jeton"
show("identifiant de cle inconnu : refuse", ok)
claims = sso.validate_id_token(make_token({"oid": "x", "upn": "u@e.test"}, "n"), "n")
show("jeton valide : revendications renvoyees", claims["oid"] == "x" and claims["tid"] == TENANT)

print("== Journal d'audit ==")
os.environ["KIKAN_SSO_AUTHORITY"] = AUTH
s, log = j("GET", "/audit?limit=500", token=ADM)
acts = {x["action"] for x in log}
need = {"sso_login_ok", "sso_refuse", "sso_compte_cree", "sso_role_modifie", "sso_active", "sso_desactive", "sso_test_ok", "sso_reglages",
        "compte_lie_sso", "compte_delie_sso", "login_local_refuse"}
show("evenements SSO journalises", need <= acts, sorted(need - acts))
blob = json.dumps(log)
show("journal : ni jeton, ni secret, ni code d'autorisation", "eyJ" not in blob and SECRET not in blob and "code_verifier" not in blob)
refus = [x for x in log if x["action"] == "sso_refuse"]
show("journal : motifs de refus renseignes", any("role" in (x.get("detail") or "") for x in refus) and any("mfa" in (x.get("detail") or "") for x in refus))

srv.shutdown()
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
