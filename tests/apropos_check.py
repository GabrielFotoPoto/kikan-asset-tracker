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

"""Page A propos : version, licence, composants ; lecture ouverte a tous les comptes, rien de secret.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/apropos_check.py

Cree des comptes sec_ap* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. ASCII uniquement.
"""
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(user, pw):
    s, b = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


ADM = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None, token=None):
    s, b = call(method, path, body, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b



def account(name, role):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role})
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW})
    return s


print("== Acces ==")
s, b = call("GET", "/apropos", None, None)
show("sans session : refuse", s in (401, 403), s)
tokens = {}
for role in ("informatique", "rh", "lecture"):
    show("compte %s cree" % role, account("sec_ap_" + role, role) in (200, 201))
    tokens[role] = login("sec_ap_" + role, PW)
    s, r = j("GET", "/apropos", None, tokens[role])
    show("%s : lecture autorisee" % role, s == 200 and isinstance(r, dict), s)

print("== Contenu ==")
s, d = j("GET", "/apropos")
show("application, version et licence", d["application"] and d["version"] and d["licence"]["spdx"] == "GPL-3.0-or-later", d.get("licence"))
show("version de developpement signalee (pas de numero ni de date)",
     (d["developpement"] is True and d["version"] == "dev" and d["date_publication"] is None and d["liens"]["version"] is None)
     or (d["developpement"] is False and d["liens"]["version"].endswith("/v" + d["version"])), d)
show("version coherente avec /health", d["version"] == j("GET", "/health")[1]["version"])
show("auteur, copyright et mention IA", d["auteur"] == "Gabriel Chollet" and "2026" in d["copyright"] and "IA" in d["ia"])
show("liens HTTPS vers le depot", all(v is None or v.startswith("https://github.com/") for v in d["liens"].values()), d["liens"])
noms = {c["nom"]: c for c in d["composants"]}
show("composants principaux presents", all(n in noms for n in ("FastAPI", "PostgreSQL", "React", "ReportLab", "nginx")))
show("version lue sur un paquet installe", bool(noms["FastAPI"]["version"]), noms["FastAPI"])
show("composant externe sans version : null", noms["PostgreSQL"]["version"] is None)
show("chaque composant a une licence", all(c["licence"] and c["role"] for c in d["composants"]))
txt = json.dumps(d).lower()
show("aucun secret ni chemin interne", not any(w in txt for w in ("password", "secret", "token", "/app/", "database_url", "postgresql+")), "")

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
