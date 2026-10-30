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

"""Echange de materiel (renouvellement) : remise du nouveau materiel et restitution de l'ancien, un seul document signe.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/echange_check.py

Cree des donnees ZZEC et des comptes sec_ec* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
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


import base64
import io
import re
import threading
import uuid
from datetime import date

from PIL import Image, ImageDraw
from pypdf import PdfReader

TODAY = date.today()
NOM_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_[A-Z0-9-]+_[A-Z0-9-]+_[A-Z]{3}_\d{3}(-\d+)?\.pdf$")


def sig_image():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)], fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIG = sig_image()


def raw(method, path, body=None, token=None):
    return call(method, path, body, token or ADM)


def account(name, role):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True})
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, "portee_globale": True})


def upload(path, fields, token):
    bnd = uuid.uuid4().hex
    parts = ["--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bnd, k, v) for k, v in fields.items()]
    body = "".join(parts).encode() + ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"c.md\"\r\nContent-Type: text/markdown\r\n\r\n"
                                       "# Charte ZZEC\n\nTexte de test.\r\n--%s--\r\n" % (bnd, bnd)).encode()
    req = urllib.request.Request(B + path, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + bnd})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def new_asset(cle, type_="ZZEC portable", eid=None):
    s, r = j("POST", "/assets", {"type": type_, "marque": "ZZEC", "modele": "M" + cle, "numero_serie": "ZZEC-SN-" + cle,
                                 "identifiant_interne": "ZZEC-ID-" + cle, "entite_id": eid})
    return r


def statut(asset):
    return j("GET", "/assets/%d" % asset["id"])[1]["statut"]


def echange(user, nouveaux, anciens, token=None, **extra):
    body = {"user_id": user["id"], "nouveaux_ids": [a["id"] for a in nouveaux],
            "anciens": [{"asset_id": a["id"], "destination": d} for a, d in anciens],
            "consent": True, "signature_image": SIG, "strokes": 4, "duration_ms": 2500, **extra}
    return j("POST", "/assignments/echange", body, token)


def pdf_text(assignment_id, type_="echange"):
    s, b = raw("GET", "/assignments/%d/document?type=%s" % (assignment_id, type_))
    return s, b, "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(b)).pages) if s == 200 else ""


print("== Preparation ==")
ent = {}
for code in ("ZZEC-A", "ZZEC-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZEC-A"], ent["ZZEC-B"]
account("sec_ec_rh", "rh")
account("sec_ec_le", "lecture")
RH, LE = login("sec_ec_rh", PW), login("sec_ec_le", PW)
j("POST", "/parametres/types", {"nom": "ZZEC portable"})
j("POST", "/parametres/types", {"nom": "ZZEC telephone"})

def new_user(cle, eid, statut_="actif"):
    s, r = j("POST", "/users", {"matricule": "ZZEC-" + cle, "nom": "ZZEC" + cle, "prenom": "Zz" + cle, "entite_id": eid, "statut": statut_,
                                "date_arrivee": str(TODAY)})
    return r

U1, U2, U4 = new_user("1", EA), new_user("2", EA, "prevu"), new_user("4", EB)
show("salaries crees", all("id" in u for u in (U1, U2, U4)), (U1, U2, U4))
P1, S1, P2 = new_asset("P1", eid=EA), new_asset("S1", "ZZEC telephone", EA), new_asset("P2", eid=EA)
N1, N2, N3, N4, N5 = (new_asset("N%d" % i, eid=EA) for i in range(1, 6))
X1 = new_asset("X1", eid=EB)
REF = new_asset("REF", eid=EA)
j("PUT", "/assets/%d" % REF["id"], {**REF, "statut": "reforme"})
show("materiel cree", all("id" in a for a in (P1, S1, P2, N1, N2, N3, N4, N5, X1, REF)))

# Situation de depart : U1 detient P1 + S1 (affectation A1) et P2 (A2) ; U4 detient X1.
s, A1 = j("POST", "/assignments", {"user_id": U1["id"], "asset_ids": [P1["id"], S1["id"]], "sans_charte": True})
s, A2 = j("POST", "/assignments", {"user_id": U1["id"], "asset_ids": [P2["id"]], "sans_charte": True})
s, A4 = j("POST", "/assignments", {"user_id": U4["id"], "asset_ids": [X1["id"]], "sans_charte": True})
show("remises de depart creees", all("id" in a for a in (A1, A2, A4)), (A1, A2))
for a in (A1, A2, A4):
    j("POST", "/assignments/%d/sign" % a["id"], {"consent": True, "signature_image": SIG})

print("== Droits ==")
s, r = echange(U1, [N1], [(P1, "rendu")], RH)
show("RH : echange refuse", s == 403, r)
s, r = echange(U1, [N1], [(P1, "rendu")], LE)
show("lecture : echange refuse", s == 403, r)
s, b = call("POST", "/assignments/echange", {}, None)
show("sans session : refuse", s in (401, 403), s)
s, r = j("GET", "/assignments/echange/recap?user_id=%d" % U1["id"], None, RH)
show("RH : ecran d'echange refuse", s == 403, r)
s, r = j("GET", "/assignments/detenteur/%d" % P1["id"], None, RH)
show("RH : detenteur d'un materiel refuse", s == 403, r)

print("== Validations (rien ne change en cas de refus) ==")
def inchange():
    return statut(P1) == "affecte" and statut(S1) == "affecte" and statut(N1) == "stock" and statut(N2) == "stock"

s, r = echange(U2, [N1], [(P1, "rendu")])
show("salarie pas encore en poste (prevu) : 409", s == 409, r)
s, r = j("POST", "/assignments/echange", {"user_id": 99999999, "nouveaux_ids": [N1["id"]], "anciens": [{"asset_id": P1["id"]}], "consent": True, "signature_image": SIG})
show("salarie inconnu : 404", s == 404, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [], "anciens": [{"asset_id": P1["id"]}]})
show("aucun nouveau materiel : 422", s == 422, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [N1["id"]], "anciens": []})
show("aucun ancien materiel : 422", s == 422, r)
s, r = echange(U1, [P1], [(P1, "rendu")])
show("meme materiel remis et restitue : 400", s == 400, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [N1["id"]], "consent": True, "signature_image": SIG,
                                          "anciens": [{"asset_id": P1["id"], "destination": "rendu"}, {"asset_id": P1["id"], "destination": "stock"}]})
show("deux devenirs pour un meme materiel : 400", s == 400, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [N1["id"]], "consent": True, "signature_image": SIG,
                                          "anciens": [{"asset_id": P1["id"], "destination": "poubelle"}]})
show("devenir inconnu : 422", s == 422, r)
s, r = echange(U1, [N1], [(N2, "rendu")])
show("ancien materiel qui n'est pas detenu (en stock) : 409", s == 409, r)
s, r = echange(U1, [N1], [(X1, "rendu")])
show("ancien materiel detenu par un autre salarie : 409", s == 409, r)
s, r = echange(U1, [P2], [(P1, "rendu")])
show("nouveau materiel deja affecte : 409", s == 409, r)
s, r = echange(U1, [REF], [(P1, "rendu")])
show("nouveau materiel reforme : 409", s == 409, r)
s, r = echange(U1, [{"id": 99999999}], [(P1, "rendu")])
show("nouveau materiel inconnu : 404", s == 404, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [N1["id"]], "anciens": [{"asset_id": P1["id"]}], "signature_image": SIG})
show("sans consentement : 400", s == 400, r)
s, r = j("POST", "/assignments/echange", {"user_id": U1["id"], "nouveaux_ids": [N1["id"]], "anciens": [{"asset_id": P1["id"]}], "consent": True})
show("sans signature manuscrite : 400", s == 400, r)
s, r = echange(U1, [N1], [(P1, "rendu")], besoin_ids=[999999])
show("besoin inconnu : 400", s == 400, r)
s, r = echange(U1, [N1], [(P1, "rendu")], joindre_charte=True, policy_id=999999)
show("charte inconnue : 400", s == 400, r)
show("apres tous les refus : aucun statut n'a change", inchange())

print("== Preparation de l'ecran ==")
s, rc = j("GET", "/assignments/echange/recap?user_id=%d" % U1["id"])
show("ecran : materiel detenu (P1, S1, P2)", s == 200 and {a["id"] for a in rc["detenus"]} == {P1["id"], S1["id"], P2["id"]}, rc.get("detenus"))
show("ecran : salarie, charte, acces, besoins", rc["salarie"]["id"] == U1["id"] and "charte" in rc and "acces_remise" in rc and rc["besoins"] == [], list(rc))
s, r = j("GET", "/assignments/echange/recap?user_id=99999999")
show("ecran : salarie inconnu : 404", s == 404, r)
s, r = j("GET", "/assignments/detenteur/%d" % P1["id"])
show("detenteur de P1 : U1", s == 200 and r["user_id"] == U1["id"], r)
s, r = j("GET", "/assignments/detenteur/%d" % N1["id"])
show("materiel en stock : aucun detenteur (404)", s == 404, r)

print("== Echange partiel : P1 reformee, remplacee par N1 (S1 et P2 restent) ==")
s, cats = j("GET", "/besoins/choix")
cat = cats[0]["nom"] if cats else None
s, bes = j("POST", "/besoins", {"user_id": U1["id"], "type": cat, "quantite": 1})
show("besoin ouvert cree", s == 201, bes)
s, sig1 = echange(U1, [N1], [(P1, "reforme")], besoin_ids=[bes["id"]], note="renouvellement anticipe")
show("echange accepte (201)", s == 201 and sig1["audit_json"]["type"] == "echange", sig1)
AE1 = sig1["assignment_id"]
show("preuves : 1 remis, 1 restitue, temoin, devenirs", sig1["audit_json"]["nb_actifs"] == 1 and sig1["audit_json"]["nb_restitues"] == 1
     and sig1["audit_json"]["temoin"] == ADMIN and sig1["audit_json"]["devenirs"] == {str(P1["id"]): "reforme"}, sig1["audit_json"])
show("signataire deduit de la fiche", sig1["signataire"] == "Zz1 ZZEC1", sig1["signataire"])
show("statuts : N1 affecte, P1 reforme, S1 et P2 inchanges", statut(N1) == "affecte" and statut(P1) == "reforme" and statut(S1) == "affecte" and statut(P2) == "affecte")
s, lst = j("GET", "/assignments?user_id=%d" % U1["id"])
by = {a["id"]: a for a in lst}
show("nouvelle affectation de type echange, signee", by[AE1]["type"] == "echange" and by[AE1]["date_signature"] is not None and by[AE1]["statut"] == "en_cours", by.get(AE1))
show("l'echange liste l'ancien materiel restitue et son devenir", [(r["id"], r["destination"]) for r in by[AE1]["restitues"]] == [(P1["id"], "reforme")], by[AE1]["restitues"])
show("A1 reste ouverte (S1 encore detenu), A2 aussi", by[A1["id"]]["statut"] == "en_cours" and by[A2["id"]]["statut"] == "en_cours")
show("les remises classiques gardent le type remise", by[A1["id"]]["type"] == "remise")
s, b2 = j("GET", "/besoins?user_id=%d" % U1["id"])
sold = next(b for b in b2 if b["id"] == bes["id"])
show("besoin solde par l'echange", sold["statut"] == "satisfait" and sold["assignment_id"] == AE1, sold)
s, b, txt = pdf_text(AE1)
show("document d'echange : PDF", s == 200 and b[:5] == b"%PDF-", s)
show("document : deux tableaux, materiel remis et restitue", "Materiel remis" in txt and "Materiel restitue" in txt and "ZZEC-ID-N1" in txt and "ZZEC-ID-P1" in txt, txt[:200])
show("document : declaration d'echange et titre", "avoir restitue l'ancien materiel" in txt and "echange de materiel" in txt.lower(), txt[-300:])
req = urllib.request.Request(B + "/assignments/%d/document?type=echange" % AE1, headers={"Authorization": "Bearer " + ADM})
resp = urllib.request.urlopen(req, timeout=60)
fname = re.search(r'filename="([^"]+)"', resp.headers["Content-Disposition"]).group(1)
show("nom de fichier lisible et numerote (un seul numero)", bool(NOM_RE.match(fname)), fname)
s, b = raw("GET", "/assignments/%d/document?type=restitution" % AE1)
show("pas de document de restitution separe pour l'echange", s == 404, s)
s, b = raw("GET", "/assignments/%d/document?type=nimporte" % AE1)
show("type de document inconnu : 422", s == 422, s)

print("== Echange total : S1 remis en stock, P2 rendu, remplaces par N2 et N3 ==")
s, sig2 = echange(U1, [N2, N3], [(S1, "stock"), (P2, "rendu")])
show("2e echange accepte", s == 201, sig2)
AE2 = sig2["assignment_id"]
show("statuts : S1 en stock, P2 rendu, N2 et N3 affectes", statut(S1) == "stock" and statut(P2) == "rendu" and statut(N2) == "affecte" and statut(N3) == "affecte")
s, lst = j("GET", "/assignments?user_id=%d" % U1["id"])
by = {a["id"]: a for a in lst}
show("A1 et A2 cloturees (plus rien de detenu)", by[A1["id"]]["statut"] == "restitue" and by[A2["id"]]["statut"] == "restitue"
     and by[A1["id"]]["date_restitution"] and by[A2["id"]]["date_restitution"], [by[A1["id"]]["statut"], by[A2["id"]]["statut"]])
show("le 2e echange liste ses deux retours", {(r["id"], r["destination"]) for r in by[AE2]["restitues"]} == {(S1["id"], "stock"), (P2["id"], "rendu")})
s, st = j("GET", "/assets?statut=stock")
show("S1 remis en stock est de nouveau disponible", S1["id"] in {a["id"] for a in st})
s, h = j("GET", "/lifecycle/holdings/%d" % U1["id"])
show("materiel detenu : N1, N2, N3", {a["id"] for a in h} == {N1["id"], N2["id"], N3["id"]}, [a["id"] for a in h])
s, rc = j("GET", "/assignments/echange/recap?user_id=%d" % U1["id"])
show("ecran : plus que le nouveau materiel", {a["id"] for a in rc["detenus"]} == {N1["id"], N2["id"], N3["id"]})

print("== Charte annexee (au choix) ==")
s, pol = upload("/policies", {"titre": "ZZEC charte", "entite_id": str(EA)}, ADM)
show("charte de l'entite deposee", s == 201, pol)
s, rc = j("GET", "/assignments/echange/recap?user_id=%d" % U1["id"])
show("ecran : charte applicable proposee", rc["charte"] and rc["charte"]["id"] == pol["id"], rc.get("charte"))
s, sig3 = echange(U1, [N4], [(N1, "rendu")], joindre_charte=True)
show("echange avec charte accepte", s == 201 and sig3["audit_json"]["charte"] and sig3["audit_json"]["charte"]["id"] == pol["id"], sig3)
s, b3, txt3 = pdf_text(sig3["assignment_id"])
show("la charte est annexee (document plus long)", s == 200 and len(PdfReader(io.BytesIO(b3)).pages) > len(PdfReader(io.BytesIO(raw("GET", "/assignments/%d/document?type=echange" % AE2)[1])).pages)
     and "charte informatique" in txt3.lower(), txt3[-200:])
s, sig4 = echange(U1, [N5], [(N4, "rendu")])
show("sans option : charte non annexee", s == 201 and sig4["audit_json"]["charte"] is None, sig4.get("audit_json", {}).get("charte"))

print("== Statistiques et restitution classique ==")
q = "?entite_id=%d&du=%s&au=%s" % (EA, TODAY, TODAY)
s, st = j("GET", "/stats" + q)
mv = st["mouvements"]
# remises : P1+S1, P2, N1, N2+N3, N4, N5 = 8 ; retours : P1, S1, P2, N1, N4 = 5
show("mouvements : 8 remis, 5 restitues (par actif, echanges compris)", mv["remis"] == 8 and mv["restitues"] == 5, mv)
s, sig5 = j("POST", "/lifecycle/restituer", {"user_id": U1["id"], "consent": True, "signature_image": SIG})
show("restitution classique de tout le reste", s == 201, sig5)
s, st = j("GET", "/stats" + q)
show("la restitution classique enregistre aussi la date de retour de chaque actif (N2, N3, N5 : +3)", st["mouvements"]["restitues"] == 8, st["mouvements"])
s, lst = j("GET", "/assignments?user_id=%d" % U1["id"])
show("toutes les affectations du salarie sont cloturees", all(a["statut"] == "restitue" for a in lst), [a["statut"] for a in lst])

print("== Concurrence ==")
V1 = new_user("5", EA)
Q1, Q2, Q3 = new_asset("Q1", eid=EA), new_asset("Q2", eid=EA), new_asset("Q3", eid=EA)
s, AQ = j("POST", "/assignments", {"user_id": V1["id"], "asset_ids": [Q1["id"]], "sans_charte": True})
res = []
def go(nv):
    res.append(echange(V1, [nv], [(Q1, "rendu")])[0])
ts = [threading.Thread(target=go, args=(Q2,)), threading.Thread(target=go, args=(Q3,))]
[t.start() for t in ts]; [t.join() for t in ts]
show("deux echanges simultanes du meme materiel : un seul passe", sorted(res) == [201, 409], res)
show("un seul des deux nouveaux materiels est affecte", [statut(Q2), statut(Q3)].count("affecte") == 1 and [statut(Q2), statut(Q3)].count("stock") == 1, (statut(Q2), statut(Q3)))

print("== Journal, suppression ==")
s, logs = j("GET", "/audit?limit=200")
ech = [x for x in logs if x["action"] == "echange"]
show("echanges journalises (comptes, jamais de nom)", len(ech) >= 4 and all("remis" in (x.get("detail") or "") and "ZZEC" not in json.dumps(x) for x in ech), ech[:1])
s, r = j("DELETE", "/users/%d" % U1["id"])
show("un salarie qui a des echanges ne se supprime pas : 409", s == 409, r)

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
