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

"""Annulation d'un import : lots, garde-fous (element deja utilise), tout ou rien, ordre inverse, droits, journal.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/import_annulation_check.py

Cree des donnees marquees ZZIA (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import base64
import io
import json
import os
import sys
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


def call(method, path, body=None, token=None, raw=None, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
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


def upload(kind, content, query=""):
    boundary = "----kikanIA"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.csv\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + content.encode() + f"\r\n--{boundary}--\r\n".encode()
    s, b = call("POST", f"/import/{kind}{query}", token=T, raw=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def lots():
    return j("GET", "/import/lots?limit=100")[1]


def undo(lot_id):
    return j("POST", f"/import/lots/{lot_id}/annuler", {})


def audit_actions():
    s, rows = j("GET", "/audit?limit=500")
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    return {x.get("action") for x in rows}


ENT = "code;nom;code_parent;actif\nZZIA-E1;ZZIA Groupe;;oui\nZZIA-E2;ZZIA Filiale;ZZIA-E1;oui\n"
APP = "nom;description;code_entite;actif\nZZIA-App;Application d'essai;ZZIA-E2;oui\n"
USR = "matricule;nom;prenom;code_entite;statut\nZZIA-U1;Dupont;ZZIAUn;ZZIA-E2;actif\nZZIA-U2;Martin;ZZIADeux;ZZIA-E2;actif\n"
MAT = ("identifiant_interne;type;marque;modele;numero_serie;statut;code_entite\n"
       "ZZIA-PC1;PC portable;ZZIA-HP;Elite;ZZIA-SN1;stock;ZZIA-E2\nZZIA-PC2;PC portable;ZZIA-HP;Elite;ZZIA-SN2;rendu;ZZIA-E2\n")
AFF = "matricule_utilisateur;identifiant_interne_actif;date_remise\nZZIA-U1;ZZIA-PC1;2026-09-01\nZZIA-U2;ZZIA-PC2;2026-09-01\n"
ACC = "matricule_utilisateur;application;acces;note\nZZIA-U1;ZZIA-App;oui;profil standard\n"

print("== Lots d'import ==")
n0 = len(lots())
s, r = upload("entites", ENT, "?dry_run=true")
show("la simulation ne cree aucun lot", s == 200 and "lot_id" not in r and len(lots()) == n0, (s, r.get("lot_id") if isinstance(r, dict) else r))
s, r = upload("entites", "code;nom\n;sans code\n", "?strict=true")
show("un import refuse (erreurs) ne cree aucun lot", s == 409 and len(lots()) == n0, s)
s, r_ent = upload("entites", ENT, "?strict=true")
show("un import reel renvoie son numero de lot", s == 200 and r_ent.get("imported") == 2 and isinstance(r_ent.get("lot_id"), int), r_ent.get("lot_id"))
s, r2 = upload("entites", ENT, "?strict=true")
show("reimporter le meme fichier (tout existe deja) ne cree pas de lot", s == 200 and r2.get("imported") == 0 and "lot_id" not in r2, r2.get("lot_id"))
mine = [x for x in lots() if x["id"] == r_ent["lot_id"]]
show("le lot est liste (type, createur, nombre de lignes)", len(mine) == 1 and mine[0]["kind"] == "entites" and mine[0]["nb_creees"] == 2
     and mine[0]["statut"] == "actif" and mine[0]["cree_par"], mine)

print("== Annulation simple ==")
s, sim = j("GET", f"/import/lots/{r_ent['lot_id']}/annulation")
show("la simulation d'annulation annonce 2 entites et aucun blocage", s == 200 and sim["annulable"] and sim["a_supprimer"] == {"entite": 2} and not sim["bloquants"], sim)
s, e = j("GET", "/entites")
show("les entites existent avant l'annulation", {"ZZIA-E1", "ZZIA-E2"} <= {x["code"] for x in e})
s, u = undo(r_ent["lot_id"])
show("annulation de l'import des entites", s == 200 and u["supprimes"] == 2, (s, u))
s, e = j("GET", "/entites")
show("les entites ont disparu", not ({"ZZIA-E1", "ZZIA-E2"} & {x["code"] for x in e}))
show("le lot est marque annule", [x for x in lots() if x["id"] == r_ent["lot_id"]][0]["statut"] == "annule")
s, u = undo(r_ent["lot_id"])
show("une seconde annulation est refusee (409)", s == 409, s)
s, sim = j("GET", f"/import/lots/{r_ent['lot_id']}/annulation")
show("un lot annule n'est plus annulable", s == 200 and sim["annulable"] is False)
s, u = undo(99999999)
show("lot inconnu -> 404", s == 404, s)

print("== Chaine d'imports : garde-fous ==")
ids = {}
for kind, content in (("entites", ENT), ("applications", APP), ("utilisateurs", USR), ("materiel", MAT), ("affectations", AFF), ("acces_applicatifs", ACC)):
    s, r = upload(kind, content, "?strict=true")
    ids[kind] = r.get("lot_id") if isinstance(r, dict) else None
    show(f"import {kind}", s == 200 and ids[kind] is not None, (s, r if s != 200 else r.get("imported")))
s, a = j("GET", "/assets?limit=500")
a = a if isinstance(a, list) else a.get("items", [])
pc1 = [x for x in a if x.get("identifiant_interne") == "ZZIA-PC1"][0]
show("le materiel remis est affecte", pc1["statut"] == "affecte", pc1["statut"])

s, u = undo(ids["entites"])
show("entites : refusees, car des salaries, actifs et applications s'en servent", s == 409 and "salarie" in json.dumps(u) and "actif" in json.dumps(u), u)
s, u = undo(ids["utilisateurs"])
show("salaries : refuses, car ils ont des affectations et des acces", s == 409 and "affectation" in json.dumps(u) and "acces" in json.dumps(u), u)
s, u = undo(ids["materiel"])
show("materiel : refuse, car des actifs sont affectes", s == 409 and "affecte" in json.dumps(u), u)
s, u = undo(ids["applications"])
show("applications : refusees, car un acces est attribue", s == 409 and "acces" in json.dumps(u), u)
show("un refus ne supprime rien (tout ou rien)", len([x for x in lots() if x["statut"] == "actif" and x["id"] in ids.values()]) == 6)
acts = audit_actions()
show("le refus est journalise", "import_annulation_refusee" in acts)

print("== Chaine d'imports : annulation dans l'ordre inverse ==")
s, u = undo(ids["acces_applicatifs"])
show("acces : annules", s == 200 and u["supprimes"] == 1, u)
s, u = undo(ids["affectations"])
show("affectations : annulees", s == 200 and u["supprimes"] >= 2, u)
s, a = j("GET", "/assets?limit=500")
a = a if isinstance(a, list) else a.get("items", [])
st = {x["identifiant_interne"]: x["statut"] for x in a if str(x.get("identifiant_interne", "")).startswith("ZZIA-")}
show("les actifs reprennent leur statut d'avant (stock, rendu)", st.get("ZZIA-PC1") == "stock" and st.get("ZZIA-PC2") == "rendu", st)
s, asg = j("GET", "/assignments")
asg = asg if isinstance(asg, list) else asg.get("items", [])
s, us = j("GET", "/users")
zz = {x["id"] for x in us if str(x.get("matricule", "")).startswith("ZZIA-")}
show("plus aucune affectation pour ces salaries", not [x for x in asg if x["user_id"] in zz])
s, u = undo(ids["applications"])
show("applications : annulees", s == 200 and u["supprimes"] == 1, u)
s, u = undo(ids["utilisateurs"])
show("salaries : annules", s == 200 and u["supprimes"] == 2, u)
s, u = undo(ids["materiel"])
show("materiel : annule", s == 200 and u["supprimes"] == 2, u)
s, u = undo(ids["entites"])
show("entites : annulees", s == 200 and u["supprimes"] == 2, u)
show("l'annulation est journalisee", "import_annule" in audit_actions())

print("== Elements utilises hors de l'import ==")
s, r = upload("entites", ENT, "?strict=true")
lot_e = r["lot_id"]
s, e = j("GET", "/entites")
eid = [x["id"] for x in e if x["code"] == "ZZIA-E2"][0]
s, sal = j("POST", "/users", {"nom": "Manuel", "prenom": "ZZIAhors", "matricule": "ZZIA-H1", "statut": "actif", "entite_id": eid})
s, u = undo(lot_e)
show("une entite utilisee par un salarie cree a la main n'est pas annulable", s == 409 and "salarie" in json.dumps(u), u)
j("DELETE", f"/users/{sal['id']}")
s, u = undo(lot_e)
show("une fois le salarie supprime, l'annulation passe", s == 200 and u["supprimes"] == 2, (s, u))

s, r = upload("entites", ENT, "?strict=true")
lot_e = r["lot_id"]
s, e = j("GET", "/entites")
parent = [x for x in e if x["code"] == "ZZIA-E1"][0]
s, fille = j("POST", "/entites", {"code": "ZZIA-E9", "nom": "ZZIA creee a la main", "code_parent": "ZZIA-E1"})
s, u = undo(lot_e)
show("une entite mere d'une entite creee a la main n'est pas annulable", s == 409 and "mere" in json.dumps(u), u)
j("DELETE", f"/entites/{fille['id']}")
s, u = undo(lot_e)
show("sans l'entite fille, l'annulation passe", s == 200, (s, u))

print("== Remise signee ou besoin : plus annulable ==")
for kind, content in (("entites", ENT), ("utilisateurs", USR), ("materiel", MAT)):
    s, r = upload(kind, content, "?strict=true")
    ids[kind] = r["lot_id"]
s, r = upload("affectations", AFF, "?strict=true")
lot_aff = r["lot_id"]
s, us = j("GET", "/users")
u1 = [x for x in us if x.get("matricule") == "ZZIA-U1"][0]
s, asg = j("GET", f"/assignments?user_id={u1['id']}")
asg = asg if isinstance(asg, list) else asg.get("items", [])
s, sg = j("POST", f"/assignments/{asg[0]['id']}/sign", SIGN)
show("la remise importee se signe", s == 201, s)
s, sim = j("GET", f"/import/lots/{lot_aff}/annulation")
show("la simulation signale la remise signee", s == 200 and sim["annulable"] is False and any("signee" in x for x in sim["bloquants"]), sim)
s, u = undo(lot_aff)
show("affectations signees : annulation refusee (409)", s == 409 and "signee" in json.dumps(u), u)
s, bs = j("POST", "/besoins", {"user_id": [x for x in us if x.get("matricule") == "ZZIA-U2"][0]["id"], "type": "Smartphone Android", "quantite": 1})
show("un besoin de materiel est cree pour un des salaries", s == 201, s)
s, u = undo(ids["utilisateurs"])
show("salaries : annulation refusee (affectation signee, besoin)", s == 409 and "besoin" in json.dumps(u), u)

print("== Droits ==")
s, _ = call("GET", "/import/lots")
show("liste des lots sans jeton -> 401", s == 401, s)
s, _ = call("POST", f"/import/lots/{lot_aff}/annuler", {})
show("annulation sans jeton -> 401", s == 401, s)

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
