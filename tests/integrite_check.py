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

"""Integrite des donnees : unicite garantie par la base (creations simultanees) et longueurs maximales des champs.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/integrite_check.py

Cree des donnees ZZINT (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. ASCII uniquement.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
fails = 0
N = 12   # requetes simultanees


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


s, b = call("POST", "/auth/login", {"username": ADMIN, "password": ADMIN_PW})
ADM = json.loads(b)["access_token"] if s == 200 else None
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None):
    s, b = call(method, path, body, ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def en_parallele(path, bodies):
    """Envoie les requetes en meme temps (barriere) ; renvoie la liste des codes HTTP."""
    codes = [None] * len(bodies)
    barriere = threading.Barrier(len(bodies))

    def run(i):
        barriere.wait()
        codes[i] = call("POST", path, bodies[i], ADM)[0]

    ts = [threading.Thread(target=run, args=(i,)) for i in range(len(bodies))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return codes


def bilan(codes):
    return sum(c == 201 for c in codes), sum(c == 409 for c in codes), sorted(set(codes))


s, ent = j("POST", "/entites", {"code": "ZZINT", "nom": "ZZ Integrite"})
if s == 409:
    ent = next(e for e in j("GET", "/entites")[1] if e["code"] == "ZZINT")
EID = ent["id"]

print("== Creations simultanees : un seul gagnant, les autres recoivent 409 ==")
ok, conflits, vus = bilan(en_parallele("/assets", [{"marque": "ZZINT", "numero_serie": "ZZINT-SN-1", "entite_id": EID} for _ in range(N)]))
show("numero de serie identique x%d : 1 creation" % N, ok == 1 and conflits == N - 1, vus)
ok, conflits, vus = bilan(en_parallele("/assets", [{"marque": "ZZINT", "identifiant_interne": "ZZINT-ID-1", "entite_id": EID} for _ in range(N)]))
show("identifiant interne identique x%d : 1 creation" % N, ok == 1 and conflits == N - 1, vus)
ok, conflits, vus = bilan(en_parallele("/users", [{"nom": "ZZInt", "prenom": "ZZUn", "matricule": "ZZINT-M1", "entite_id": EID} for _ in range(N)]))
show("matricule identique x%d : 1 creation" % N, ok == 1 and conflits == N - 1, vus)
ok, conflits, vus = bilan(en_parallele("/entites", [{"code": "ZZINT-E1", "nom": "ZZ Integrite bis"} for _ in range(N)]))
show("code d'entite identique x%d : 1 creation" % N, ok == 1 and conflits == N - 1, vus)

print("== Casse et valeurs vides ==")
s, r = j("POST", "/assets", {"marque": "ZZINT", "numero_serie": "zzint-sn-1", "entite_id": EID})
show("numero de serie en minuscules : 409 (insensible a la casse)", s == 409, s)
s, r = j("POST", "/users", {"nom": "ZZInt", "prenom": "ZZDeux", "matricule": "zzint-m1", "entite_id": EID})
show("matricule en minuscules : 409", s == 409, s)
codes = [j("POST", "/assets", {"marque": "ZZINT", "numero_serie": "", "identifiant_interne": "", "entite_id": EID})[0] for _ in range(3)]
show("plusieurs numeros de serie vides : acceptes", codes == [201, 201, 201], codes)
codes = [j("POST", "/assets", {"marque": "ZZINT", "entite_id": EID})[0] for _ in range(2)]
show("plusieurs numeros de serie absents : acceptes", codes == [201, 201], codes)
codes = [j("POST", "/users", {"nom": "ZZInt", "prenom": "ZZVide", "matricule": "", "entite_id": EID})[0] for _ in range(2)]
show("plusieurs matricules vides : acceptes", codes == [201, 201], codes)

print("== Modification : prendre la valeur d'un autre ==")
s, a1 = j("POST", "/assets", {"marque": "ZZINT", "numero_serie": "ZZINT-SN-2", "entite_id": EID})
s, r = j("PUT", "/assets/%d" % a1["id"], {"marque": "ZZINT", "numero_serie": "ZZINT-SN-1", "entite_id": EID})
show("PUT vers le numero de serie d'un autre actif : 409", s == 409, s)
s, r = j("PUT", "/assets/%d" % a1["id"], {"marque": "ZZINT", "numero_serie": "ZZINT-SN-2", "notes": "ok", "entite_id": EID})
show("PUT en gardant son propre numero de serie : 200", s == 200, s)

print("== Longueurs maximales (422) ==")
LIM_ASSET = {"identifiant_interne": 100, "type": 100, "marque": 100, "modele": 100, "numero_serie": 100, "notes": 2000}
for champ, lim in LIM_ASSET.items():
    base = {"marque": "ZZINT", "entite_id": EID}
    s_ok, _ = j("POST", "/assets", {**base, champ: ("ZZ" + "x" * lim)[:lim] if champ != "numero_serie" else "ZZINT-L-" + "x" * (lim - 8)})
    s_ko, _ = j("POST", "/assets", {**base, champ: "ZZ" + "x" * lim})
    show("actif.%s : %d accepte, %d refuse" % (champ, lim, lim + 2), s_ok == 201 and s_ko == 422, (s_ok, s_ko))
LIM_USER = {"matricule": 50, "nom": 200, "prenom": 200, "email": 200, "service": 100}
for champ, lim in LIM_USER.items():
    base = {"nom": "ZZInt", "prenom": "ZZLong", "entite_id": EID}
    valeur = {"email": ("a" * (lim - 7)) + "@zz.test", "matricule": "ZZL-" + "x" * (lim - 4)}.get(champ, "ZZ" + "x" * (lim - 2))
    s_ok, r_ok = j("POST", "/users", {**base, champ: valeur})
    s_ko, _ = j("POST", "/users", {**base, champ: valeur + "xx"})
    show("salarie.%s : %d accepte, %d refuse" % (champ, lim, lim + 2), s_ok in (201, 400, 422) and s_ko == 422 and (s_ok != 422 or champ == "email"), (s_ok, s_ko))
s, _ = j("POST", "/users", {"nom": "N" * 200000, "prenom": "ZZInt", "entite_id": EID})
show("salarie.nom de 200000 caracteres : 422", s == 422, s)
s, _ = j("POST", "/assets", {"marque": "ZZINT", "notes": "N" * 1000000, "entite_id": EID})
show("actif.notes de 1000000 caracteres : 422", s == 422, s)
s, _ = j("POST", "/entites", {"code": "ZZINT-X" + "x" * 60, "nom": "ZZ"})
show("entite.code trop long : 422", s == 422, s)
s, _ = j("POST", "/entites", {"code": "ZZINT-E2", "nom": "Z" * 201})
show("entite.nom trop long : 422", s == 422, s)
s, _ = j("POST", "/applications", {"nom": "ZZINT-" + "x" * 200})
show("application.nom trop long : 422", s == 422, s)
s, _ = j("POST", "/applications", {"nom": "ZZINT-app", "description": "d" * 2001})
show("application.description trop longue : 422", s == 422, s)
s, a = j("GET", "/assets/%d" % a1["id"])
s2, _ = j("PUT", "/assets/%d" % a1["id"], {"marque": "ZZINT", "notes": "n" * 2001, "entite_id": EID})
show("PUT avec notes trop longues : 422", s2 == 422, s2)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
