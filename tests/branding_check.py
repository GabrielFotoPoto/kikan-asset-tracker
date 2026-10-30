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

"""Icone de l'application (Parametrage, Apparence) : lecture publique, depot reserve a l'informatique, image verifiee.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/branding_check.py

Cree des comptes sec_br* (nettoyage : tests/cleanup_test_data.sql) et retire l'icone a la fin. Code de sortie 1 si un test
echoue. ASCII uniquement.
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


import base64
import io

from PIL import Image


def png(w=64, h=64, color=(200, 30, 30, 255), info=False):
    im = Image.new("RGBA", (w, h), color)
    out = io.BytesIO()
    if info:
        from PIL.PngImagePlugin import PngInfo
        meta = PngInfo()
        meta.add_text("Comment", "secret-metadata-zzbr")
        im.save(out, "PNG", pnginfo=meta)
    else:
        im.save(out, "PNG")
    return out.getvalue()


def jpeg(w=64, h=64):
    out = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(out, "JPEG")
    return out.getvalue()


def data_url(raw, mime="image/png"):
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode())


def account(name, role):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role})
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW})
    return s


j("DELETE", "/parametres/icone")

print("== Lecture publique ==")
s, b = call("GET", "/branding", None, None)
show("sans session, sans icone : /branding repond 200 avec icone nulle", s == 200 and json.loads(b) == {"icone": None}, b)
s, b = call("GET", "/branding/icone", None, None)
show("sans icone : /branding/icone repond 404", s == 404, s)

print("== Depot ==")
s, r = j("PUT", "/parametres/icone", {"image": data_url(png(64, 64, info=True))})
show("PNG carre accepte", s == 200 and r["largeur"] == 64 and r["hauteur"] == 64, r)
s, b = call("GET", "/branding", None, None)
h1 = json.loads(b)["icone"]
show("/branding donne une empreinte (sans session)", s == 200 and isinstance(h1, str) and len(h1) == 16, b)
req = urllib.request.Request(B + "/branding/icone")
r = urllib.request.urlopen(req, timeout=60)
body = r.read()
show("l'icone est servie sans session, en PNG", r.status == 200 and r.headers["Content-Type"] == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n", r.headers["Content-Type"])
show("nosniff sur l'image", r.headers.get("X-Content-Type-Options") == "nosniff")
show("metadonnees de l'image retirees", b"secret-metadata-zzbr" not in body and b"Comment" not in body)
show("l'empreinte correspond a l'image servie", __import__("hashlib").sha256(body).hexdigest()[:16] == h1)
s, r = j("PUT", "/parametres/icone", {"image": data_url(jpeg(), "image/jpeg")})
show("JPEG accepte et converti en PNG", s == 200, r)
body2 = urllib.request.urlopen(urllib.request.Request(B + "/branding/icone"), timeout=60).read()
show("JPEG : l'image servie est un PNG", body2[:8] == b"\x89PNG\r\n\x1a\n")
s, b = call("GET", "/branding", None, None)
show("l'empreinte change quand l'icone change", json.loads(b)["icone"] != h1)

print("== Refus ==")
svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
s, r = j("PUT", "/parametres/icone", {"image": data_url(svg, "image/svg+xml")})
show("SVG refuse", s == 400, r)
s, r = j("PUT", "/parametres/icone", {"image": data_url(svg, "image/png")})
show("SVG deguise en PNG refuse (verification du contenu)", s == 400, r)
s, r = j("PUT", "/parametres/icone", {"image": "pas-du-base64!!"})
show("texte qui n'est pas une image refuse", s == 400, r)
s, r = j("PUT", "/parametres/icone", {"image": data_url(png(8, 8))})
show("image trop petite refusee", s == 400, r)
s, r = j("PUT", "/parametres/icone", {"image": data_url(png(2000, 300))})
show("image trop large refusee", s == 400, r)
noisy = io.BytesIO()
Image.frombytes("RGB", (400, 400), os.urandom(400 * 400 * 3)).save(noisy, "PNG")
s, r = j("PUT", "/parametres/icone", {"image": data_url(noisy.getvalue())})
show("image trop lourde refusee", s in (400, 422), r)
s, b = call("GET", "/branding", None, None)
show("les refus ne modifient pas l'icone en place", json.loads(b)["icone"] is not None)

print("== Droits ==")
for role in ("rh", "lecture"):
    account("sec_br_" + role, role)
    t = login("sec_br_" + role, PW)
    s, r = j("PUT", "/parametres/icone", {"image": data_url(png())}, t)
    show("%s : depot refuse" % role, s == 403, r)
    s, r = call("DELETE", "/parametres/icone", None, t)
    show("%s : suppression refusee" % role, s == 403, r)
s, r = call("PUT", "/parametres/icone", {"image": data_url(png())}, None)
show("sans session : depot refuse", s in (401, 403), s)
s, r = call("DELETE", "/parametres/icone", None, None)
show("sans session : suppression refusee", s in (401, 403), s)

print("== Journal ==")
s, logs = j("GET", "/audit?limit=100")
mine = [x for x in logs if (x.get("target") or "") == "parametres/icone"]
show("depots journalises", len(mine) >= 2 and any("sha256=" in (x.get("detail") or "") for x in mine), mine[:1])
show("le journal ne contient pas l'image", not any("base64" in json.dumps(x) for x in mine))

print("== Suppression ==")
s, r = call("DELETE", "/parametres/icone", None, ADM)
show("suppression", s == 204, r)
s, b = call("GET", "/branding", None, None)
show("apres suppression : icone nulle", json.loads(b) == {"icone": None})
s, b = call("GET", "/branding/icone", None, None)
show("apres suppression : 404", s == 404)

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
