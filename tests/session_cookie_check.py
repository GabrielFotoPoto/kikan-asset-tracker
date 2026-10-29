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

"""Tests de la session par cookie HttpOnly : attributs du cookie, protection CSRF, jeton Bearer, deconnexion.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/session_cookie_check.py

Ne cree aucune donnee. Fichier ASCII uniquement. Code de sortie 1 si un test echoue.
"""
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:150] if detail else ""))


def call(method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def session_cookie(headers):
    for line in headers.get_all("Set-Cookie") or []:
        if line.startswith("kikan_session="):
            return line
    return None


status, raw, hdrs = call("POST", "/auth/login", {"username": ADMIN, "password": ADMIN_PW})
show("connexion", status == 200, status)
line = session_cookie(hdrs)
show("le cookie de session est pose", line is not None)
flags = (line or "").lower()
show("cookie HttpOnly", "httponly" in flags, line)
show("cookie SameSite=Strict", "samesite=strict" in flags, line)
show("cookie limite a /api", "path=/api" in flags, line)
cookie = (line or "").split(";")[0]
bearer = json.loads(raw).get("access_token", "") if status == 200 else ""

# Lecture : le cookie suffit.
status, _, _ = call("GET", "/auth/me", headers={"Cookie": cookie})
show("GET /auth/me avec le seul cookie", status == 200, status)

# Ecriture par cookie : l'en-tete anti-CSRF est obligatoire.
body = {"old_password": "faux-mot-de-passe-1", "new_password": "un-autre-mot-de-passe-2"}
status, _, _ = call("POST", "/auth/change-password", body, {"Cookie": cookie})
show("ecriture par cookie sans en-tete anti-CSRF : 403", status == 403, status)
status, _, _ = call("POST", "/auth/change-password", body, {"Cookie": cookie, "X-Kikan-Request": "1"})
show("ecriture par cookie avec l'en-tete : traitee (400, ancien mot de passe faux)", status == 400, status)
status, _, _ = call("POST", "/auth/change-password", body, {"Cookie": cookie, "X-Kikan-Request": "0"})
show("en-tete anti-CSRF a une autre valeur : 403", status == 403, status)

# Jeton Bearer (scripts, tests) : toujours accepte, sans l'en-tete.
status, _, _ = call("GET", "/auth/me", headers={"Authorization": "Bearer " + bearer})
show("GET avec Bearer", status == 200, status)
status, _, _ = call("POST", "/auth/change-password", body, {"Authorization": "Bearer " + bearer})
show("ecriture avec Bearer sans en-tete anti-CSRF : traitee (400)", status == 400, status)

# Cookie invalide ou absent.
status, _, _ = call("GET", "/auth/me", headers={"Cookie": "kikan_session=pas-un-jeton"})
show("cookie invalide : 401", status == 401, status)
status, _, _ = call("GET", "/auth/me")
show("sans cookie ni jeton : 401", status == 401, status)

# Deconnexion : le cookie est efface.
status, _, hdrs = call("POST", "/auth/logout", headers={"X-Kikan-Request": "1"})
show("deconnexion : 204", status == 204, status)
line = (session_cookie(hdrs) or "").lower()
show("deconnexion : cookie efface", "max-age=0" in line or "1970" in line, line)

sys.exit(1 if fails else 0)
