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

"""Recherche globale (GET /search, palette Ctrl+K) : etancheite de la portee par entite et forme de la reponse.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/search_check.py

Organisation de test : un groupe ZZSR-G avec deux filiales (A, B) et un site sous A. Cree des donnees ZZSR et des
comptes sec_sr* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. ASCII uniquement.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
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


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        accs = j("GET", "/auth/accounts")[1]
        acc = next(a for a in accs if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


def search(q, token, **params):
    qs = urllib.parse.urlencode({"q": q, **params})
    return j("GET", "/search?" + qs, token=token)


def seen(rows, wanted):
    """Cles (A, A1, B, N) des elements de test presents dans `rows`."""
    ids = {r["id"] for r in rows}
    return {k for k, v in wanted.items() if v["id"] in ids}


print("== Organisation de test ==")
ent = {}
for code, parent in [("ZZSR-G", None), ("ZZSR-A", "ZZSR-G"), ("ZZSR-B", "ZZSR-G"), ("ZZSR-A1", "ZZSR-A")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB, EA1 = ent["ZZSR-A"], ent["ZZSR-B"], ent["ZZSR-A1"]
show("4 entites creees", len(ent) == 4)

assets, users = {}, {}
for key, eid in [("A", EA), ("A1", EA1), ("B", EB), ("N", None)]:
    s, r = j("POST", "/assets", {"type": "ZZSR type", "marque": "ZZSR Marqué", "modele": "Mod" + key,
                                   "numero_serie": "ZZSR-SN-" + key, "identifiant_interne": "ZZSR-ID-" + key,
                                   "notes": "ZZSR note confidentielle", "entite_id": eid})
    assets[key] = r
show("4 actifs crees (A, site A1, B, sans entite)", all(isinstance(a, dict) and "id" in a for a in assets.values()), assets)
for key, eid in [("A", EA), ("B", EB), ("N", None)]:
    s, r = j("POST", "/users", {"matricule": "ZZSR-U" + key, "nom": "ZZSRNom" + key, "prenom": "Zoe", "email": "zzsr.%s@exemple.test" % key.lower(),
                                  "entite_id": eid})
    users[key] = r
show("3 salaries crees (A, B, sans entite)", all(isinstance(u, dict) and "id" in u for u in users.values()), users)

print("== Comptes ==")
account("sec_sr_it", "informatique")
account("sec_sr_rh0", "rh")
s, r = account("sec_sr_rhA", "rh", portee_globale=False, entites=[EA])
RHA_ID = r.get("id")
account("sec_sr_rhB", "rh", portee_globale=False, entites=[EB])
account("sec_sr_lecA", "lecture", portee_globale=False, entites=[EA])
IT, R0, RA, RB, LA = (login(n, PW) for n in ("sec_sr_it", "sec_sr_rh0", "sec_sr_rhA", "sec_sr_rhB", "sec_sr_lecA"))
show("connexions de test", all([IT, R0, RA, RB, LA]))

print("== Acces et validation ==")
s, b = call("GET", "/search?q=zzsr")
show("sans jeton : refuse", s in (401, 403), s)
s, r = search("z", IT)
show("moins de 2 caracteres : resultat vide", s == 200 and r["materiel"] == [] and r["utilisateurs"] == [] and r["total_materiel"] == 0, r)
s, r = search("", IT)
show("requete vide : resultat vide", s == 200 and r["materiel"] == [] and r["utilisateurs"] == [])
s, r = search("  ", IT)
show("espaces seuls : resultat vide", s == 200 and r["materiel"] == [])
s, r = search("x" * 81, IT)
show("requete de plus de 80 caracteres : 422", s == 422, s)
s, r = search("zzsr", IT, limit=11)
show("limit au-dela de 10 : 422", s == 422, s)
s, r = search("zzsr", IT, limit=0)
show("limit a 0 : 422", s == 422, s)
s, r = search("%' OR 1=1 --", IT)
show("caracteres SQL : traites comme du texte, aucun resultat", s == 200 and r["materiel"] == [] and r["utilisateurs"] == [], r)

print("== Compte global (informatique) ==")
s, r = search("zzsr-sn", IT)
show("voit les 4 actifs, dont celui sans entite", s == 200 and seen(r["materiel"], assets) == {"A", "A1", "B", "N"} and r["total_materiel"] >= 4, r.get("total_materiel"))
s, r = search("MARQUE zzsr", IT)
show("casse et accents ignores, tous les termes exiges", s == 200 and seen(r["materiel"], assets) == {"A", "A1", "B", "N"}, r.get("total_materiel"))
s, r = search("zzsr marque modb", IT)
show("un terme qui ne correspond pas exclut l'actif", s == 200 and seen(r["materiel"], assets) == {"B"}, seen(r["materiel"], assets))
s, r = search("zzsrnom", IT)
show("voit les 3 salaries", s == 200 and seen(r["utilisateurs"], users) == {"A", "B", "N"}, r.get("total_utilisateurs"))
s, r = search("zzsr-sn", IT, limit=2)
show("limit borne la liste, le total reste complet", s == 200 and len(r["materiel"]) == 2 and r["total_materiel"] >= 4, (len(r.get("materiel", [])), r.get("total_materiel")))

print("== Portee par entite ==")
for who, tok, expect_assets, expect_users in [("RH A", RA, {"A", "A1"}, {"A"}), ("RH B", RB, {"B"}, {"B"}),
                                              ("lecture A", LA, {"A", "A1"}, {"A"}), ("RH sans portee", R0, set(), set())]:
    s, r = search("zzsr", tok)
    show("actifs - " + who, s == 200 and seen(r["materiel"], assets) == expect_assets, sorted(seen(r.get("materiel", []), assets)))
    show("salaries - " + who, s == 200 and seen(r["utilisateurs"], users) == expect_users, sorted(seen(r.get("utilisateurs", []), users)))
s, r = search("zzsr", RA)
show("RH A : les totaux ne revelent pas les elements hors portee",
     s == 200 and r["total_materiel"] == 2 and r["total_utilisateurs"] == 1, (r.get("total_materiel"), r.get("total_utilisateurs")))
s, r = search("zzsr", R0)
show("RH sans portee : totaux a zero", s == 200 and r["total_materiel"] == 0 and r["total_utilisateurs"] == 0, r)
s, r = search("zzsr-sn-b", RA)
show("recherche exacte d'un actif hors portee : introuvable", s == 200 and r["materiel"] == [] and r["total_materiel"] == 0, r)
s, r = search("zzsr-sn-n", RA)
show("actif sans entite : invisible d'un compte cloisonne", s == 200 and r["materiel"] == [])

print("== Forme de la reponse ==")
s, r = search("zzsr-sn-a", IT)
item = next((a for a in r["materiel"] if a["id"] == assets["A"]["id"]), {})
show("actif : seulement les champs deja visibles dans les listes",
     set(item) == {"id", "type", "marque", "modele", "numero_serie", "identifiant_interne", "statut"}, sorted(item))
s, r = search("zzsrnoma", IT)
item = next((u for u in r["utilisateurs"] if u["id"] == users["A"]["id"]), {})
show("salarie : ni e-mail ni autre donnee personnelle", set(item) == {"id", "nom", "prenom", "matricule", "statut"}, sorted(item))
s, r = search("confidentielle", IT)
show("les notes ne sont pas indexees", s == 200 and r["materiel"] == [], r.get("materiel"))
s, r = search("zzsr.a@exemple", IT)
show("l'e-mail n'est pas indexe", s == 200 and r["utilisateurs"] == [], r.get("utilisateurs"))

print("== Effet immediat d'un changement de portee ==")
if RHA_ID:
    s, r = j("PUT", "/auth/accounts/%d" % RHA_ID, {"entites": [EB]})
    s, r = search("zzsr-sn", RA)
    show("portee deplacee de A vers B : la recherche suit", s == 200 and seen(r["materiel"], assets) == {"B"}, sorted(seen(r.get("materiel", []), assets)))
    j("PUT", "/auth/accounts/%d" % RHA_ID, {"entites": [EA]})
    s, r = search("zzsr-sn", RA)
    show("portee remise sur A", s == 200 and seen(r["materiel"], assets) == {"A", "A1"}, sorted(seen(r.get("materiel", []), assets)))
else:
    show("compte RH A recupere", False)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
