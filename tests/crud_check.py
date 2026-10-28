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

"""Tests de la modification et de la suppression (entites, salaries, materiel, applications).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/crud_check.py

Cree des donnees ZZCR et des comptes sec_cr* (nettoyage : tests/cleanup_test_data.sql).
Code de sortie 1 si un test echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402

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


def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
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
        return s, (b.decode("utf-8", "replace") if isinstance(b, bytes) else b)


def msg(r):
    return r.get("detail", "") if isinstance(r, dict) else str(r)


def ensure_account(name, role):
    s, b = call("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": PW, "portee_globale": True}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


def sign_payload():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"consent": True, "signature_image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "strokes": 4, "duration_ms": 1800}


SIGN = sign_payload()

print("== Preparation ==")
ids = [ensure_account("sec_crrh", "rh"), ensure_account("sec_crlect", "lecture")]
RH, LECT = login("sec_crrh", PW), login("sec_crlect", PW)
show("comptes de test", bool(RH and LECT))

print("== Entites : creation et hierarchie ==")
s, ga = j("POST", "/entites", {"code": "ZZCR-A", "nom": "ZZCR Groupe"})
show("creation", s == 201 and ga["code"] == "ZZCR-A")
s, r = j("POST", "/entites", {"code": "ZZCR-A", "nom": "Doublon"})
show("code deja utilise -> 409", s == 409 and "ZZCR-A" in msg(r), msg(r))
s, r = j("POST", "/entites", {"code": "ZZCR-X", "nom": "Orpheline", "code_parent": "ZZCR-NOPE"})
show("parent inconnu -> 400", s == 400 and "ZZCR-NOPE" in msg(r), msg(r))
s, r = j("POST", "/entites", {"code": "  ", "nom": "Vide"})
show("code vide -> 400", s == 400, msg(r))
s, gb = j("POST", "/entites", {"code": "ZZCR-B", "nom": "ZZCR Filiale", "code_parent": "ZZCR-A"})
s, gc = j("POST", "/entites", {"code": "ZZCR-C", "nom": "ZZCR Sous-filiale", "code_parent": "ZZCR-B"})
show("filiale et sous-filiale", gb.get("code_parent") == "ZZCR-A" and gc.get("code_parent") == "ZZCR-B")

print("== Entites : modification ==")
s, r = j("PUT", f"/entites/{ga['id']}", {"code": "ZZCR-A", "nom": "ZZCR Groupe", "code_parent": "ZZCR-A", "actif": True})
show("une entite ne peut pas etre son propre parent", s == 400, msg(r))
s, r = j("PUT", f"/entites/{ga['id']}", {"code": "ZZCR-A", "nom": "ZZCR Groupe", "code_parent": "ZZCR-B", "actif": True})
show("boucle directe (A sous B, B sous A) refusee", s == 400 and "boucle" in msg(r), msg(r))
s, r = j("PUT", f"/entites/{ga['id']}", {"code": "ZZCR-A", "nom": "ZZCR Groupe", "code_parent": "ZZCR-C", "actif": True})
show("boucle indirecte (A sous C sous B sous A) refusee", s == 400 and "boucle" in msg(r), msg(r))
s, r = j("PUT", f"/entites/{gb['id']}", {"code": "ZZCR-A", "nom": "x", "code_parent": None, "actif": True})
show("renommer vers un code deja pris -> 409", s == 409, msg(r))
s, r = j("PUT", f"/entites/{ga['id']}", {"code": "ZZCR-A2", "nom": "ZZCR Groupe renomme", "code_parent": None, "actif": True})
show("renommage du code accepte", s == 200 and r["code"] == "ZZCR-A2" and r["nom"] == "ZZCR Groupe renomme", msg(r))
s, kids = j("GET", "/entites")
kid = next(e for e in kids if e["id"] == gb["id"])
show("la filiale suit le renommage du code parent", kid["code_parent"] == "ZZCR-A2", kid["code_parent"])
s, r = j("PUT", f"/entites/{gb['id']}", {"code": "ZZCR-B", "nom": "ZZCR Filiale", "code_parent": "ZZCR-A2", "actif": False})
show("desactivation", s == 200 and r["actif"] is False)
s, r = j("PUT", "/entites/999999", {"code": "ZZCR-Z", "nom": "z"})
show("modifier une entite inconnue -> 404", s == 404)

print("== Salaries : creation et modification ==")
s, u1 = j("POST", "/users", {"prenom": "Ana", "nom": "Cree", "matricule": "ZZCR-U1", "statut": "actif", "entite_id": gb["id"]})
show("creation", s == 201)
s, r = j("POST", "/users", {"prenom": "Bis", "nom": "Doublon", "matricule": "ZZCR-U1", "statut": "actif"})
show("matricule deja utilise -> 409", s == 409 and "ZZCR-U1" in msg(r), msg(r))
s, r = j("POST", "/users", {"prenom": "Bis", "nom": "Inconnue", "matricule": "ZZCR-U9", "statut": "actif", "entite_id": 987654})
show("entite inconnue -> 400", s == 400, msg(r))
s, u2 = j("POST", "/users", {"prenom": "Bob", "nom": "Deux", "matricule": "ZZCR-U2", "statut": "actif"})
body = {"prenom": "Ana", "nom": "Modifiee", "matricule": "ZZCR-U1", "statut": "actif", "entite_id": gb["id"], "service": "Compta"}
s, r = j("PUT", f"/users/{u1['id']}", body)
show("modification (nom, service)", s == 200 and r["nom"] == "Modifiee" and r["service"] == "Compta" and r["maj_le"] != u1["maj_le"], msg(r))
s, r = j("PUT", f"/users/{u1['id']}", {**body, "matricule": "ZZCR-U2"})
show("matricule d'un autre -> 409", s == 409, msg(r))
s, r = j("PUT", f"/users/{u1['id']}", {**body, "statut": "prevu"})
show("actif vers prevu autorise", s == 200 and r["statut"] == "prevu")
s, r = j("PUT", f"/users/{u1['id']}", {**body, "statut": "actif"})
show("prevu vers actif autorise", s == 200 and r["statut"] == "actif")
s, r = j("PUT", f"/users/{u1['id']}", {**body, "statut": "sorti"})
show("sorti saisi a la main refuse (409, page Sorties)", s == 409 and "Sorties" in msg(r), msg(r))
s, r = j("PUT", f"/users/{u1['id']}", {**body, "statut": "en_depart"})
show("en_depart saisi a la main refuse (409)", s == 409, msg(r))
s, r = j("PUT", f"/users/{u1['id']}", {**body, "entite_id": 987654})
show("entite inconnue a la modification -> 400", s == 400)

print("== Materiel : creation et modification ==")
def asset(sn, **kw):
    return {"type": "PC", "marque": "ZZCR", "modele": "M", "numero_serie": sn, "identifiant_interne": "ZZCR-ID-" + sn[-2:], "statut": "stock", **kw}

s, a1 = j("POST", "/assets", asset("ZZCR-S1"))
show("creation", s == 201)
s, r = j("POST", "/assets", asset("ZZCR-S1", identifiant_interne="ZZCR-AUTRE"))
show("numero de serie en double -> 409", s == 409 and "ZZCR-S1" in msg(r), msg(r))
s, r = j("POST", "/assets", asset("ZZCR-S9", identifiant_interne="ZZCR-ID-S1"))
show("identifiant interne en double -> 409", s == 409, msg(r))
s, r = j("POST", "/assets", asset("ZZCR-S8", statut="affecte"))
show("creation directement 'affecte' refusee", s == 409, msg(r))
s, r = j("POST", "/assets", asset("ZZCR-S7", entite_id=987654))
show("entite inconnue -> 400", s == 400)
s, a2 = j("POST", "/assets", asset("ZZCR-S2"))
a1b = {k: a1[k] for k in ("identifiant_interne", "type", "marque", "modele", "numero_serie", "statut", "entite_id", "notes",
                          "date_achat", "fin_garantie", "echeance_renouvellement", "source", "id_externe")}
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "modele": "M2", "notes": "ok"})
show("modification (modele, notes)", s == 200 and r["modele"] == "M2" and r["notes"] == "ok", msg(r))
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "numero_serie": "ZZCR-S2"})
show("numero de serie d'un autre actif -> 409", s == 409, msg(r))
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "statut": "affecte"})
show("stock vers affecte a la main refuse (409)", s == 409, msg(r))
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "statut": "rendu"})
show("stock vers rendu a la main refuse (409)", s == 409, msg(r))
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "statut": "reforme"})
show("stock vers reforme autorise", s == 200 and r["statut"] == "reforme")
s, r = j("PUT", f"/assets/{a1['id']}", {**a1b, "statut": "stock"})
show("reforme vers stock autorise", s == 200 and r["statut"] == "stock")

print("== Applications ==")
s, p1 = j("POST", "/applications", {"nom": "ZZCR-ERP", "description": "ERP"})
show("creation", s == 201)
s, r = j("POST", "/applications", {"nom": "zzcr-erp"})
show("doublon (casse differente) -> 409", s == 409, msg(r))
s, p2 = j("POST", "/applications", {"nom": "ZZCR-ERP", "entite_id": ga["id"]})
show("meme nom dans une autre portee (entite) autorise", s == 201)
s, r = j("POST", "/applications", {"nom": "  "})
show("nom vide -> 400", s == 400)
s, r = j("POST", "/applications", {"nom": "ZZCR-X", "entite_id": 987654})
show("entite inconnue -> 400", s == 400)
s, r = j("PUT", f"/applications/{p2['id']}", {"nom": "ZZCR-ERP", "entite_id": None, "actif": True})
show("modification vers un doublon -> 409", s == 409, msg(r))
s, r = j("PUT", f"/applications/{p1['id']}", {"nom": "ZZCR-ERP", "description": "ERP v2", "entite_id": None, "actif": False})
show("modification et desactivation", s == 200 and r["description"] == "ERP v2" and r["actif"] is False)

print("== Suppression refusee : l'element est utilise ==")
def refused(name, path, *needles, token=None):
    s, r = j("DELETE", path, token=token)
    show(name, s == 409 and all(n in msg(r) for n in needles), f"HTTP {s} {msg(r)}")

refused("entite avec une entite fille", f"/entites/{ga['id']}", "1 entite(s) fille(s)", "Desactivez")
refused("entite avec un salarie", f"/entites/{gb['id']}", "1 salarie(s)")
s, ab = j("POST", "/assets", asset("ZZCR-S3", entite_id=gc["id"]))
refused("entite avec un actif", f"/entites/{gc['id']}", "1 actif(s)")
s, ap = j("POST", "/applications", {"nom": "ZZCR-PAIE", "entite_id": gc["id"]})
s, r = j("DELETE", f"/assets/{ab['id']}")
show("(actif sans historique supprime)", s == 204)
refused("entite avec une application", f"/entites/{gc['id']}", "1 application(s)")
s, g = j("POST", "/entites", {"code": "ZZCR-P", "nom": "ZZCR Avec charte"})
bd = "----kikanCR"
md = b"# Charte test\n\nTexte.\n"
raw = (f'--{bd}\r\nContent-Disposition: form-data; name="titre"\r\n\r\nZZCR Charte\r\n--{bd}\r\nContent-Disposition: form-data; name="entite_id"\r\n\r\n{g["id"]}\r\n'
       f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="c.md"\r\nContent-Type: text/markdown\r\n\r\n').encode() + md + f"\r\n--{bd}--\r\n".encode()
s, _ = call("POST", "/policies", token=ADM, raw=raw, ctype="multipart/form-data; boundary=" + bd)
refused("entite avec une charte", f"/entites/{g['id']}", "1 charte(s)")

s, asg = j("POST", "/assignments", {"user_id": u2["id"], "asset_ids": [a2["id"]]})
refused("salarie avec une affectation", f"/users/{u2['id']}", "1 affectation(s) de materiel", "purge RGPD")
refused("actif affecte", f"/assets/{a2['id']}", "1 affectation(s)", "reforme")
s, r = j("PUT", f"/assets/{a2['id']}", {**{k: a2[k] for k in a1b}, "statut": "stock"})
show("actif affecte : statut non modifiable (409)", s == 409 and "restitution" in msg(r), msg(r))
s, r = j("PUT", f"/assets/{a2['id']}", {**{k: a2[k] for k in a1b}, "statut": "affecte", "modele": "M3"})
show("actif affecte : autres champs modifiables", s == 200 and r["modele"] == "M3" and r["statut"] == "affecte", msg(r))
j("POST", f"/users/{u2['id']}/applications", {"application_id": p2["id"], "acces": True, "note": "n"})
refused("application avec un acces attribue", f"/applications/{p2['id']}", "1 acces attribue(s)", "Desactivez")

print("== Apres restitution ==")
s, sg = j("POST", f"/assignments/{asg['id']}/sign", SIGN)
j("POST", f"/lifecycle/depart/{u2['id']}", {"date_sortie": "2026-12-31"})
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u2["id"], **SIGN})
show("depart et restitution signes", s == 201, msg(rs))
s, cur = j("GET", f"/users/{u2['id']}")
ub = {k: cur[k] for k in ("prenom", "nom", "matricule", "statut", "entite_id", "service", "date_arrivee", "date_sortie", "email")}
s, r = j("PUT", f"/users/{u2['id']}", {**ub, "statut": "actif"})
show("salarie sorti : reactivation refusee (409)", s == 409 and "reactive" in msg(r), msg(r))
s, r = j("PUT", f"/users/{u2['id']}", {**ub, "service": "Archives"})
show("salarie sorti : autres champs modifiables", s == 200 and r["service"] == "Archives")
s, cura = j("GET", f"/assets/{a2['id']}")
ab2 = {k: cura[k] for k in a1b}
s, r = j("PUT", f"/assets/{a2['id']}", {**ab2, "statut": "stock"})
show("actif rendu : remise en stock autorisee", s == 200 and r["statut"] == "stock", msg(r))
refused("actif deja remis : suppression refusee meme en stock", f"/assets/{a2['id']}", "1 affectation(s)")

print("== Suppression autorisee ==")
s, free = j("POST", "/entites", {"code": "ZZCR-FREE", "nom": "ZZCR Libre"})
s, r = j("DELETE", f"/entites/{free['id']}")
show("entite libre supprimee (204)", s == 204 and free["id"] not in {e["id"] for e in j("GET", "/entites")[1]})
show("entite supprimee : 404 ensuite", j("GET", f"/entites/{free['id']}")[0] == 404 and j("DELETE", f"/entites/{free['id']}")[0] == 404)
s, nu = j("POST", "/users", {"prenom": "Neuf", "nom": "Sansfiche", "matricule": "ZZCR-U3", "statut": "actif"})
s, r = j("DELETE", f"/users/{nu['id']}", token=RH)
show("RH : suppression d'un salarie refusee (403)", s == 403)
s, r = j("DELETE", f"/users/{nu['id']}")
show("informatique : salarie sans historique supprime (204)", s == 204 and j("GET", f"/users/{nu['id']}")[0] == 404)
s, na = j("POST", "/assets", asset("ZZCR-S4"))
s, r = j("DELETE", f"/assets/{na['id']}")
show("actif jamais remis supprime (204)", s == 204 and j("GET", f"/assets/{na['id']}")[0] == 404)
s, np_ = j("POST", "/applications", {"nom": "ZZCR-LIBRE"})
s, r = j("DELETE", f"/applications/{np_['id']}")
show("application sans acces supprimee (204)", s == 204)
show("suppression d'un element inconnu -> 404", j("DELETE", "/applications/999999")[0] == 404 and j("DELETE", "/assets/999999")[0] == 404
     and j("DELETE", "/users/999999")[0] == 404)

print("== Roles ==")
s, r = j("PUT", f"/users/{u1['id']}", {**body, "service": "RH ok"}, token=RH)
show("RH : modification d'un salarie autorisee", s == 200 and r["service"] == "RH ok", msg(r))
s, r = j("PUT", f"/users/{u1['id']}", body, token=LECT)
show("lecture : modification d'un salarie refusee (403)", s == 403)
for name, path, payload in (
    ("entite", f"/entites/{gb['id']}", {"code": "ZZCR-B", "nom": "x"}),
    ("actif", f"/assets/{a1['id']}", a1b),
    ("application", f"/applications/{p1['id']}", {"nom": "ZZCR-ERP"}),
):
    show(f"RH : modification d'une/un {name} refusee (403)", j("PUT", path, payload, token=RH)[0] == 403)
    show(f"lecture : suppression d'une/un {name} refusee (403)", j("DELETE", path, token=LECT)[0] == 403)

print("== Journal d'audit ==")
j("PUT", f"/users/{u1['id']}", {**body, "service": "ValeurSecreteZZCR", "nom": "NomSecretZZCR"})
s, log = j("GET", "/audit?limit=300")
mods = [x for x in log if x["action"] == "modification" and x["target"] == f"users/{u1['id']}"]
last = max(mods, key=lambda x: x["id"]) if mods else {}
show("modification journalisee avec les noms de champs", bool(mods) and "service" in last.get("detail", "") and "nom" in last.get("detail", ""), last.get("detail"))
show("journal : jamais les valeurs (donnees personnelles)", not any("Secret" in (x.get("detail") or "") for x in log))
show("journal : champs inchanges non listes", "matricule" not in last.get("detail", ""), last.get("detail"))

for aid in ids:
    call("PUT", f"/auth/accounts/{aid}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
