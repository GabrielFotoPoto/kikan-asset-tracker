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


"""Suppression de materiel en lot : simulation, refus d'un actif deja remis, perimetre, journal.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/assets_suppression_lot_check.py

Cree des donnees marquees ZZSL (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
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


def actif(n, marque="ZZSL"):
    s, a = j("POST", "/assets", {"identifiant_interne": f"ZZSL-{n}", "type": "Serveur virtuel", "marque": marque,
                                 "modele": "VM", "numero_serie": f"ZZSL-SN-{n}", "statut": "stock"})
    assert s == 201, (s, a)
    return a["id"]


def existe(asset_id):
    return j("GET", f"/assets/{asset_id}")[0] == 200


print("== Simulation ==")
a, b2, c = actif(1), actif(2), actif(3)
s, r = j("POST", "/assets/suppression-lot", {"ids": [a, b2]})
show("la simulation est le comportement par defaut", s == 200 and r["simulation"] is True and sorted(r["supprimes"]) == sorted([a, b2]), r)
show("la simulation decrit les actifs concernes", len(r["apercu"]) == 2 and {x["identifiant"] for x in r["apercu"]} == {"ZZSL-1", "ZZSL-2"}, r["apercu"])
show("la simulation ne supprime rien", existe(a) and existe(b2))

print("== Suppression reelle ==")
s, r = j("POST", "/assets/suppression-lot", {"ids": [a, b2, a], "simulation": False})
show("suppression reelle, doublons ignores", s == 200 and sorted(r["supprimes"]) == sorted([a, b2]) and r["refuses"] == [], r)
show("les actifs ont disparu", not existe(a) and not existe(b2))
show("un autre actif n'est pas touche", existe(c))

print("== Refus ==")
s, us = j("POST", "/users", {"nom": "ZZSL", "prenom": "Lot", "matricule": "ZZSL-U1", "email": "zzsl@example.invalid"})
uid = us["id"] if s in (200, 201) else None
show("salarie de test cree", uid is not None, us if uid is None else "")
remis = actif(4)
s, asg = j("POST", "/assignments", {"user_id": uid, "asset_ids": [remis], "sans_charte": True})
show("remise creee", s == 201, asg if s != 201 else "")
s, r = j("POST", "/assets/suppression-lot", {"ids": [remis, c, 99999999], "simulation": False})
raisons = {x["id"]: x["raison"] for x in r["refuses"]} if s == 200 else {}
show("un actif remis est refuse", s == 200 and remis in raisons and "remis" in raisons[remis].lower(), r)
show("un actif inconnu est refuse", 99999999 in raisons, raisons)
show("les actifs libres du meme lot sont supprimes", r.get("supprimes") == [c] and not existe(c), r)
show("l'actif remis est conserve", existe(remis))

print("== Limites et droits ==")
s, r = j("POST", "/assets/suppression-lot", {"ids": []})
show("liste vide : 422", s == 422, s)
s, r = j("POST", "/assets/suppression-lot", {"ids": list(range(1, 502))})
show("plus de 500 identifiants : 422", s == 422, s)
s, _ = call("POST", "/assets/suppression-lot", {"ids": [remis]})
show("sans jeton : refuse", s in (401, 403), s)

print("== Journal ==")
s, log = j("GET", "/audit?limit=100")
rows = log if isinstance(log, list) else log.get("items", [])
show("la suppression en lot est journalisee", any(x.get("action") == "suppression" and "en lot" in str(x.get("detail")) for x in rows), len(rows))

if fails:
    sys.exit(f"{fails} test(s) en echec")
print("Tous les tests passent.")
