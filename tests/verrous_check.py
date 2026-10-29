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

"""Verrous contre la double affectation, la double signature et la double restitution (appels simultanes).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/verrous_check.py

Cree des donnees marquees ZZVL (a nettoyer ensuite). Code de sortie 1 si un test echoue.
"""
import base64
import io
import json
import os
import sys
import threading
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
fails = 0


def signature_b64():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIGN = {"consent": True, "signature_image": signature_b64(), "strokes": 4, "duration_ms": 1800}


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=90)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


s, b = call("POST", "/auth/login", {"username": os.environ.get("TEST_ADMIN_USER", "admin"),
                                     "password": os.environ.get("TEST_ADMIN_PASSWORD", "")})
if s != 200:
    sys.exit("Connexion admin impossible")
T = json.loads(b)["access_token"]


def j(method, path, body=None):
    s, b = call(method, path, body, T)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def simultane(method, path, body, n=2):
    """Lance n appels identiques en meme temps (barriere) ; retourne la liste des codes HTTP."""
    barrier, codes = threading.Barrier(n), []

    def go():
        barrier.wait()
        s, _ = call(method, path, body, T)
        codes.append(s)

    threads = [threading.Thread(target=go) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(codes)


print("== Double affectation du meme materiel ==")
s, u1 = j("POST", "/users", {"nom": "ZZVL", "prenom": "Un", "matricule": "ZZVL1", "statut": "actif"})
s, u2 = j("POST", "/users", {"nom": "ZZVL", "prenom": "Deux", "matricule": "ZZVL2", "statut": "actif"})
s, a1 = j("POST", "/assets", {"type": "PC", "marque": "ZZVL-HP", "numero_serie": "ZZVL-SN1", "statut": "stock"})
barrier, res = threading.Barrier(2), []


def affecter(uid):
    barrier.wait()
    res.append(call("POST", "/assignments", {"user_id": uid, "asset_ids": [a1["id"]]}, T)[0])


ths = [threading.Thread(target=affecter, args=(u["id"],)) for u in (u1, u2)]
for t in ths:
    t.start()
for t in ths:
    t.join()
show("un seul des deux appels simultanes cree la remise", sorted(res) == [201, 409], sorted(res))
s, asg = j("GET", f"/assignments?user_id={u1['id']}")
s, asg2 = j("GET", f"/assignments?user_id={u2['id']}")
show("une seule affectation existe pour ce materiel", len(asg) + len(asg2) == 1, (len(asg), len(asg2)))
s, a1b = j("GET", f"/assets/{a1['id']}")
show("le materiel est affecte", a1b.get("statut") == "affecte", a1b.get("statut"))

print("== Double signature de la meme remise ==")
owner, other = (u1, u2) if asg else (u2, u1)
asg_id = (asg or asg2)[0]["id"]
codes = simultane("POST", f"/assignments/{asg_id}/sign", SIGN)
show("une seule des deux signatures simultanees est acceptee", codes == [201, 409], codes)
s, sigs = j("GET", f"/assignments/{asg_id}")
show("la remise est signee une seule fois", s == 200)
s, r = j("POST", f"/assignments/{asg_id}/sign", SIGN)
show("une signature ulterieure reste refusee", s == 409, f"HTTP {s}")

print("== Double restitution ==")
j("POST", f"/lifecycle/depart/{owner['id']}", {"date_sortie": "2019-01-01"})
codes = simultane("POST", "/lifecycle/restituer", {"user_id": owner["id"], **SIGN})
show("une seule des deux restitutions simultanees aboutit", codes == [201, 400], codes)
s, a1c = j("GET", f"/assets/{a1['id']}")
show("le materiel est rendu", a1c.get("statut") == "rendu", a1c.get("statut"))

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
