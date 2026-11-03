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

print("== Verification des mises a jour ==")
s, _ = call("GET", "/apropos/mise-a-jour", None, None)
show("mise-a-jour sans session : refuse", s in (401, 403), s)
for role in ("rh", "lecture"):
    s, _ = j("GET", "/apropos/mise-a-jour", None, tokens[role])
    show("mise-a-jour %s : refuse (403)" % role, s == 403, s)
s, m = j("GET", "/apropos/mise-a-jour", None, tokens["informatique"])
show("mise-a-jour informatique : autorise (200)", s == 200 and isinstance(m, dict), s)
show("mise-a-jour : champs attendus presents",
     all(k in m for k in ("verification_active", "version_actuelle", "developpement", "derniere_version", "disponible", "url_release", "erreur")),
     m)
show("mise-a-jour : url_release HTTPS GitHub", isinstance(m.get("url_release"), str) and m["url_release"].startswith("https://github.com/"), m.get("url_release"))

import http.server
import threading
import time
from unittest.mock import patch
from app.routers import apropos as ap_mod

show("semver : comparaison standard", ap_mod._parse_semver("0.5.0") > ap_mod._parse_semver("0.4.2"))
show("semver : finale > preversion", ap_mod._parse_semver("0.5.0") > ap_mod._parse_semver("0.5.0-rc.1"))
show("semver : prefixe v ignore", ap_mod._parse_semver("v1.2.3") == ap_mod._parse_semver("1.2.3"))
show("semver : version invalide -> None", ap_mod._parse_semver("dev") is None and ap_mod._parse_semver("") is None)

MOCK_STATE = {"status": 200, "body": {"tag_name": "v0.6.0", "published_at": "2026-11-03T10:00:00Z", "html_url": "https://github.com/GabrielFotoPoto/kikan-asset-tracker/releases/tag/v0.6.0"}, "calls": 0}


class MockGh(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        MOCK_STATE["calls"] += 1
        if MOCK_STATE["status"] in (301, 302):
            self.send_response(MOCK_STATE["status"])
            self.send_header("Location", "http://evil.example/release")
            self.end_headers()
            return
        self.send_response(MOCK_STATE["status"])
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        raw = MOCK_STATE["body"] if isinstance(MOCK_STATE["body"], bytes) else json.dumps(MOCK_STATE["body"]).encode()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), MockGh)
mock_url = "http://127.0.0.1:%d/releases/latest" % srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    with patch.dict(os.environ, {"KIKAN_VERSION": "0.5.0", "KIKAN_UPDATE_CHECK": "true", "KIKAN_UPDATE_CHECK_URL": mock_url, "KIKAN_ENV": "development"}):
        ap_mod.reset_update_cache()
        MOCK_STATE["calls"] = 0
        r1 = ap_mod.verifier_mise_a_jour(forcer=False)
        show("faux GitHub : nouvelle version detectee (0.5.0 -> 0.6.0)", r1["disponible"] is True and r1["derniere_version"] == "0.6.0" and r1["date_publication"] == "2026-11-03", r1)
        r2 = ap_mod.verifier_mise_a_jour(forcer=False)
        show("cache : pas de second appel reseau", MOCK_STATE["calls"] == 1 and r2["derniere_version"] == "0.6.0", MOCK_STATE["calls"])
        r3 = ap_mod.verifier_mise_a_jour(forcer=True)
        show("anti-rebond : forcer=true dans les 60 s repond depuis le cache", MOCK_STATE["calls"] == 1, MOCK_STATE["calls"])
        ap_mod._maj_cache["ts"] -= 120
        r4 = ap_mod.verifier_mise_a_jour(forcer=True)
        show("forcer=true apres 60 s : nouvel appel reseau", MOCK_STATE["calls"] == 2, MOCK_STATE["calls"])

    with patch.dict(os.environ, {"KIKAN_VERSION": "0.6.0", "KIKAN_UPDATE_CHECK": "true", "KIKAN_UPDATE_CHECK_URL": mock_url, "KIKAN_ENV": "development"}):
        ap_mod.reset_update_cache()
        r_ajour = ap_mod.verifier_mise_a_jour(forcer=False)
        show("meme version : disponible=False", r_ajour["disponible"] is False and r_ajour["derniere_version"] == "0.6.0", r_ajour)

    with patch.dict(os.environ, {"KIKAN_VERSION": "0.5.0", "KIKAN_UPDATE_CHECK": "false", "KIKAN_UPDATE_CHECK_URL": mock_url}):
        ap_mod.reset_update_cache()
        calls_before = MOCK_STATE["calls"]
        r_off = ap_mod.verifier_mise_a_jour(forcer=False)
        show("desactivation KIKAN_UPDATE_CHECK=false : aucun appel", r_off["verification_active"] is False and r_off["disponible"] is False and MOCK_STATE["calls"] == calls_before, r_off)

    with patch.dict(os.environ, {"KIKAN_VERSION": "0.5.0", "KIKAN_UPDATE_CHECK": "true", "KIKAN_UPDATE_CHECK_URL": "http://example.com/releases", "KIKAN_ENV": "development"}):
        ap_mod.reset_update_cache()
        r_http = ap_mod.verifier_mise_a_jour(forcer=False)
        show("URL HTTP distante refusee", bool(r_http["erreur"]) and r_http["disponible"] is False, r_http)

    MOCK_STATE["status"] = 302
    with patch.dict(os.environ, {"KIKAN_VERSION": "0.5.0", "KIKAN_UPDATE_CHECK": "true", "KIKAN_UPDATE_CHECK_URL": mock_url, "KIKAN_ENV": "development"}):
        ap_mod.reset_update_cache()
        r_redir = ap_mod.verifier_mise_a_jour(forcer=False)
        show("redirection 302 refusee et erreur mise en cache court", bool(r_redir["erreur"]) and r_redir["disponible"] is False, r_redir)
        ap_mod._maj_cache["ts"] -= (ap_mod.ERROR_TTL_SEC + 5)
        MOCK_STATE["status"] = 200
        r_recov = ap_mod.verifier_mise_a_jour(forcer=False)
        show("expiration du cache court d'erreur (5 min) : reprise automatique", r_recov["erreur"] is None and r_recov["disponible"] is True, r_recov)
finally:
    srv.shutdown()

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
