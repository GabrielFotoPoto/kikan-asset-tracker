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

"""Tests de l'autocompletion : recherche (casse et accents ignores), classement, graphie canonique, import.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/catalogue_check.py

Cree des donnees ZZCA et des comptes sec_ca* (nettoyage : tests/cleanup_test_data.sql). Fichier ASCII uniquement.
Code de sortie 1 si un test echoue.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")
from sqlmodel import Session  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Asset  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
E = chr(233)  # e accent aigu
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
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


def q(path, **params):
    return urllib.parse.quote(str(params.pop("_", "")), safe="") if False else path + "?" + urllib.parse.urlencode(params)


def marques(token=None, **params):
    s, r = j("GET", q("/assets/catalogue/marques", detail="true", **params), token=token)
    return r if s == 200 else (s, r)


def modeles(token=None, **params):
    s, r = j("GET", q("/assets/catalogue/modeles", detail="true", **params), token=token)
    return r if s == 200 else (s, r)


def names(items):
    return [i["nom"] for i in items]


def ensure_account(name, role):
    s, b = call("POST", "/auth/accounts", {"username": name, "password": PW, "role": role}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": PW}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


print("== Donnees historiques (inserees directement : le formulaire les normalise desormais) ==")
sn = [0]


def legacy(marque, modele, type_, n):
    with Session(engine) as ses:
        for _ in range(n):
            sn[0] += 1
            ses.add(Asset(marque=marque, modele=modele, type=type_, numero_serie=f"ZZCA-SN{sn[0]}", statut="stock"))
        ses.commit()


LENOVO = "ZZCA L" + E + "novo"
legacy("ZZCA Dell", "Latitude 5550", "ZZCA-Portable", 3)
legacy("ZZCA Dell", "latitude 5550", "ZZCA-Portable", 1)
legacy("ZZCA Dell", "Precision 3480", "ZZCA-Fixe", 2)
legacy("ZZCA Dell", "Pro T14", "ZZCA-Portable", 1)
legacy("zzca DELL", "Latitude 5550", "ZZCA-Portable", 1)
legacy(LENOVO, "ThinkPad T14", "ZZCA-Portable", 2)
legacy("ZZCA Asus", "Zen", "ZZCA-Portable", 1)
legacy("ZZCA Hp Inc", "Elite", "ZZCA-Fixe", 1)
legacy("ZZCA Alpha", "A1", None, 1)
legacy("Beta ZZCA Alpha", "B1", None, 9)
ids = [ensure_account("sec_cahr", "rh"), ensure_account("sec_calect", "lecture")]
RH, LECT = login("sec_cahr", PW), login("sec_calect", PW)
show("donnees de test et comptes prets", bool(RH and LECT))

print("== Recherche de marques ==")
r = marques(q="zzca", limit=50)
top = [x["nom"] for x in r if x["nom"] in ("ZZCA Dell", LENOVO, "ZZCA Asus", "ZZCA Hp Inc", "ZZCA Alpha", "Beta ZZCA Alpha")]
show("variantes regroupees sous la graphie la plus utilisee, effectifs cumules",
     {x["nom"]: x["count"] for x in r}.get("ZZCA Dell") == 8 and "zzca DELL" not in names(r), {x["nom"]: x["count"] for x in r if "ZZCA" in x["nom"].upper()})
show("commence par d'abord, puis contient (meme avec moins d'usage)", names(marques(q="zzca alpha", limit=5))[:2] == ["ZZCA Alpha", "Beta ZZCA Alpha"], names(marques(q="zzca alpha", limit=5)))
show("a egalite de rang : les plus utilisees d'abord", top.index("ZZCA Dell") < top.index(LENOVO) < top.index("ZZCA Asus"), top)
show("recherche sans accent trouve la marque accentuee", names(marques(q="zzca lenovo")) == [LENOVO], names(marques(q="zzca lenovo")))
show("recherche avec accent", names(marques(q="zzca l" + E + "novo")) == [LENOVO])
show("recherche insensible a la casse", names(marques(q="ZZCA LENOVO")) == [LENOVO])
show("recherche partielle (contient)", names(marques(q="hp inc")) == ["ZZCA Hp Inc"])
show("espaces multiples ignores dans la recherche", names(marques(q="zzca    dell")) == ["ZZCA Dell"])
show("limite respectee", len(marques(q="zzca", limit=2)) == 2)
show("limite invalide refusee (422)", j("GET", "/assets/catalogue/marques?limit=0")[0] == 422 and j("GET", "/assets/catalogue/marques?limit=51")[0] == 422)
s, plain = j("GET", "/assets/catalogue/marques?q=zzca+dell")
show("format simple conserve (liste de noms)", s == 200 and plain == ["ZZCA Dell"], plain)
show("sans recherche : les plus utilisees", len(marques(limit=3)) == 3 and marques(limit=3)[0]["count"] >= marques(limit=3)[2]["count"])
show("aucun resultat -> liste vide", marques(q="zzca-introuvable") == [])
show("recherche en caracteres speciaux sans erreur", isinstance(marques(q="%_'\"<>;--"), list))

print("== Recherche de modeles ==")
r = modeles(marque="zzca dell")
show("modeles d'une marque, casse ignoree, variantes de marque fusionnees", names(r) == ["Latitude 5550", "Precision 3480", "Pro T14"], r)
show("effectifs cumules sur les variantes", {x["nom"]: x["count"] for x in r}["Latitude 5550"] == 5)
show("le type classe en premier les modeles deja vus avec lui", names(modeles(marque="zzca dell", type="zzca-fixe"))[0] == "Precision 3480", names(modeles(marque="zzca dell", type="zzca-fixe")))
show("le type n'exclut rien (simple classement)", len(modeles(marque="zzca dell", type="zzca-fixe")) == 3)
show("recherche partielle sur le modele", names(modeles(marque="zzca dell", q="LATITUDE")) == ["Latitude 5550"] and names(modeles(marque="zzca dell", q="5550")) == ["Latitude 5550"])
show("recherche 'contient'", names(modeles(marque="zzca dell", q="t14")) == ["Pro T14"])
show("une autre marque ne voit pas ces modeles", names(modeles(marque="zzca asus")) == ["Zen"])
show("marque saisie sans accent", names(modeles(marque="zzca lenovo")) == ["ThinkPad T14"] and names(modeles(marque=LENOVO)) == ["ThinkPad T14"])
show("marque inconnue -> liste vide", modeles(marque="zzca-introuvable") == [])
s, plain = j("GET", "/assets/catalogue/modeles?marque=zzca+asus")
show("format simple conserve (liste de noms)", s == 200 and plain == ["Zen"], plain)

print("== Roles ==")
show("lecture seule : suggestions lisibles", isinstance(marques(token=LECT, q="zzca"), list) and isinstance(modeles(token=RH, marque="zzca dell"), list))
show("sans jeton : refuse (401)", call("GET", "/assets/catalogue/marques")[0] == 401 and call("GET", "/assets/catalogue/modeles")[0] == 401)

print("== Graphie canonique a l'enregistrement ==")
def create(**kw):
    sn[0] += 1
    s, r = j("POST", "/assets", {"statut": "stock", "numero_serie": f"ZZCA-SN{sn[0]}", "type": "ZZCA-Portable", **kw})
    return r if s == 201 else (s, r)


a = create(marque="  zzca   DELL  ", modele="LATITUDE   5550")
show("marque et modele ramenes a la graphie la plus utilisee", (a["marque"], a["modele"]) == ("ZZCA Dell", "Latitude 5550"), (a["marque"], a["modele"]) if isinstance(a, dict) else a)
a = create(marque="zzca lenovo", modele="thinkpad t14")
show("accents retrouves (marque saisie sans accent)", (a["marque"], a["modele"]) == (LENOVO, "ThinkPad T14"), a if not isinstance(a, dict) else (a["marque"], a["modele"]))
a1 = create(marque="  ZZCA   Nouvelle ", modele="  Mod   X ")
show("valeur inedite : acceptee, espaces nettoyes", (a1["marque"], a1["modele"]) == ("ZZCA Nouvelle", "Mod X"))
a2 = create(marque="zzca NOUVELLE", modele="MOD x")
show("la valeur inedite sert ensuite de reference", (a2["marque"], a2["modele"]) == ("ZZCA Nouvelle", "Mod X"), (a2["marque"], a2["modele"]))
a = create(marque="ZZCA Asus", modele="LATITUDE 5550")
show("modeles propres a chaque marque (pas de fusion entre marques)", a["modele"] == "LATITUDE 5550", a["modele"])
a = create(marque="ZZCA Dell", modele="Pro T-14")
show("la ponctuation reste significative (T-14 et T14 distincts)", a["modele"] == "Pro T-14", a["modele"])
a = create(marque="   ", modele="")
show("valeurs vides -> aucune", a["marque"] is None and a["modele"] is None)
b = create(marque="ZZCA Hp Inc", modele="Elite", type="ZZCA-Fixe")
s, up = j("PUT", f"/assets/{b['id']}", {**{k: b[k] for k in ("identifiant_interne", "type", "numero_serie", "statut", "entite_id", "notes", "date_achat", "fin_garantie", "echeance_renouvellement", "source", "id_externe")},
                                          "marque": "zzca hp inc", "modele": "ELITE"})
show("modification : meme normalisation", s == 200 and (up["marque"], up["modele"]) == ("ZZCA Hp Inc", "Elite"), (s, up if s != 200 else (up["marque"], up["modele"])))
s, allr = j("GET", "/assets")
show("donnees historiques inchangees (aucune reecriture)", any(x["marque"] == "zzca DELL" for x in allr) and any(x["modele"] == "latitude 5550" for x in allr))
r = marques(q="zzca nouvelle")
show("catalogue mis a jour par les saisies", names(r) == ["ZZCA Nouvelle"] and r[0]["count"] == 2, r)

print("== Import ==")
def post_import(content, query=""):
    bd = "----kikanCA"
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\nContent-Type: text/csv\r\n\r\n').encode() + content + f"\r\n--{bd}--\r\n".encode()
    s, b = call("POST", f"/import/materiel{query}", token=ADM, raw=body, ctype="multipart/form-data; boundary=" + bd)
    return json.loads(b)


csv_mat = ("identifiant_interne;type;marque;modele;numero_serie;statut\n"
           "ZZCA-I1;ZZCA-Portable;ZZCA Imp Brand;Modele  Un;ZZCA-IS1;stock\n"
           "ZZCA-I2;ZZCA-Portable;zzca imp brand;MODELE UN;ZZCA-IS2;stock\n"
           "ZZCA-I3;ZZCA-Portable;ZZCA IMP BRAND;modele deux;ZZCA-IS3;stock\n"
           "ZZCA-I4;ZZCA-Portable;zzca dell;latitude 5550;ZZCA-IS4;stock\n").encode()
r = post_import(csv_mat, "?dry_run=true")
show("simulation : 4 lignes valides", r["imported"] == 4 and r["errors_total"] == 0, r["errors"])
show("simulation : aucune marque ajoutee au catalogue", marques(q="zzca imp brand") == [])
r = post_import(csv_mat)
show("import reel", r["imported"] == 4)
s, allr = j("GET", "/assets?statut=stock")
imp = {x["identifiant_interne"]: x for x in allr if (x.get("identifiant_interne") or "").startswith("ZZCA-I")}
show("import : variantes du fichier regroupees sous la premiere graphie", {imp[k]["marque"] for k in ("ZZCA-I1", "ZZCA-I2", "ZZCA-I3")} == {"ZZCA Imp Brand"}, {imp[k]["marque"] for k in ("ZZCA-I1", "ZZCA-I2", "ZZCA-I3")})
show("import : modeles regroupes et espaces nettoyes", {imp["ZZCA-I1"]["modele"], imp["ZZCA-I2"]["modele"]} == {"Modele Un"}, (imp["ZZCA-I1"]["modele"], imp["ZZCA-I2"]["modele"]))
show("import : une marque existante reprend sa graphie", (imp["ZZCA-I4"]["marque"], imp["ZZCA-I4"]["modele"]) == ("ZZCA Dell", "Latitude 5550"))

for aid in ids:
    call("PUT", f"/auth/accounts/{aid}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
