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

"""API d'integration par jetons (B5) : jetons, droits, perimetre, idempotence, liaison, conflits, simulation, debit.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/api_check.py

Cree des donnees ZZAP, des comptes sec_ap* et des jetons ZZ* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1
si un test echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "/app")

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
SRC = "zzapi"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


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


def make_token(nom, droits, **kw):
    body = {"nom": nom, "source": SRC, "droits": droits, "portee_globale": True, "jours": 30, **kw}
    s, r = j("POST", "/integrations/tokens", body)
    return s, r


print("== Preparation ==")
ent = {}
for code in ("ZZAP-A", "ZZAP-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZAP-A"], ent["ZZAP-B"]
for name, role in (("sec_ap_rh", "rh"), ("sec_ap_lec", "lecture")):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True})
RH, LEC = login("sec_ap_rh", PW), login("sec_ap_lec", PW)
j("POST", "/parametres/types", {"nom": "ZZAP portable"})
show("comptes de test", bool(RH and LEC))

print("== Administration des jetons ==")
s, r = make_token("ZZ jeton complet", ["assets_lecture", "assets_ecriture", "users_lecture", "users_ecriture"])
show("creation d'un jeton global", s == 201 and r["jeton"].startswith("kik_") and len(r["jeton"]) > 40, r)
FULL, FULL_ID = r["jeton"], r["id"]
show("le prefixe affiche est le debut du jeton, pas le jeton", r["prefixe"] == FULL[:8] and r["prefixe"] != FULL)
s, rows = j("GET", "/integrations/tokens")
mine = next(x for x in rows if x["id"] == FULL_ID)
show("la liste ne contient jamais le jeton", FULL not in json.dumps(rows) and "token_hash" not in json.dumps(rows) and "jeton" not in mine, mine)
from sqlmodel import Session, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import ApiToken  # noqa: E402

with Session(engine) as s_:
    row = s_.exec(select(ApiToken).where(ApiToken.id == FULL_ID)).one()
    show("en base : seulement l'empreinte (le jeton n'y figure pas)", FULL not in json.dumps(row.model_dump(), default=str) and len(row.token_hash) == 64)
for name, payload, codes in [
    ("nom trop court", {"nom": "ab", "droits": ["assets_lecture"], "portee_globale": True}, (422,)),
    ("droit inconnu", {"nom": "ZZ x", "droits": ["tout"], "portee_globale": True}, (422,)),
    ("aucun droit", {"nom": "ZZ x", "droits": [], "portee_globale": True}, (422,)),
    ("global avec entites", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": True, "entites": [EA]}, (400,)),
    ("ni global ni entite", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": False}, (400,)),
    ("entite inconnue", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": False, "entites": [999999]}, (400,)),
    ("duree 0 jour", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": True, "jours": 0}, (422,)),
    ("duree 731 jours", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": True, "jours": 731}, (422,)),
    ("source invalide", {"nom": "ZZ x", "droits": ["assets_lecture"], "portee_globale": True, "source": "Glpi Prod"}, (422,)),
]:
    s, r = j("POST", "/integrations/tokens", payload)
    show("refuse : " + name, s in codes, s)
for who, tok in (("RH", RH), ("lecture", LEC)):
    for method, path in (("GET", "/integrations/tokens"), ("POST", "/integrations/tokens"), ("POST", "/integrations/tokens/1/revoquer")):
        s, r = j(method, path, {} if method == "POST" else None, token=tok)
        show("%s %s refuse a un compte %s" % (method, path, who), s == 403, s)

print("== Authentification de l'API ==")
for name, tok in [("sans jeton", None), ("jeton de session (JWT)", ADM), ("jeton inconnu", "kik_" + "x" * 43), ("jeton mal forme", "abc")]:
    s, r = j("GET", "/v1/me", token=tok)
    show("/v1/me refuse : " + name, s == 401, s)
s, r = j("GET", "/v1/me", token=FULL)
show("/v1/me avec un jeton valide", s == 200 and r["nom"] == "ZZ jeton complet" and r["perimetre"] == "global", r)
for path in ("/users", "/assets", "/auth/accounts", "/stats", "/integrations/tokens"):
    s, r = j("GET", path, token=FULL)
    show("le jeton d'API n'ouvre pas %s" % path, s == 401, s)
s, r = make_token("ZZ jeton lecture", ["assets_lecture", "users_lecture"])
RO = r["jeton"]
s, r = j("PUT", "/v1/assets/ZZ-1", {"id_externe": "ZZ-1", "type": "ZZAP portable"}, token=RO)
show("jeton en lecture seule : ecriture refusee", s == 403, r)
s, r = j("GET", "/v1/assets", token=RO)
show("jeton en lecture seule : lecture permise", s == 200)
s, r = make_token("ZZ jeton users", ["users_ecriture"])
USR = r["jeton"]
s, r = j("GET", "/v1/assets", token=USR)
show("un droit n'en donne pas un autre (users_ecriture ne lit pas le materiel)", s == 403, r)
s, r = make_token("ZZ jeton a revoquer", ["assets_lecture"])
REV, REV_ID = r["jeton"], r["id"]
s, r = j("POST", "/integrations/tokens/%d/revoquer" % REV_ID)
show("revocation", s == 200 and r["actif"] is False)
s, r = j("GET", "/v1/me", token=REV)
show("un jeton revoque est refuse", s == 401)
s, r = make_token("ZZ jeton expire", ["assets_lecture"])
EXP = r["jeton"]
with Session(engine) as s_:
    t = s_.exec(select(ApiToken).where(ApiToken.id == r["id"])).one()
    t.expire_le = date.today() - timedelta(days=1)
    s_.add(t)
    s_.commit()
s, r = j("GET", "/v1/me", token=EXP)
show("un jeton expire est refuse", s == 401)
s, r = j("GET", "/integrations/tokens")
used = next(x for x in r if x["id"] == FULL_ID)
show("derniere utilisation et compteur mis a jour", used["derniere_utilisation"] and used["utilisations"] >= 1, used)

print("== Materiel : creation, liaison, mises a jour ==")
asset = {"type": "zzap PORTABLE", "marque": "ZZAP", "modele": "X1", "numero_serie": "ZZAP-SN-1", "identifiant_interne": "ZZAP-ID-1",
         "entite_code": "ZZAP-A", "notes": "importe"}
s, r = j("PUT", "/v1/assets/A-100", asset, token=FULL)
show("creation d'un materiel", s == 200 and r["resultat"] == "cree" and r["id"], r)
AID = r["id"]
s, a = j("GET", "/assets/%d" % AID)
show("en stock, source et identifiant externe, type canonique", a["statut"] == "stock" and a["source"] == SRC and a["id_externe"] == "A-100"
     and a["type"] == "ZZAP portable", a)
s, r = j("PUT", "/v1/assets/A-100", asset, token=FULL)
show("meme appel : idempotent (inchange)", r["resultat"] == "inchange" and r["id"] == AID, r)
s, r = j("PUT", "/v1/assets/A-100", {**asset, "modele": "X2"}, token=FULL)
show("changement de modele : modifie", r["resultat"] == "modifie" and j("GET", "/assets/%d" % AID)[1]["modele"] == "X2", r)
j("PUT", "/assets/%d" % AID, {**{k: a[k] for k in ("type", "marque", "numero_serie", "identifiant_interne", "entite_id", "statut", "source", "id_externe")},
                              "modele": "X2", "notes": "corrige a la main"})
s, r = j("PUT", "/v1/assets/A-100", {**asset, "modele": "X3"}, token=FULL)
show("modifie a la main dans Kikan : conflit, rien d'ecrase", r["resultat"] == "conflit" and j("GET", "/assets/%d" % AID)[1]["modele"] == "X2", r)
s, r = j("PUT", "/v1/assets/A-101", {**asset, "identifiant_interne": "ZZAP-ID-2"}, token=FULL)
show("meme numero de serie deja lie a un autre identifiant externe : conflit", r["resultat"] == "conflit", r)
s, m = j("POST", "/assets", {"type": "ZZAP portable", "marque": "ZZAP", "modele": "M9", "numero_serie": "ZZAP-SN-MANUEL",
                             "identifiant_interne": "ZZAP-ID-M", "entite_id": EA})
s, r = j("PUT", "/v1/assets/A-200", {"type": "ZZAP portable", "marque": "Autre", "modele": "Z", "numero_serie": "zzap-sn-manuel", "entite_code": "ZZAP-A"}, token=FULL)
show("materiel deja connu (meme numero de serie, casse differente) : lie sans modification", r["resultat"] == "lie" and r["id"] == m["id"], r)
s, a2 = j("GET", "/assets/%d" % m["id"])
show("le materiel existant n'a pas ete modifie", a2["marque"] == "ZZAP" and a2["modele"] == "M9" and a2["source"] == "manuel", a2)
s, u0 = j("POST", "/users", {"matricule": "ZZAP-U0", "nom": "NomU0", "prenom": "ZZAPu0", "entite_id": EA})
j("POST", "/assignments", {"user_id": u0["id"], "asset_ids": [AID]})
s, r = j("PUT", "/v1/assets/A-100", {**asset, "modele": "X2", "type": "ZZAP portable", "echeance_renouvellement": "2030-01-01"}, token=FULL)
s, a3 = j("GET", "/assets/%d" % AID)
show("un materiel affecte garde son statut (affecte)", a3["statut"] == "affecte", a3["statut"])
s, r = j("PUT", "/v1/assets/A-300", {**asset, "numero_serie": "ZZAP-SN-3"}, token=FULL)
show("identifiant interne deja utilise : refuse", r["resultat"] == "refuse", r)
s, r = j("PUT", "/v1/assets/A-301", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-4", "entite_code": "ZZAP-NOPE"}, token=FULL)
show("entite inconnue : refuse", r["resultat"] == "refuse", r)
s, r = j("PUT", "/v1/assets/A-302", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-5", "bidon": 1}, token=FULL)
show("champ inconnu -> 422", s == 422)
s, r = j("PUT", "/v1/assets/A-303", {"type": "", "numero_serie": "ZZAP-SN-6"}, token=FULL)
show("type vide -> 422", s == 422)
s, r = j("PUT", "/v1/assets/A-304", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-7\r\nX", "notes": "a\x00b"}, token=FULL)
show("sauts de ligne et caracteres de controle nettoyes", s == 200 and r["resultat"] == "cree" and
     j("GET", "/assets/%d" % r["id"])[1]["numero_serie"] == "ZZAP-SN-7 X", r)

print("== Simulation et lots ==")
n_before = len(j("GET", "/assets")[1])
s, r = j("PUT", "/v1/assets/A-400?dry_run=1", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-400", "entite_code": "ZZAP-A"}, token=FULL)
show("simulation : annonce la creation sans rien ecrire", r["resultat"] == "cree" and r["id"] is None and len(j("GET", "/assets")[1]) == n_before, r)
s, r = j("POST", "/v1/assets/_batch?dry_run=1", {"items": [{"id_externe": "B1", "type": "ZZAP portable", "numero_serie": "ZZAP-SN-B1", "entite_code": "ZZAP-A"},
                                                          {"id_externe": "B2", "type": "ZZAP portable", "numero_serie": "ZZAP-SN-B2", "entite_code": "ZZAP-A"}]}, token=FULL)
show("lot simule : resume", r["simulation"] is True and r["resume"] == {"cree": 2} and len(j("GET", "/assets")[1]) == n_before, r)
s, r = j("POST", "/v1/assets/_batch", {"items": [{"id_externe": "B1", "type": "ZZAP portable", "numero_serie": "ZZAP-SN-B1", "entite_code": "ZZAP-A"},
                                                {"id_externe": "B2", "type": "ZZAP portable", "numero_serie": "ZZAP-SN-B2", "entite_code": "ZZAP-NOPE"},
                                                {"id_externe": "B3", "type": "ZZAP portable", "numero_serie": "ZZAP-SN-B3", "entite_code": "ZZAP-B"}]}, token=FULL)
show("lot reel : un element refuse n'arrete pas les autres", r["resume"] == {"cree": 2, "refuse": 1}, r)
s, r = j("POST", "/v1/assets/_batch", {"items": [{"id_externe": str(i), "type": "ZZAP portable"} for i in range(101)]}, token=FULL)
show("lot de plus de 100 elements -> 422", s == 422)
s, r = j("POST", "/v1/assets/_batch", {"items": []}, token=FULL)
show("lot vide -> 422", s == 422)

print("== Perimetre d'un jeton ==")
s, r = make_token("ZZ jeton entite A", ["assets_lecture", "assets_ecriture", "users_lecture", "users_ecriture"], portee_globale=False, entites=[EA])
TA = r["jeton"]
s, r = j("GET", "/v1/me", token=TA)
show("/v1/me : perimetre = entite A", r["perimetre"] == ["ZZAP-A"], r)
s, r = j("PUT", "/v1/assets/S-1", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-S1", "entite_code": "ZZAP-A"}, token=TA)
show("jeton limite : ecriture dans son entite", r["resultat"] == "cree", r)
s, r = j("PUT", "/v1/assets/S-2", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-S2", "entite_code": "ZZAP-B"}, token=TA)
show("jeton limite : entite hors perimetre refusee", r["resultat"] == "refuse", r)
s, r = j("PUT", "/v1/assets/S-3", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-S3"}, token=TA)
show("jeton limite : entite obligatoire", r["resultat"] == "refuse", r)
s, b_asset = j("PUT", "/v1/assets/B-OUT", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-OUT", "entite_code": "ZZAP-B"}, token=FULL)
s, r = j("PUT", "/v1/assets/B-OUT", {"type": "ZZAP portable", "numero_serie": "ZZAP-SN-OUT", "entite_code": "ZZAP-A"}, token=TA)
show("jeton limite : un element hors perimetre n'est ni modifie ni revele", r["resultat"] == "refuse", r)
s, r = j("PUT", "/v1/assets/NEW-OUT", {"type": "ZZAP portable", "numero_serie": "zzap-sn-out", "entite_code": "ZZAP-A"}, token=TA)
show("jeton limite : correspondance hors perimetre refusee", r["resultat"] == "refuse", r)
s, rows = j("GET", "/v1/assets?limit=500", token=TA)
sns = {x["numero_serie"] for x in rows}
show("lecture limitee au perimetre", "ZZAP-SN-S1" in sns and "ZZAP-SN-OUT" not in sns and "ZZAP-SN-1" in sns, len(rows))
s, rows = j("GET", "/v1/assets?limit=501", token=TA)
show("limite de page > 500 -> 422", s == 422)

print("== Salaries ==")
u = {"id_externe": "U-1", "matricule": "ZZAP-M1", "nom": "Dupont", "prenom": "ZZAPjean", "email": "zzap.jean@exemple.test", "service": "ZZAP service",
     "entite_code": "ZZAP-A"}
s, r = j("PUT", "/v1/users/U-1", u, token=FULL)
show("creation d'un salarie (actif)", r["resultat"] == "cree", r)
UID = r["id"]
s, usr = j("GET", "/users/%d" % UID)
show("statut actif, entite et service", usr["statut"] == "actif" and usr["entite_id"] == EA and usr["service"] == "ZZAP service", usr)
s, r = j("PUT", "/v1/users/U-1", u, token=FULL)
show("meme appel : idempotent", r["resultat"] == "inchange", r)
future = (date.today() + timedelta(days=20)).isoformat()
s, r = j("PUT", "/v1/users/U-2", {"nom": "Martin", "prenom": "ZZAPmarie", "date_arrivee": future, "entite_code": "ZZAP-A"}, token=FULL)
show("arrivee future : statut prevu", r["resultat"] == "cree" and j("GET", "/users/%d" % r["id"])[1]["statut"] == "prevu", r)
s, r = j("PUT", "/v1/users/U-3", {"matricule": "ZZAP-M1", "nom": "AUTRE", "prenom": "AUTRE", "entite_code": "ZZAP-A"}, token=FULL)
show("un salarie deja lie a un autre identifiant externe : conflit, pas de seconde liaison", r["resultat"] == "conflit" and r["id"] == UID, r)
s, m9 = j("POST", "/users", {"matricule": "ZZAP-M9", "nom": "Durand", "prenom": "ZZAPm9", "entite_id": EA})
s, r = j("PUT", "/v1/users/U-4", {"matricule": "ZZAP-M9", "nom": "AUTRE", "prenom": "AUTRE", "email": "zzap.m9@exemple.test", "entite_code": "ZZAP-A"}, token=FULL)
show("meme matricule qu'une fiche existante : liee, pas dupliquee", r["resultat"] == "lie" and r["id"] == m9["id"], r)
fm9 = j("GET", "/users/%d" % m9["id"])[1]
show("jamais d'ecrasement : nom et prenom conserves, e-mail vide complete, differences signalees",
     fm9["nom"] == "Durand" and fm9["prenom"] == "ZZAPm9" and fm9["email"] == "zzap.m9@exemple.test" and set(r.get("champs_ignores", [])) >= {"nom", "prenom"}, r)
s, e0 = j("POST", "/users", {"matricule": "ZZAP-M5", "nom": "Vide", "prenom": "ZZAPvide", "entite_id": EA})
s, r = j("PUT", "/v1/users/U-5", {"matricule": "ZZAP-M5", "nom": "Vide", "prenom": "ZZAPvide", "email": "zzap.vide@exemple.test", "service": "ZZAP service"}, token=FULL)
show("les champs vides d'une fiche sont completes (e-mail, service)", r["resultat"] == "lie" and j("GET", "/users/%d" % e0["id"])[1]["email"] == "zzap.vide@exemple.test", r)
s, h0 = j("POST", "/users", {"matricule": "ZZAP-H0", "nom": "Homonyme", "prenom": "ZZAPhomo", "entite_id": EA})
s, r = j("PUT", "/v1/users/U-6", {"nom": "Homonyme", "prenom": "ZZAPhomo", "entite_code": "ZZAP-A"}, token=FULL)
show("homonyme : conflit tant que la decision n'est pas explicite", r["resultat"] == "conflit" and r["id"] == h0["id"], r)
s, r = j("PUT", "/v1/users/U-7", {"nom": "Homonyme", "prenom": "ZZAPhomo", "entite_code": "ZZAP-A", "homonyme": "lier"}, token=FULL)
show("homonyme = lier : rattache a la fiche existante", r["resultat"] == "lie" and r["id"] == h0["id"], r)
s, r = j("PUT", "/v1/users/U-12", {"nom": "Homonyme", "prenom": "ZZAPhomo", "entite_code": "ZZAP-A", "homonyme": "creer"}, token=FULL)
show("homonyme = creer : nouvelle fiche", r["resultat"] == "cree" and r["id"] != h0["id"], r)
s, r = j("PUT", "/v1/users/U-8", {"nom": "", "prenom": "", "entite_code": "ZZAP-A"}, token=FULL)
show("nom et prenom requis pour creer", r["resultat"] == "refuse", r)
s, r = j("PUT", "/v1/users/U-9", {"nom": "Hors", "prenom": "ZZAPhors", "entite_code": "ZZAP-B"}, token=TA)
show("jeton limite : salarie d'une autre entite refuse", r["resultat"] == "refuse", r)
s, mb = j("POST", "/users", {"matricule": "ZZAP-MB", "nom": "EnB", "prenom": "ZZAPenb", "entite_id": EB})
s, r = j("PUT", "/v1/users/U-10", {"matricule": "ZZAP-MB", "nom": "X", "prenom": "Y", "entite_code": "ZZAP-A"}, token=TA)
show("jeton limite : un salarie existant d'une autre entite est refuse, sans etre revele ni lie", r["resultat"] == "refuse" and r["id"] is None, r)
s, rows = j("GET", "/v1/users", token=TA)
show("lecture des salaries limitee au perimetre", all(x["entite_code"] == "ZZAP-A" for x in rows) and len(rows) >= 2, len(rows))
s, r = j("PUT", "/v1/users/U-11", {"nom": "Seul", "prenom": "ZZAPseul", "entite_code": "ZZAP-A", "inconnu": 1}, token=FULL)
show("champ inconnu -> 422", s == 422)
s, r = j("POST", "/v1/users/_batch?dry_run=1", {"items": [{"id_externe": "L1", "nom": "Lot", "prenom": "ZZAPlot1", "entite_code": "ZZAP-A"}]}, token=FULL)
n = len([x for x in j("GET", "/users")[1] if x["prenom"] == "ZZAPlot1"])
show("simulation de lot de salaries : rien d'ecrit", r["resume"] == {"cree": 1} and n == 0, r)

print("== Audit et fuites ==")
s, rows = j("GET", "/audit?limit=500")
rows = rows if isinstance(rows, list) else rows.get("items", [])
actions = {r.get("action") for r in rows}
show("creations, revocations et imports journalises", {"jeton_api_cree", "jeton_api_revoque", "api_assets_import", "api_assets_simulation", "api_users_import"} <= actions,
     sorted(a for a in actions if a and (a.startswith("api") or a.startswith("jeton"))))
show("l'acteur des imports est le nom du jeton", any(r.get("actor") == "api:ZZ jeton complet" for r in rows))
show("aucun jeton dans le journal", all("kik_" not in json.dumps(r) for r in rows))

print("== Limitation de debit ==")
s, r = make_token("ZZ jeton debit", ["assets_lecture"])
RATE = r["jeton"]
codes = [call("GET", "/v1/me", token=RATE)[0] for _ in range(305)]
show("au-dela de 300 requetes par minute : 429", codes[:300].count(200) == 300 and 429 in codes[300:], (codes.count(200), codes.count(429)))
s, r = j("GET", "/v1/me", token=FULL)
show("la limite est propre a chaque jeton", s == 200)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
