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

"""Renouvellements (informatique) : materiel a renouveler, detenteur, report ou avancement de l'echeance, materiel rendu exclu.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/renouvellements_check.py

Cree des donnees ZZRN et des comptes sec_rn* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
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
import calendar
import io
from datetime import date, timedelta

from PIL import Image, ImageDraw

sys.path.insert(0, "/app")
TODAY = date.today()
FIN_DU_MOIS = date(TODAY.year, TODAY.month, calendar.monthrange(TODAY.year, TODAY.month)[1])


def sig_image():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)], fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIG = sig_image()


def account(name, role):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True})
    if s == 409:
        acc = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == name.lower())
        j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, "portee_globale": True})


def situation(d):
    if d < TODAY:
        return "en_retard"
    return "ce_mois" if d <= FIN_DU_MOIS else "a_venir"


def asset(cle, echeance, eid=None, statut=None):
    s, r = j("POST", "/assets", {"type": "ZZRN type", "marque": "ZZRN", "modele": "M" + cle, "numero_serie": "ZZRN-SN-" + cle,
                                 "identifiant_interne": "ZZRN-ID-" + cle, "entite_id": eid, "echeance_renouvellement": str(echeance) if echeance else None})
    if statut and "id" in r:
        j("PUT", "/assets/%d" % r["id"], {**r, "statut": statut})
    return r


def liste(query="", token=None):
    return j("GET", "/renouvellements" + query, None, token)


def ids_zz(rows):
    return {i["identifiant_interne"]: i for i in rows["items"] if (i["identifiant_interne"] or "").startswith("ZZRN-ID-")}


print("== Preparation ==")
ent = {}
for code in ("ZZRN-A", "ZZRN-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZRN-A"], ent["ZZRN-B"]
account("sec_rn_rh", "rh")
account("sec_rn_le", "lecture")
RH, LE = login("sec_rn_rh", PW), login("sec_rn_le", PW)
j("POST", "/parametres/types", {"nom": "ZZRN type"})
s, U = j("POST", "/users", {"matricule": "ZZRN-1", "nom": "ZZRN1", "prenom": "Zz1", "entite_id": EA, "statut": "actif", "date_arrivee": str(TODAY)})
RETARD = asset("RETARD", TODAY - timedelta(days=10), EA)           # detenu par U, echeance depassee
PROCHE = asset("PROCHE", FIN_DU_MOIS if FIN_DU_MOIS > TODAY else TODAY, EA)   # ce mois-ci (ou aujourd'hui)
FUTUR = asset("FUTUR", TODAY + timedelta(days=75), EA)              # dans environ 2 a 3 mois
LOIN = asset("LOIN", TODAY + timedelta(days=200), EA)               # hors d'un horizon de 3 mois
SANS = asset("SANS", None, EA)                                      # aucune echeance
REF = asset("REF", TODAY - timedelta(days=30), EA, "reforme")       # reforme : hors liste
AUTRE = asset("AUTRE", TODAY - timedelta(days=5), EB)               # autre entite
RENDU = asset("RENDU", TODAY - timedelta(days=20), EA)              # sera rendu
show("materiel cree", all("id" in a for a in (RETARD, PROCHE, FUTUR, LOIN, SANS, REF, AUTRE, RENDU)))
s, A = j("POST", "/assignments", {"user_id": U["id"], "asset_ids": [RETARD["id"], RENDU["id"]], "sans_charte": True})
j("POST", "/assignments/%d/sign" % A["id"], {"consent": True, "signature_image": SIG})

print("== Droits ==")
for who, tok in (("RH", RH), ("lecture", LE)):
    s, r = liste("", tok)
    show("%s : liste refusee" % who, s == 403, r)
    s, r = j("POST", "/renouvellements/%d/reporter" % FUTUR["id"], {"nouvelle": str(TODAY + timedelta(days=100))}, tok)
    show("%s : report refuse" % who, s == 403, r)
s, b = call("GET", "/renouvellements", None, None)
show("sans session : refuse", s in (401, 403), s)

print("== Liste ==")
s, r = liste("?horizon_mois=3")
z = ids_zz(r) if s == 200 else {}
show("liste (3 mois) : retard, ce mois, a venir", s == 200 and {"ZZRN-ID-RETARD", "ZZRN-ID-PROCHE", "ZZRN-ID-FUTUR", "ZZRN-ID-AUTRE", "ZZRN-ID-RENDU"} <= set(z), sorted(z))
show("hors liste : echeance trop lointaine, sans echeance, reforme", not ({"ZZRN-ID-LOIN", "ZZRN-ID-SANS", "ZZRN-ID-REF"} & set(z)), sorted(z))
show("situation calculee", z["ZZRN-ID-RETARD"]["situation"] == "en_retard" and z["ZZRN-ID-PROCHE"]["situation"] == situation(FIN_DU_MOIS if FIN_DU_MOIS > TODAY else TODAY)
     and z["ZZRN-ID-FUTUR"]["situation"] == situation(TODAY + timedelta(days=75)), {k: v["situation"] for k, v in z.items()})
show("jours : negatif quand l'echeance est depassee", z["ZZRN-ID-RETARD"]["jours"] == -10, z["ZZRN-ID-RETARD"]["jours"])
show("detenteur indique pour le materiel affecte", z["ZZRN-ID-RETARD"]["detenteur"] == {"id": U["id"], "nom": "Zz1 ZZRN1"}, z["ZZRN-ID-RETARD"]["detenteur"])
show("materiel en stock : pas de detenteur", z["ZZRN-ID-FUTUR"]["detenteur"] is None and z["ZZRN-ID-FUTUR"]["statut"] == "stock")
show("totaux coherents avec la liste", sum(r["totaux"].values()) == len(r["items"]), r["totaux"])
s, r12 = liste("?horizon_mois=12")
show("horizon de 12 mois : l'echeance lointaine apparait", "ZZRN-ID-LOIN" in ids_zz(r12))
s, r0 = liste("?horizon_mois=0")
z0 = ids_zz(r0)
show("horizon 0 : seulement les echeances depassees", set(z0) == {"ZZRN-ID-RETARD", "ZZRN-ID-AUTRE", "ZZRN-ID-RENDU"}, sorted(z0))
s, r = liste("?horizon_mois=99")
show("horizon hors limites : 422", s == 422, r)
s, rb = liste("?horizon_mois=3&entite_id=%d" % EB)
show("filtre entite B", s == 200 and set(ids_zz(rb)) == {"ZZRN-ID-AUTRE"}, sorted(ids_zz(rb)))
s, r = liste("?entite_id=99999999")
show("entite inconnue : 404", s == 404, r)
items = [i for i in r12["items"] if i["echeance"]]
show("tri par echeance", [i["echeance"] for i in items] == sorted(i["echeance"] for i in items))

print("== Report de l'echeance ==")
nouvelle = TODAY + timedelta(days=120)
s, r = j("POST", "/renouvellements/%d/reporter" % RETARD["id"], {"nouvelle": str(nouvelle), "motif": "  materiel\r\nencore   en bon etat\x00 "})
show("report d'une echeance depassee", s == 200 and r["echeance"] == str(nouvelle), r)
s, a = j("GET", "/assets/%d" % RETARD["id"])
show("l'echeance du materiel est mise a jour", a["echeance_renouvellement"] == str(nouvelle))
s, rl = liste("?horizon_mois=3")
show("le materiel reporte sort de la liste a 3 mois", "ZZRN-ID-RETARD" not in ids_zz(rl))
s, rl = liste("?horizon_mois=12")
dr = ids_zz(rl)["ZZRN-ID-RETARD"]["dernier_report"]
show("dernier report : date, auteur, anciennes et nouvelles echeances", dr["par"] == ADMIN and dr["nouvelle"] == str(nouvelle)
     and dr["ancienne"] == str(TODAY - timedelta(days=10)) and dr["le"] == str(TODAY), dr)
show("motif nettoye (espaces et caracteres de controle)", dr["motif"] == "materiel encore en bon etat", repr(dr["motif"]))
s, r = j("POST", "/renouvellements/%d/reporter" % RETARD["id"], {"nouvelle": str(nouvelle)})
show("meme echeance : 409", s == 409, r)
s, r = j("POST", "/renouvellements/%d/reporter" % RETARD["id"], {"nouvelle": str(TODAY - timedelta(days=1))})
show("echeance dans le passe : 400", s == 400, r)
s, r = j("POST", "/renouvellements/%d/reporter" % RETARD["id"], {"nouvelle": str(TODAY + timedelta(days=5)), "motif": "x" * 201})
show("motif trop long : 422", s == 422, r)
s, r = j("POST", "/renouvellements/%d/reporter" % RETARD["id"], {"nouvelle": str(TODAY + timedelta(days=3))})
show("avancer l'echeance (anticiper) sans motif", s == 200, r)
s, r = j("POST", "/renouvellements/%d/reporter" % SANS["id"], {"nouvelle": str(TODAY + timedelta(days=40))})
show("donner une echeance a un materiel qui n'en avait pas", s == 200, r)
s, r = j("POST", "/renouvellements/%d/reporter" % SANS["id"], {"nouvelle": None})
show("aucun renouvellement prevu (echeance supprimee)", s == 200 and r["echeance"] is None, r)
s, a = j("GET", "/assets/%d" % SANS["id"])
show("echeance supprimee sur la fiche", a["echeance_renouvellement"] is None)
s, r = j("POST", "/renouvellements/%d/reporter" % REF["id"], {"nouvelle": str(TODAY + timedelta(days=40))})
show("materiel reforme : 409", s == 409, r)
s, r = j("POST", "/renouvellements/99999999/reporter", {"nouvelle": str(TODAY + timedelta(days=40))})
show("materiel inconnu : 404", s == 404, r)
s, logs = j("GET", "/audit?limit=200")
rep = [x for x in logs if x["action"] == "echeance_reportee"]
show("reports journalises par leurs dates, jamais par le motif", len(rep) >= 3 and not any("encore" in json.dumps(x) for x in rep), rep[:1])

print("== Le materiel rendu n'est plus a renouveler ==")
s, rl = liste("?horizon_mois=0")
show("avant restitution : RENDU est en retard", "ZZRN-ID-RENDU" in ids_zz(rl))
s, pv = j("GET", "/previsions?du=%s&au=%s" % (TODAY - timedelta(days=400), TODAY + timedelta(days=400)))
avant = {i["identifiant_interne"] for i in pv["items"]} | set()
s, sig = j("POST", "/lifecycle/restituer", {"user_id": U["id"], "asset_ids": [RENDU["id"]], "consent": True, "signature_image": SIG})
show("restitution du materiel RENDU", s == 201, sig)
s, rl = liste("?horizon_mois=12")
show("rendu : plus dans la liste des renouvellements", "ZZRN-ID-RENDU" not in ids_zz(rl))
s, r = j("POST", "/renouvellements/%d/reporter" % RENDU["id"], {"nouvelle": str(TODAY + timedelta(days=40))})
show("rendu : le report est refuse (409)", s == 409, r)
s, st = j("GET", "/stats?entite_id=%d" % EA)
show("statistiques : le materiel rendu n'est plus dans les echeances", all(i["identifiant_interne"] != "ZZRN-ID-RENDU" for i in st["renouvellements_12m"]["items"]))
s, pv2 = j("GET", "/previsions?du=%s&au=%s&entite_id=%d" % (TODAY - timedelta(days=400), TODAY + timedelta(days=400), EA))
show("previsions : le materiel rendu n'est plus compte", all(i["identifiant_interne"] != "ZZRN-ID-RENDU" for i in pv2["items"]) and pv2["en_retard"]["nombre"] >= 0)
from sqlmodel import Session  # noqa: E402
from app import mailer, reminders  # noqa: E402
from app.db import engine  # noqa: E402
with Session(engine) as ss:
    cfg = mailer.load_config(ss)
    cfg.renouv, cfg.renouv_jours = True, 400
    texte = " | ".join(x["ligne"] for x in reminders.collect(ss, cfg, TODAY)["renouv"])
    show("rappels : le materiel rendu n'est plus signale", "ZZRN-ID-RENDU" not in texte and "ZZRN-ID-AUTRE" in texte, texte[:160])

print("== Suppression ==")
s, r = j("DELETE", "/assets/%d" % SANS["id"])
show("un materiel jamais remis, avec historique de reports, se supprime", s == 204, r)

print("%d echec(s)" % fails)
sys.exit(1 if fails else 0)
