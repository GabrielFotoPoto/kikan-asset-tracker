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

"""Besoins materiels (B7) : saisie par les RH, cycle de vie, cloisonnement, solde par la remise, suppression et purge.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/besoins_check.py

Cree des donnees ZZBS et des comptes sec_bs* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test
echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, "/app")

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
TODAY = date.today()
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


def call(method, path, payload=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers=h)
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


def j(method, path, payload=None, token=None):
    s, b = call(method, path, payload, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def account(name, role, **scope):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, **scope})
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})


def ids(rows):
    return {r["id"] for r in rows}


print("== Preparation ==")
ent = {}
for code in ("ZZBS-A", "ZZBS-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZBS-A"], ent["ZZBS-B"]
account("sec_bs_it", "informatique")
account("sec_bs_rha", "rh", portee_globale=False, entites=[EA])
account("sec_bs_rhb", "rh", portee_globale=False, entites=[EB])
account("sec_bs_rh0", "rh")
account("sec_bs_lec", "lecture", portee_globale=True)
IT, RA, RB, R0, LEC = (login(n, PW) for n in ("sec_bs_it", "sec_bs_rha", "sec_bs_rhb", "sec_bs_rh0", "sec_bs_lec"))
show("comptes de test", all([IT, RA, RB, R0, LEC]))
arrivee = (TODAY + timedelta(days=10)).isoformat()
s, UA = j("POST", "/users", {"matricule": "ZZBS-A", "nom": "NomA", "prenom": "ZZBSa", "entite_id": EA, "statut": "prevu", "date_arrivee": arrivee})
s, UB = j("POST", "/users", {"matricule": "ZZBS-B", "nom": "NomB", "prenom": "ZZBSb", "entite_id": EB, "statut": "prevu", "date_arrivee": arrivee})
s, r = j("POST", "/parametres/types", {"nom": "ZZBS portable"})
s, r2 = j("POST", "/parametres/types", {"nom": "ZZBS ecran"})
show("salaries et types crees", "id" in UA and "id" in UB and s in (201, 409), (s, r2))

print("== Saisie par une RH ==")
s, b1 = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable", "quantite": 1, "commentaire": "avec sacoche"}, token=RA)
show("la RH cree un besoin pour un salarie de son perimetre", s == 201 and b1["statut"] == "demande" and b1["cree_par"] == "sec_bs_rha", b1)
show("date souhaitee par defaut : date d'arrivee", b1.get("date_souhaitee") == arrivee, b1.get("date_souhaitee"))
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "zzbs ECRAN", "quantite": 2}, token=RA)
show("le type est ramene a la graphie de la liste", s == 201 and r["type"] == "ZZBS ecran", r)
b2 = r
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS inconnu"}, token=RA)
show("type hors liste -> 400 (les RH ne creent pas de types)", s == 400, r)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable", "quantite": 0}, token=RA)
show("quantite 0 -> 422", s == 422)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable", "quantite": 21}, token=RA)
show("quantite 21 -> 422", s == 422)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable", "commentaire": "x" * 201}, token=RA)
show("commentaire trop long -> 422", s == 422)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable", "commentaire": "ligne1\r\nligne2\x00"}, token=RA)
show("commentaire : sauts de ligne et controles retires", s == 201 and r["commentaire"] == "ligne1 ligne2", r)
b3 = r
s, r = j("POST", "/besoins", {"user_id": UB["id"], "type": "ZZBS portable"}, token=RA)
show("salarie d'une autre entite -> 404", s == 404, r)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable"}, token=R0)
show("RH sans perimetre -> 404", s == 404)
s, r = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable"}, token=LEC)
show("lecture : creation refusee", s == 403)
s, r = j("POST", "/besoins", {"user_id": 999999, "type": "ZZBS portable"}, token=RA)
show("salarie inconnu -> 404", s == 404)
s, bb = j("POST", "/besoins", {"user_id": UB["id"], "type": "ZZBS portable"}, token=RB)
show("la RH B cree pour son salarie", s == 201, bb)

print("== Lecture et cloisonnement ==")
for who, tok, expect in [("RH A", RA, {b1["id"], b2["id"], b3["id"]}), ("RH B", RB, {bb["id"]}),
                         ("informatique", IT, {b1["id"], b2["id"], b3["id"], bb["id"]}), ("lecture", LEC, {b1["id"], b2["id"], b3["id"], bb["id"]}),
                         ("RH sans perimetre", R0, set())]:
    s, rows = j("GET", "/besoins", token=tok)
    got = ids(rows) & {b1["id"], b2["id"], b3["id"], bb["id"]}
    show("liste des besoins - " + who, s == 200 and got == expect, sorted(got))
s, rows = j("GET", "/besoins?statut=ouverts", token=RA)
show("filtre sur les besoins ouverts", s == 200 and len(rows) == 3)
s, rows = j("GET", "/besoins?statut=nimporte", token=RA)
show("statut de filtre inconnu -> 400", s == 400)
s, rows = j("GET", "/besoins?entite_id=%d" % EB, token=RA)
show("filtre sur une entite hors perimetre : vide", s == 200 and rows == [])
s, rows = j("GET", "/besoins/ouverts/%d" % UA["id"], token=RA)
show("besoins ouverts d'un salarie du perimetre", s == 200 and len(rows) == 3)
s, rows = j("GET", "/besoins/ouverts/%d" % UB["id"], token=RA)
show("besoins ouverts d'un salarie hors perimetre -> 404", s == 404)

print("== Modification et statuts ==")
s, r = j("PUT", "/besoins/%d" % b1["id"], {"quantite": 3, "commentaire": "avec sacoche et souris"}, token=RA)
show("la RH modifie un besoin en demande", s == 200 and r["quantite"] == 3 and r["commentaire"] == "avec sacoche et souris", r)
s, r = j("PUT", "/besoins/%d" % bb["id"], {"quantite": 2}, token=RA)
show("modifier un besoin hors perimetre -> 404", s == 404)
s, r = j("PUT", "/besoins/%d" % b1["id"], {"type": "ZZBS inconnu"}, token=RA)
show("modifier avec un type hors liste -> 400", s == 400)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "en_preparation"}, token=RA)
show("la RH ne met pas un besoin en preparation -> 403", s == 403)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "en_preparation"}, token=LEC)
show("lecture : changement de statut refuse", s == 403)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "satisfait"}, token=IT)
show("'satisfait' ne s'obtient pas par ce chemin -> 422", s == 422)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "en_preparation"}, token=IT)
show("l'informatique met en preparation", s == 200 and r["statut"] == "en_preparation" and r["traite_par"] == "sec_bs_it", r)
s, r = j("PUT", "/besoins/%d" % b1["id"], {"quantite": 2}, token=RA)
show("la RH ne modifie plus un besoin en preparation -> 409", s == 409)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "annule"}, token=RA)
show("la RH n'annule pas un besoin en preparation -> 403", s == 403)
s, r = j("PUT", "/besoins/%d" % b1["id"], {"quantite": 2}, token=IT)
show("l'informatique modifie un besoin en preparation", s == 200 and r["quantite"] == 2)
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "demande"}, token=IT)
show("retour en demande par l'informatique", s == 200 and r["statut"] == "demande")
s, r = j("POST", "/besoins/%d/statut" % b3["id"], {"statut": "annule"}, token=RA)
show("la RH annule un besoin en demande", s == 200 and r["statut"] == "annule")
s, r = j("POST", "/besoins/%d/statut" % b3["id"], {"statut": "demande"}, token=IT)
show("un besoin annule est clos -> 409", s == 409)
s, r = j("PUT", "/besoins/%d" % b3["id"], {"quantite": 5}, token=IT)
show("un besoin annule n'est plus modifiable -> 409", s == 409)
s, r = j("POST", "/besoins/%d/statut" % b2["id"], {"statut": "demande"}, token=IT)
show("meme statut -> 409", s == 409)

print("== Solde par la remise ==")
s, a1 = j("POST", "/assets", {"type": "ZZBS portable", "marque": "ZZBS", "modele": "P1", "numero_serie": "ZZBS-SN-1",
                              "identifiant_interne": "ZZBS-ID-1", "entite_id": EA})
s, a2 = j("POST", "/assets", {"type": "ZZBS ecran", "marque": "ZZBS", "modele": "E1", "numero_serie": "ZZBS-SN-2",
                              "identifiant_interne": "ZZBS-ID-2", "entite_id": EA})
s, a3 = j("POST", "/assets", {"type": "ZZBS portable", "marque": "ZZBS", "modele": "P3", "numero_serie": "ZZBS-SN-3",
                              "identifiant_interne": "ZZBS-ID-3", "entite_id": EB})
n_before = len(j("GET", "/assignments")[1])
s, r = j("POST", "/assignments", {"user_id": UA["id"], "asset_ids": [a1["id"]], "besoin_ids": [bb["id"]]})
show("besoin d'un autre salarie -> 400, aucune remise creee",
     s == 400 and len(j("GET", "/assignments")[1]) == n_before and j("GET", "/assets/%d" % a1["id"])[1]["statut"] == "stock", r)
s, r = j("POST", "/assignments", {"user_id": UA["id"], "asset_ids": [a1["id"]], "besoin_ids": [b3["id"]]})
show("besoin deja clos -> 409, aucune remise creee", s == 409 and len(j("GET", "/assignments")[1]) == n_before, r)
s, r = j("POST", "/assignments", {"user_id": UA["id"], "asset_ids": [a1["id"]], "besoin_ids": [999999]})
show("besoin inconnu -> 400", s == 400)
s, r = j("POST", "/assignments", {"user_id": UA["id"], "asset_ids": [a1["id"]], "besoin_ids": [b1["id"]]}, token=RA)
show("la RH ne cree pas de remise", s == 403)
s, asg = j("POST", "/assignments", {"user_id": UA["id"], "asset_ids": [a1["id"], a2["id"]], "besoin_ids": [b1["id"], b2["id"]]})
show("remise creee avec solde des besoins", s == 201, asg)
s, rows = j("GET", "/besoins?user_id=%d" % UA["id"])
by_id = {r["id"]: r for r in rows}
show("les besoins sont satisfaits et relies a la remise",
     all(by_id[i]["statut"] == "satisfait" and by_id[i]["assignment_id"] == asg["id"] for i in (b1["id"], b2["id"])), [by_id[i]["statut"] for i in (b1["id"], b2["id"])])
show("traite par le compte qui a cree la remise", by_id[b1["id"]]["traite_par"] == "admin", by_id[b1["id"]]["traite_par"])
s, r = j("POST", "/besoins/%d/statut" % b1["id"], {"statut": "annule"}, token=IT)
show("un besoin satisfait est clos -> 409", s == 409)
s, r = j("GET", "/besoins/ouverts/%d" % UA["id"], token=RA)
show("plus aucun besoin ouvert pour ce salarie", s == 200 and r == [])
s, r = j("POST", "/assignments", {"user_id": UB["id"], "asset_ids": [a3["id"]], "besoin_ids": [bb["id"], bb["id"]]})
show("un meme besoin cite deux fois n'est solde qu'une fois", s == 201, r)

print("== Tableau de bord ==")
s, st = j("POST", "/besoins", {"user_id": UA["id"], "type": "ZZBS portable"}, token=RA)
s, r = j("GET", "/stats", token=RA)
show("compteur 'besoins a traiter' limite au perimetre de la RH", s == 200 and r["besoins_a_traiter"] == 1, r.get("besoins_a_traiter"))
s, r = j("GET", "/stats", token=R0)
show("compteur pour une RH sans perimetre : 0", r["besoins_a_traiter"] == 0)
s, r = j("GET", "/stats", token=IT)
show("compteur informatique : tous les besoins ouverts", r["besoins_a_traiter"] >= 1)

print("== Suppression et purge RGPD ==")
s, r = j("DELETE", "/users/%d" % UA["id"], token=IT)
show("un salarie avec des besoins ne se supprime pas -> 409", s == 409 and "besoin" in json.dumps(r), r)
from sqlmodel import Session, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Besoin, User  # noqa: E402

s, prev = j("GET", "/rgpd/purge-preview")
baseline = prev["count"]
with Session(engine) as s_:
    u = User(matricule="ZZBS-OLD", nom="Ancien", prenom="ZZBSold", statut="sorti", date_sortie=date(2000, 1, 1), entite_id=EA)
    s_.add(u)
    s_.commit()
    s_.refresh(u)
    s_.add(Besoin(user_id=u.id, type="ZZBS portable", statut="annule"))
    s_.commit()
    old_id = u.id
s, prev = j("GET", "/rgpd/purge-preview")
show("le salarie ancien est candidat a la purge", prev["count"] == baseline + 1, prev["count"])
if prev["count"] == baseline + 1:
    s, r = j("POST", "/rgpd/purge")
    with Session(engine) as s_:
        left = s_.exec(select(Besoin).where(Besoin.user_id == old_id)).all()
    show("la purge supprime aussi les besoins du salarie", s == 200 and not left, (s, len(left)))
else:
    show("la purge supprime aussi les besoins du salarie", False, "preconditions non reunies")

print("== Acces et audit ==")
for who, tok in (("sans jeton", None),):
    s, r = j("GET", "/besoins", token=None) if False else call("GET", "/besoins")[0], None
    show("liste sans jeton -> 401", s == 401, s)
s, rows = j("GET", "/audit?limit=300")
rows = rows if isinstance(rows, list) else rows.get("items", [])
actions = {r.get("action") for r in rows}
show("creation, modification, statut et solde journalises",
     {"besoin_cree", "besoin_modifie", "besoin_statut", "besoins_soldes"} <= actions, sorted(a for a in actions if a and a.startswith("besoin")))
show("le journal ne contient pas le texte des commentaires", all("sacoche" not in json.dumps(r) for r in rows))

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
