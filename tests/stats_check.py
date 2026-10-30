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

"""Statistiques exportables (C1) : filtres par entite et periode, portee des comptes, exports CSV, Excel et PDF.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/stats_check.py

Cree des donnees ZZST et des comptes sec_st* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
ASCII uniquement.
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


from datetime import date, timedelta

TODAY = date.today()


def raw(path, token=None):
    return call("GET", path, None, token or ADM)


def stats(query="", token=None):
    return j("GET", "/stats" + query, None, token)


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


print("== Organisation de test ==")
ent = {}
for code, parent in [("ZZST-G", None), ("ZZST-A", "ZZST-G"), ("ZZST-A1", "ZZST-A"), ("ZZST-B", "ZZST-G")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EA1, EB = ent["ZZST-A"], ent["ZZST-A1"], ent["ZZST-B"]

users, assets = {}, {}
for key, eid in [("A", EA), ("A1", EA1), ("B", EB)]:
    s, r = j("POST", "/users", {"matricule": "ZZST-" + key, "nom": "ZZST" + key, "prenom": "ZZST-" + key,
                                "entite_id": eid, "service": "ZZST svc " + key})
    users[key] = r
    renouv = str(TODAY + timedelta(days=30)) if key != "A1" else str(TODAY + timedelta(days=500))
    s, r = j("POST", "/assets", {"type": "ZZST type", "marque": "ZZST", "modele": "M" + key, "numero_serie": "ZZST-SN-" + key,
                                   "identifiant_interne": "ZZST-ID-" + key, "entite_id": eid,
                                   "date_achat": "2025-03-15", "echeance_renouvellement": renouv})
    assets[key] = r
for key in ("A", "A1", "B"):
    j("POST", "/assignments", {"user_id": users[key]["id"], "asset_ids": [assets[key]["id"]]})
show("donnees creees", all("id" in v for v in list(users.values()) + list(assets.values())), (users, assets))


def mine(rows):
    return [r for r in rows if "ZZST" in str(r)]


print("== Filtres ==")
s, tout = stats()
show("sans filtre : 200 et filtres vides", s == 200 and tout["filtres"] == {"entite_id": None, "entite": None, "du": None, "au": None}, tout.get("filtres"))
show("sans filtre : pas de bloc mouvements", "mouvements" not in tout)
show("sans filtre : renouvellements sur 12 mois", tout["renouvellements"]["du"] == str(TODAY)
     and tout["renouvellements"]["au"] == str(TODAY + timedelta(days=365)))
s, ea = stats("?entite_id=%d" % EA)
show("entite A : sous-entite A1 incluse", s == 200 and ea["actifs_total"] == 2 and ea["filtres"]["entite"] == "ZZST-A", ea.get("actifs_total"))
show("entite A : repartition par entite sans B", {i["entite"] for i in ea["par_entite"]} == {"ZZST-A", "ZZST-A1"}, ea["par_entite"])
s, eb = stats("?entite_id=%d" % EB)
show("entite B : un seul actif", s == 200 and eb["actifs_total"] == 1, eb.get("actifs_total"))
show("entite B : renouvellement a 12 mois = 1", eb["renouvellements_12m"]["count"] == 1)
show("entite A : renouvellement A1 (500 jours) hors 12 mois", ea["renouvellements_12m"]["count"] == 1, ea["renouvellements_12m"])
s, r = stats("?entite_id=99999999")
show("entite inconnue : 404", s == 404, r)

print("== Periode ==")
s, p = stats("?entite_id=%d&du=2025-01-01&au=2025-12-31" % EA)
show("periode : bloc mouvements present", s == 200 and "mouvements" in p, p)
show("periode : 2 achats en mars 2025", p["mouvements"]["achetes"] == 2 and p["mouvements"]["par_mois"][0]["mois"] == "2025-03", p["mouvements"])
show("periode passee : aucune remise", p["mouvements"]["remis"] == 0)
s, p2 = stats("?entite_id=%d&du=%s&au=%s" % (EA, TODAY, TODAY))
show("periode du jour : 2 remises", s == 200 and p2["mouvements"]["remis"] == 2 and p2["mouvements"]["restitues"] == 0, p2.get("mouvements"))
show("periode du jour : fenetre de renouvellement bornee", p2["renouvellements"]["du"] == p2["renouvellements"]["au"] == str(TODAY)
     and p2["renouvellements"]["count"] == 0, p2["renouvellements"])
s, p3 = stats("?entite_id=%d&du=%s" % (EA, TODAY))
show("debut seul : fenetre de 12 mois", p3["renouvellements"]["count"] == 1 and p3["renouvellements"]["au"] == str(TODAY + timedelta(days=365)))
s, r = stats("?du=2026-02-01&au=2026-01-01")
show("debut apres la fin : 422", s == 422, r)
s, r = stats("?du=pas-une-date")
show("date invalide : 422", s == 422, r)

print("== Portee des comptes ==")
s, r = account("sec_st_ra", "rh", portee_globale=False, entites=[EA])
show("compte RH limite a A cree", s in (200, 201), r)
RA = login("sec_st_ra", PW)
s, r = stats("", RA)
show("RH limite : ne voit que A et A1", s == 200 and "ZZST-B" not in {i["entite"] for i in r["par_entite"]}, r.get("par_entite"))
s, r = stats("?entite_id=%d" % EB, RA)
show("RH limite : entite B hors portee = 404", s == 404, r)
s, r = stats("?entite_id=%d" % EA1, RA)
show("RH limite : sous-entite A1 accessible", s == 200 and r["actifs_total"] == 1, r.get("actifs_total"))
s, b = raw("/stats?format=csv&entite_id=%d" % EB, RA)
show("RH limite : export hors portee refuse", s == 404, b[:80])
s, b = raw("/stats?format=csv", RA)
show("RH limite : export sans filtre ne contient pas B", s == 200 and b"ZZST-B" not in b and b"ZZST-A" in b, b[:80])

print("== Exports ==")
q = "?entite_id=%d&du=2025-01-01&au=2025-12-31" % EA
s, b = raw("/stats?format=csv&entite_id=%d&du=2025-01-01&au=2025-12-31" % EA)
show("CSV : 200 avec BOM et entete", s == 200 and b.startswith("\ufeffRubrique;Libelle;Valeur".encode()), b[:40])
show("CSV : sections attendues", all(t in b.decode() for t in ("Synthese", "Mouvements de la periode")))
s, b2 = raw("/stats?format=csv&entite_id=%d" % EA)
show("CSV : renouvellements a venir presents", s == 200 and "Renouvellements du" in b2.decode() and "ZZST-ID-A" in b2.decode(), b2[:60])
show("CSV : sans B", b"ZZST-B" not in b)
req = urllib.request.Request(B + "/stats?format=csv", headers={"Authorization": "Bearer " + ADM})
r = urllib.request.urlopen(req, timeout=120)
show("CSV : type et nom de fichier", r.headers["Content-Type"].startswith("text/csv")
     and ("kikan-statistiques-%s.csv" % TODAY) in r.headers["Content-Disposition"], r.headers["Content-Disposition"])
s, b = raw("/stats?format=xlsx&entite_id=%d" % EA)
show("Excel : archive zip valide", s == 200 and b[:2] == b"PK", b[:8])
s, b = raw("/stats?format=pdf&entite_id=%d&du=2025-01-01&au=2025-12-31" % EA)
show("PDF : fichier PDF", s == 200 and b[:5] == b"%PDF-", b[:8])
s, b = raw("/stats?format=pdf")
show("PDF sans filtre", s == 200 and b[:5] == b"%PDF-")
s, b = raw("/stats?format=exe")
show("format inconnu : 422", s == 422, b[:80])
s, b = call("GET", "/stats?format=csv", None, None)
show("export sans session : 401", s in (401, 403), s)

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
