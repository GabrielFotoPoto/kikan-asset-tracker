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

"""Previsions de renouvellement (C3) : couts de remplacement, budget par mois, annee, type et entite, portee, exports.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/previsions_check.py

Cree des donnees ZZPV et des comptes sec_pv* (nettoyage : tests/cleanup_test_data.sql). Les dates sont fixes (2031) : le
resultat ne depend pas du jour d'execution. Code de sortie 1 si un test echoue. ASCII uniquement.
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


import io
from datetime import date

TODAY = date.today()


def raw(path, token=None):
    return call("GET", path, None, token or ADM)


def prev(query="", token=None):
    return j("GET", "/previsions" + query, None, token)


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


def type_id(nom):
    s, r = j("POST", "/parametres/types", {"nom": nom})
    if s == 409:
        r = next(t for t in j("GET", "/parametres/types")[1] if t["nom"].lower() == nom.lower())
    return r["id"]


print("== Organisation et couts ==")
ent = {}
for code, parent in [("ZZPV-G", None), ("ZZPV-A", "ZZPV-G"), ("ZZPV-B", "ZZPV-G")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZPV-A"], ent["ZZPV-B"]
T, U, V = "ZZPV portable", "ZZPV ecran", "ZZPV vide"
tid, uid, vid = type_id(T), type_id(U), type_id(V)

s, r = j("PUT", "/parametres/couts", {"type": "ZZPV inconnu", "montant": 10})
show("type inconnu refuse", s == 400, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "marque": "ZZPV", "montant": 10})
show("marque sans modele refuse", s == 400, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "montant": -1})
show("montant negatif refuse", s == 422, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "montant": 2000000})
show("montant excessif refuse", s == 422, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "montant": "1000.00"})
cout_t = r.get("id") if isinstance(r, dict) else None
show("cout du type enregistre", s == 200 and r["montant"] == 1000.0 and r["modele"] is None, r)
s, r = j("PUT", "/parametres/couts", {"type": T.upper(), "montant": 1000})
show("meme type (casse differente) : remplace, pas de doublon", s == 200 and r["id"] == cout_t, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "marque": "ZZPV", "modele": "Pro", "montant": 1500.5})
show("exception de modele enregistree", s == 200 and r["montant"] == 1500.5 and r["modele"] == "Pro", r)
s, r = j("PUT", "/parametres/couts", {"type": V, "montant": 50})
cout_v = r["id"]
s, lst = j("GET", "/parametres/couts")
mine = [c for c in lst if c["type"].startswith("ZZPV")]
show("liste : 3 couts", s == 200 and len(mine) == 3, mine)

print("== Materiel ==")
def asset(cle, type_, marque, modele, echeance, eid, statut=None):
    body = {"type": type_, "marque": marque, "modele": modele, "numero_serie": "ZZPV-SN-" + cle,
            "identifiant_interne": "ZZPV-ID-" + cle, "entite_id": eid, "echeance_renouvellement": echeance}
    s, r = j("POST", "/assets", body)
    if statut and "id" in r:
        j("PUT", "/assets/%d" % r["id"], {**body, "statut": statut})
    return r

a1 = asset("1", T, "ZZPV", "Std", "2031-03-10", EA)
a2 = asset("2", T, "ZZPV", "Pro", "2031-03-20", EA)
a3 = asset("3", T, "ZZPV", "Std", "2031-05-05", EB)
a4 = asset("4", U, "ZZPV", "Ecr", "2031-07-01", EB)
a5 = asset("5", T, "ZZPV", "Std", "2030-12-31", EA)
a6 = asset("6", T, "ZZPV", "Std", "2031-04-01", EA, statut="reforme")
a7 = asset("7", T, "ZZPV", "Std", "2032-01-01", EA)
show("7 materiels crees", all("id" in a for a in (a1, a2, a3, a4, a5, a6, a7)), [a1, a6])

print("== Calcul ==")
P = "du=2031-01-01&au=2031-12-31"
s, p = prev("?" + P)
mine_items = [i for i in p["items"] if (i["identifiant_interne"] or "").startswith("ZZPV")]
show("periode 2031 : 4 materiels a renouveler (reforme et hors periode exclus)", s == 200 and len(mine_items) == 4, [i["identifiant_interne"] for i in mine_items])
show("devise et periode", p["devise"] == "EUR" and p["periode"] == {"du": "2031-01-01", "au": "2031-12-31"}, p["periode"])
mars = next(m for m in p["par_mois"] if m["mois"] == "2031-03")
show("mars : 2 materiels, 2500,50 EUR (type + exception de modele)", mars["nombre"] == 2 and mars["montant"] == 2500.5, mars)
mai = next(m for m in p["par_mois"] if m["mois"] == "2031-05")
show("mai : 1000 EUR", mai["nombre"] == 1 and mai["montant"] == 1000.0, mai)
juil = next(m for m in p["par_mois"] if m["mois"] == "2031-07")
show("juillet : ecran sans cout = sans estimation, budget nul", juil["nombre"] == 1 and juil["montant"] == 0 and juil["sans_estimation"] == 1, juil)
show("12 mois listes, y compris les mois vides", len(p["par_mois"]) == 12 and p["par_mois"][0]["mois"] == "2031-01" and p["par_mois"][0]["nombre"] == 0)
an = next(x for x in p["par_annee"] if x["annee"] == 2031)
show("annee 2031 : 3500,50 EUR", an["montant"] == 3500.5 and an["nombre"] >= 4, an)
pt = {x["type"]: x for x in p["par_type"]}
show("par type", pt[T]["montant"] == 3500.5 and pt[T]["nombre"] == 3 and pt[U]["sans_estimation"] == 1, pt.get(T))
pe = {x["entite"]: x for x in p["par_entite"]}
show("par entite", pe["ZZPV-A"]["montant"] == 2500.5 and pe["ZZPV-B"]["montant"] == 1000.0, pe)
show("echeance anterieure a la periode : en retard (1000 EUR)", p["en_retard"]["nombre"] >= 1 and p["en_retard"]["montant"] >= 1000.0, p["en_retard"])
src = {i["identifiant_interne"]: i["source_cout"] for i in mine_items}
show("source du cout : modele, type, aucune", src["ZZPV-ID-2"] == "modele" and src["ZZPV-ID-1"] == "type" and src["ZZPV-ID-4"] is None, src)
show("aucune donnee de salarie dans la reponse", not any(k in i for i in p["items"] for k in ("nom", "prenom", "matricule", "user_id")))
s, pa = prev("?%s&entite_id=%d" % (P, EA))
ids = [i["identifiant_interne"] for i in pa["items"]]
show("filtre entite A", s == 200 and sorted(ids) == ["ZZPV-ID-1", "ZZPV-ID-2"], ids)
show("filtre entite A : budget 2500,50", pa["total"]["montant"] == 2500.5 and pa["filtres"]["entite"] == "ZZPV-A", pa["total"])
s, r = prev("?entite_id=99999999")
show("entite inconnue : 404", s == 404, r)
s, r = prev("?du=2031-02-01&au=2031-01-01")
show("debut apres la fin : 422", s == 422, r)
s, r = prev("?du=2031-01-01&au=2037-01-01")
show("periode de plus de 60 mois : 422", s == 422, r)
s, pd = prev("")
show("sans parametre : 12 mois depuis le mois courant", s == 200 and pd["periode"]["du"] == TODAY.replace(day=1).isoformat() and len(pd["par_mois"]) == 12, pd.get("periode"))

print("== Suivi du renommage et de la suppression ==")
s, r = j("PUT", "/parametres/types/%d" % uid, {"nom": U + " 2", "actif": True})
j("PUT", "/parametres/couts", {"type": U + " 2", "montant": 200})
s, lst = j("GET", "/parametres/couts")
show("renommer un type : son cout le suit", any(c["type"] == U + " 2" for c in lst) and not any(c["type"] == U for c in lst))
s, p2 = prev("?" + P)
show("renommage : le materiel est chiffre", next(i for i in p2["items"] if i["identifiant_interne"] == "ZZPV-ID-4")["cout"] == 200.0)
s, r = j("DELETE", "/parametres/types/%d" % vid)
s, lst = j("GET", "/parametres/couts")
show("supprimer un type inutilise : ses couts partent avec lui", s == 200 and not any(c["type"] == V for c in lst))
s, b = call("DELETE", "/parametres/couts/%d" % cout_t, None, ADM)
show("suppression d'un cout", s == 204, b)
s, b = call("DELETE", "/parametres/couts/%d" % cout_t, None, ADM)
show("cout deja supprime : 404", s == 404, b)
j("PUT", "/parametres/couts", {"type": T, "montant": 1000})

print("== Droits et portee ==")
s, b = call("GET", "/previsions", None, None)
show("sans session : refuse", s in (401, 403), s)
s, r = account("sec_pv_ra", "rh", portee_globale=False, entites=[EA])
RA = login("sec_pv_ra", PW)
s, r = account("sec_pv_le", "lecture")
LE = login("sec_pv_le", PW)
s, r = prev("?" + P, RA)
ids = {i["identifiant_interne"] for i in r["items"]} if s == 200 else set()
show("RH limite a A : ne voit que A", s == 200 and {"ZZPV-ID-1", "ZZPV-ID-2"} <= ids and not ({"ZZPV-ID-3", "ZZPV-ID-4"} & ids), ids)
s, r = prev("?entite_id=%d" % EB, RA)
show("RH limite a A : entite B = 404", s == 404, r)
s, b = raw("/previsions?format=csv&" + P, RA)
show("RH limite a A : export sans B", s == 200 and b"ZZPV-ID-3" not in b and b"ZZPV-ID-1" in b, b[:60])
s, r = prev("?" + P, LE)
show("compte lecture : consultation autorisee", s == 200, s)
s, r = j("PUT", "/parametres/couts", {"type": T, "montant": 5}, LE)
show("compte lecture : modification des couts refusee", s == 403, r)
s, r = j("PUT", "/parametres/couts", {"type": T, "montant": 5}, RA)
show("compte RH : modification des couts refusee", s == 403, r)
s, r = j("GET", "/parametres/couts", None, RA)
show("compte RH : liste des couts refusee", s == 403, r)

print("== Exports ==")
s, lst = j("GET", "/parametres/couts")
j("DELETE", "/parametres/couts/%d" % next(c["id"] for c in lst if c["type"] == U + " 2"))
s, b = raw("/previsions?format=csv&" + P)
txt = b.decode("utf-8")
show("CSV : BOM, entete et separateur", s == 200 and b.startswith("\ufeffMois;Echeance;Entite".encode()), b[:40])
show("CSV : montant avec virgule decimale", "1500,50" in txt and "1000,00" in txt, txt[:200])
show("CSV : cout non renseigne laisse vide", "ZZPV-ID-4;;non renseigne" in txt, txt[-200:])
req = urllib.request.Request(B + "/previsions?format=csv", headers={"Authorization": "Bearer " + ADM})
r = urllib.request.urlopen(req, timeout=120)
show("CSV : type et nom de fichier", r.headers["Content-Type"].startswith("text/csv")
     and ("kikan-previsions-%s.csv" % TODAY) in r.headers["Content-Disposition"], r.headers["Content-Disposition"])
s, b = raw("/previsions?format=xlsx&" + P)
show("Excel : archive zip valide", s == 200 and b[:2] == b"PK", b[:8])
try:
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(b)).active
    cell = next(c for row in ws.iter_rows(min_row=2) if row[6].value == "ZZPV-ID-2" for c in [row[7]])
    show("Excel : cout en nombre (additionnable)", isinstance(cell.value, (int, float)) and cell.value == 1500.5, cell.value)
except Exception as e:
    show("Excel : lecture du classeur", False, e)
s, b = raw("/previsions?format=pdf&" + P)
show("PDF : fichier PDF", s == 200 and b[:5] == b"%PDF-", b[:8])
s, b = raw("/previsions?format=pdf")
show("PDF sans filtre", s == 200 and b[:5] == b"%PDF-")
s, b = raw("/previsions?format=exe")
show("format inconnu : 422", s == 422, b[:80])

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
