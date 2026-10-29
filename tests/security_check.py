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

"""Tests de securite offensifs de Kikan (a lancer sur une instance de DEVELOPPEMENT).

Usage (depuis la racine du projet, pile demarree) :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/security_check.py

Le script cree des donnees marquees ZZTEST (a nettoyer ensuite, voir SECURITY.md) et
desactive ses comptes de test a la fin. Code de sortie 1 si au moins un test echoue.
Le test de force brute alimente le compteur de tentatives par adresse IP (limite de 30 par 15 minutes) :
au-dela de trois executions rapprochees, redemarrer l'API (docker compose restart api).
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import jwt

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PROD = os.environ.get("KIKAN_ENV", "development").lower() == "production"
TEST_PW = "Sec-Test-Passw0rd-2026"
fails = 0


def signature_b64():
    """Signature manuscrite de test (PNG 1000x400, trace fonce sur fond transparent)."""
    import base64
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIG = signature_b64()
SIGN = {"consent": True, "signature_image": SIG, "strokes": 4, "duration_ms": 1800}


def call(method, path, body=None, token=None, headers=None, raw=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def login(u, p):
    s, b, _ = call("POST", "/auth/login", {"username": u, "password": p})
    return json.loads(b)["access_token"] if s == 200 else None


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))


adm = login(ADMIN_USER, ADMIN_PW)
if not adm:
    sys.exit("Connexion admin impossible : definir TEST_ADMIN_USER / TEST_ADMIN_PASSWORD")


def ensure_account(name, role):
    s, b, _ = call("POST", "/auth/accounts", {"username": name, "password": TEST_PW, "role": role}, adm)
    if s == 409:
        accounts = json.loads(call("GET", "/auth/accounts", token=adm)[1])
        acc = next(a for a in accounts if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": TEST_PW}, adm)
        return acc["id"]
    return json.loads(b)["id"]


_s, _b, _ = call("GET", "/audit?limit=1", token=adm)
AUDIT_ID0 = (json.loads(_b)[0]["id"] if _s == 200 and json.loads(_b) else 0)

id_rh = ensure_account("sec_rh", "rh")
id_lect = ensure_account("sec_lecture", "lecture")
rh = login("sec_rh", TEST_PW)
lect = login("sec_lecture", TEST_PW)

print("== 1. Acces sans jeton ==")
for p in ["/users", "/assets", "/entites", "/applications", "/assignments", "/stats", "/audit",
          "/reports/holdings", "/rgpd/retention", "/rgpd/etat", "/rgpd/documents", "/import/lots", "/auth/accounts", "/auth/me", "/lifecycle/holdings/1"]:
    s, _, _ = call("GET", p)
    show(f"GET {p} sans jeton -> 401", s == 401, f"HTTP {s}")

print("== 2. Jetons falsifies ==")
now = datetime.datetime.now(datetime.timezone.utc)


def forge(secret, alg="HS256", sub=ADMIN_USER, exp_delta=3600):
    return jwt.encode({"sub": sub, "role": "informatique", "iat": now,
                       "exp": now + datetime.timedelta(seconds=exp_delta)}, secret, algorithm=alg)


s, _, _ = call("GET", "/auth/me", token=forge("mauvaise-cle"))
show("mauvaise cle refusee", s == 401, f"HTTP {s}")
s, _, _ = call("GET", "/auth/me", token=forge("dev-secret-change-me"))
show("cle par defaut 'dev-secret-change-me' inutilisable", s == 401, f"HTTP {s}")
s, _, _ = call("GET", "/auth/me", token=forge("x" * 40, exp_delta=-60))
show("jeton expire refuse", s == 401, f"HTTP {s}")
none_tok = jwt.encode({"sub": ADMIN_USER, "exp": now + datetime.timedelta(hours=1)}, None, algorithm="none")
s, _, _ = call("GET", "/auth/me", token=none_tok)
show("jeton alg=none refuse", s == 401, f"HTTP {s}")
s, _, _ = call("GET", "/auth/me", token="pas.un.jwt")
show("jeton mal forme refuse", s == 401, f"HTTP {s}")

print("== 3. Contournement des roles ==")
for name, tok in (("lecture", lect), ("rh", rh)):
    for method, path, body in [
        ("POST", "/entites", {"code": "T", "nom": "T"}),
        ("POST", "/assets", {"marque": "T", "statut": "stock"}),
        ("POST", "/applications", {"nom": "T"}),
        ("POST", "/assignments", {"user_id": 1, "asset_ids": [1]}),
        ("POST", "/rgpd/purge", {}),
        ("PUT", "/rgpd/retention", {"mois": 0}),
        ("POST", "/rgpd/quarantaine/supprimer", {}),
        ("POST", "/rgpd/quarantaine/restaurer", {"ids": [1]}),
        ("POST", "/rgpd/ged/confirmer", {"ids": [1]}),
        ("GET", "/rgpd/documents", None),
        ("GET", "/import/lots", None),
        ("POST", "/import/lots/1/annuler", {}),
        ("POST", "/auth/accounts", {"username": "x", "password": TEST_PW, "role": "informatique"}),
        ("PUT", f"/auth/accounts/{id_rh}", {"role": "informatique"}),
    ]:
        s, _, _ = call(method, path, body, tok)
        show(f"{name}: {method} {path} -> 403", s == 403, f"HTTP {s}")
    s, _, _ = call("GET", "/audit", token=tok)
    show(f"{name}: GET /audit -> 403", s == 403, f"HTTP {s}")
    s, _, _ = call("GET", "/auth/accounts", token=tok)
    show(f"{name}: GET /auth/accounts -> 403", s == 403, f"HTTP {s}")
s, _, _ = call("POST", "/users", {"nom": "T", "prenom": "T"}, lect)
show("lecture: POST /users -> 403", s == 403, f"HTTP {s}")
s, _, _ = call("POST", "/lifecycle/restituer", {"user_id": 1, "consent": True}, lect)
show("lecture: POST /lifecycle/restituer -> 403", s == 403, f"HTTP {s}")

print("== 4. Comptes et mots de passe ==")
s, _, _ = call("POST", "/auth/accounts", {"username": "sec_court", "password": "court", "role": "lecture"}, adm)
show("mot de passe trop court refuse", s == 400, f"HTTP {s}")
s, _, _ = call("POST", "/auth/accounts", {"username": "sec_long", "password": "a" * 80, "role": "lecture"}, adm)
show("mot de passe > 72 octets refuse", s == 400, f"HTTP {s}")
accounts = json.loads(call("GET", "/auth/accounts", token=adm)[1])
actifs_it = [a for a in accounts if a["role"] == "informatique" and a["actif"]]
if len(actifs_it) == 1:
    s, _, _ = call("PUT", f"/auth/accounts/{actifs_it[0]['id']}", {"actif": False}, adm)
    show("le dernier compte informatique ne peut pas etre desactive", s == 409, f"HTTP {s}")
    s, _, _ = call("PUT", f"/auth/accounts/{actifs_it[0]['id']}", {"role": "lecture"}, adm)
    show("le dernier compte informatique ne peut pas etre retrograde", s == 409, f"HTTP {s}")
else:
    print("SKIP dernier administrateur (plusieurs comptes informatique actifs)")
s, _, _ = call("POST", "/auth/change-password", {"old_password": "faux-faux-faux", "new_password": TEST_PW + "x"}, rh)
show("changement de mot de passe avec un mauvais ancien refuse", s == 400, f"HTTP {s}")
s, _, _ = call("POST", "/auth/change-password", {"old_password": TEST_PW, "new_password": "court"}, rh)
show("nouveau mot de passe faible refuse", s == 400, f"HTTP {s}")
s, b, _ = call("GET", "/auth/accounts", token=adm)
show("aucun hash de mot de passe dans /auth/accounts", b"hashed_password" not in b and b"$2b$" not in b)

print("== 5. Injections ==")
s, b, _ = call("GET", "/users?q=" + urllib.parse.quote("' OR '1'='1"), token=adm)
show("injection SQL dans q sans effet", s == 200 and json.loads(b) == [], f"HTTP {s}")
s, _, _ = call("GET", "/assets?statut=" + urllib.parse.quote("stock' OR '1'='1"), token=adm)
show("injection SQL dans statut rejetee", s == 422, f"HTTP {s}")

print("== 6. Injection de formules dans les exports CSV ==")
s, b, _ = call("POST", "/users", {"nom": "=HYPERLINK(\"http://evil\",\"x\")", "prenom": "+cmd", "service": "@SUM(1)",
                                   "statut": "actif", "matricule": "ZZTEST"}, adm)
uid = json.loads(b)["id"] if s == 201 else None
s, b, _ = call("POST", "/assets", {"marque": "-2+3", "modele": "=1+1", "type": "PC", "numero_serie": "ZZTEST-SN",
                                    "statut": "stock"}, adm)
aid = json.loads(b)["id"] if s == 201 else None
show("preparation CSV : creation du salarie et de l'actif de test", bool(uid and aid), f"user={uid} asset={aid}")
if uid and aid:
    call("POST", "/assignments", {"user_id": uid, "asset_ids": [aid]}, adm)
    s, b, _ = call("GET", "/reports/holdings?format=csv", token=adm)
    lignes = [ln for ln in b.decode("utf-8-sig").splitlines() if "ZZTEST" in ln]
    cells = lignes[0].replace('"', "").split(";") if lignes else []
    dang = [c for c in cells if c[:1] in ("=", "+", "-", "@")]
    show("export CSV neutralise les formules", bool(lignes) and not dang, (lignes[0][:100] if lignes else "pas de ligne"))

print("== 7. Texte hostile dans les PDF ==")
s, b, _ = call("POST", "/users", {"nom": "<b>gras", "prenom": "<font size=-5>x", "statut": "actif",
                                   "matricule": "ZZPDF"}, adm)
uid2 = json.loads(b)["id"] if s == 201 else None
s, b, _ = call("POST", "/assets", {"marque": "<img src='/etc/passwd' width='5' height='5'/>",
                                    "modele": "<a href='http://evil'>x</a>", "numero_serie": "ZZPDF-SN",
                                    "statut": "stock"}, adm)
aid2 = json.loads(b)["id"] if s == 201 else None
show("preparation PDF : creation du salarie et de l'actif de test", bool(uid2 and aid2), f"user={uid2} asset={aid2}")
if uid2 and aid2:
    s, b, _ = call("POST", "/assignments", {"user_id": uid2, "asset_ids": [aid2]}, adm)
    asg2 = json.loads(b)["id"]
    s, b, _ = call("POST", f"/assignments/{asg2}/sign", SIGN, adm)
    show("signature avec balises HTML sans erreur 500", s == 201, f"HTTP {s}")

print("== 8. Fichiers d'import hostiles ==")


def upload(kind, content):
    boundary = "----kikanTEST"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.csv\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return call("POST", f"/import/{kind}", token=adm, raw=body,
                headers={"Content-Type": "multipart/form-data; boundary=" + boundary})


s, _, _ = upload("utilisateurs", b"\xff\xfe\x00binaire\x00\x00")
show("fichier binaire gere sans 500", s in (200, 400), f"HTTP {s}")
many = b"code;nom;code_parent;actif\n" + b"".join(b"ZZX%d;Nom;;oui\n" % i for i in range(25000))
s, _, _ = upload("entites", many)
show("trop de lignes refuse (413)", s == 413, f"HTTP {s}")
huge = b"code;nom;code_parent;actif\n" + b"A" * (6 * 1024 * 1024)
s, _, _ = upload("entites", huge)
show("fichier trop volumineux refuse (413)", s == 413, f"HTTP {s}")
s, _, _ = upload("../../etc/passwd", b"x")
show("type d'import invalide rejete", s in (400, 404), f"HTTP {s}")

print("== 9. Force brute ==")
import uuid  # noqa: E402
TARGET = "cible-bruteforce-" + uuid.uuid4().hex[:6]  # nom unique : le verrouillage dure 15 min
codes = [call("POST", "/auth/login", {"username": TARGET, "password": "mauvais%d" % i})[0]
         for i in range(7)]
show("verrouillage (429) apres des echecs repetes", 429 in codes, f"codes: {codes}")
s, _, h = call("POST", "/auth/login", {"username": TARGET, "password": "x"})
show("en-tete Retry-After present", s == 429 and any(k.lower() == "retry-after" for k in h), f"HTTP {s}")
show("un autre compte reste utilisable (pas de blocage global)", login(ADMIN_USER, ADMIN_PW) is not None)

print("== 10. CORS ==")
s, _, h = call("OPTIONS", "/users", headers={"Origin": "http://evil.example",
                                              "Access-Control-Request-Method": "GET",
                                              "Access-Control-Request-Headers": "authorization"})
origin = h.get("access-control-allow-origin") or h.get("Access-Control-Allow-Origin")
show("origine hostile refusee par CORS", origin not in ("*", "http://evil.example"), f"allow-origin={origin}")

print("== 11. En-tetes et divulgation ==")
s, _, h = call("GET", "/health")
show("Cache-Control: no-store", "no-store" in (h.get("Cache-Control") or h.get("cache-control") or ""))
show("X-Content-Type-Options: nosniff",
     (h.get("X-Content-Type-Options") or h.get("x-content-type-options")) == "nosniff")
show("en-tete Server non divulgue", "uvicorn" not in (h.get("server") or h.get("Server") or "").lower())
s, _, _ = call("GET", "/docs")
if PROD:
    show("/docs desactive en production", s == 404, f"HTTP {s}")
else:
    print(f"INFO /docs expose (HTTP {s}) : normal en developpement, masque avec KIKAN_ENV=production")

print("== 12. Journal d'audit ==")
adm = login(ADMIN_USER, ADMIN_PW)
s, b, _ = call("GET", "/audit?limit=500", token=adm)
logs = [x for x in (json.loads(b) if s == 200 else []) if x["id"] > AUDIT_ID0]
show("le journal est consultable et recoit de nouvelles entrees", s == 200 and len(logs) > 0,
     f"{len(logs)} nouvelle(s) entree(s)")
show("connexions echouees journalisees", any(x["action"] == "login_echec" for x in logs))
show("verrouillage journalise", any(x["action"] == "login_bloque" for x in logs))
show("ecritures journalisees avec l'auteur",
     any(x["action"].startswith("POST /") and x["actor"] == ADMIN_USER for x in logs))
show("refus d'acces journalises", any(x["status"] == 403 for x in logs))
blob = json.dumps(logs)
show("aucun mot de passe dans le journal", TEST_PW not in blob and ADMIN_PW not in blob)

# Nettoyage : comptes de test desactives
for acc_id in (id_rh, id_lect):
    call("PUT", f"/auth/accounts/{acc_id}", {"actif": False}, adm)

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
