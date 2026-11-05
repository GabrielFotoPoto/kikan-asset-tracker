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

"""Lot 1bis (SPEC 6.3bis) : Constat de materiel non restitue et cloture sans materiel.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kiktest-api python - < tests/depart_exception_check.py

Cree des donnees ZZEX et des comptes sec_ex_* (nettoyage : tests/cleanup_test_data.sql).
Couvre les 8 criteres d'acceptation du lot 1bis et les cas limites.
Code de sortie 1 si un test echoue. 100% ASCII.
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402
from sqlmodel import Session, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Asset, AssetStatus, Assignment, AssignmentAsset, AuditLog, User  # noqa: E402
from app.purge import purger  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Ex-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:200] if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        B + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=h,
    )
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


def signature_b64():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line(
        [(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
        fill=(17, 17, 17, 255),
        width=7,
    )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIGN = {"consent": True, "signature_image": signature_b64(), "strokes": 4, "duration_ms": 1800}


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        accs = j("GET", "/auth/accounts")[1]
        acc = next(a for a in accs if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


def parcours(uid, token):
    return j("GET", f"/parcours/depart/{uid}", token=token)


def etat(rep, cle):
    for e in rep.get("etapes", []):
        if e["cle"] == cle:
            return e["etat"]
    return None


def etape(rep, cle):
    for e in rep.get("etapes", []):
        if e["cle"] == cle:
            return e
    return {}


def get_entite(code, nom):
    s, r = j("POST", "/entites", {"code": code, "nom": nom})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    return r["id"]


print("== Preparation des entites et comptes de test ==")
EA = get_entite("ZZEX-EA", "ZZEX Entite A")
EB = get_entite("ZZEX-EB", "ZZEX Entite B")

account("sec_ex_it_a", "informatique", portee_globale=False, entites=[EA])
account("sec_ex_rh_a", "rh", portee_globale=False, entites=[EA])
account("sec_ex_lec_a", "lecture", portee_globale=False, entites=[EA])
account("sec_ex_it_glob", "informatique")

IT_A = login("sec_ex_it_a", PW)
RH_A = login("sec_ex_rh_a", PW)
LEC_A = login("sec_ex_lec_a", PW)
IT_GL = login("sec_ex_it_glob", PW)

# Creation de salaries de test
sortie_future = (date.today() + timedelta(days=5)).isoformat()
s, u1 = j("POST", "/users", {"matricule": "ZZEX-U1", "nom": "ZZEXU1", "prenom": "Alice", "entite_id": EA, "statut": "actif"})
s, u2 = j("POST", "/users", {"matricule": "ZZEX-U2", "nom": "ZZEXU2", "prenom": "Bob", "entite_id": EB, "statut": "actif"})
s, u_sans = j("POST", "/users", {"matricule": "ZZEX-US", "nom": "ZZEXUS", "prenom": "SansMat", "entite_id": EA, "statut": "actif"})
s, u_actif = j("POST", "/users", {"matricule": "ZZEX-UA", "nom": "ZZEXUA", "prenom": "Actif", "entite_id": EA, "statut": "actif"})

# Actifs de test
s, a1 = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "modele": "M1", "numero_serie": "ZZEX-SN-1", "entite_id": EA})
s, a2 = j("POST", "/assets", {"type": "Ecran", "marque": "ZZEX", "modele": "M2", "numero_serie": "ZZEX-SN-2", "entite_id": EA})
s, a3 = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "modele": "M3", "numero_serie": "ZZEX-SN-3", "entite_id": EB})

# Affectations
j("POST", "/assignments", {"user_id": u1["id"], "asset_ids": [a1["id"], a2["id"]], "sans_charte": True})
j("POST", "/assignments", {"user_id": u2["id"], "asset_ids": [a3["id"]], "sans_charte": True})

# Application access for u1
s, app1 = j("POST", "/applications", {"nom": "ZZEX-App1", "entite_id": EA})
j("POST", f"/users/{u1['id']}/applications", {"application_id": app1["id"], "acces": True})

# Declaration des departs pour u1, u2 et u_sans
j("POST", f"/lifecycle/depart/{u1['id']}", {"date_sortie": sortie_future})
j("POST", f"/lifecycle/depart/{u2['id']}", {"date_sortie": sortie_future})
j("POST", f"/lifecycle/depart/{u_sans['id']}", {"date_sortie": sortie_future})

print("== C1bis-1 : Droits du constat de non-restitution (informatique seule) ==")
s_rh, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": "perte"}, token=RH_A)
s_lec, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": "perte"}, token=LEC_A)
s_anon, _ = call("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": "perte"})
show("C1bis-1a - constat refuse au RH (403)", s_rh == 403, s_rh)
show("C1bis-1b - constat refuse au role lecture (403)", s_lec == 403, s_lec)
show("C1bis-1c - constat refuse sans session (401)", s_anon == 401, s_anon)

print("== C1bis-2 : Validation stricte du motif (liste fermee) ==")
s_nomotif, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]]}, token=IT_A)
s_badmotif, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": "casse_involontaire"}, token=IT_A)
s_emptymotif, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": ""}, token=IT_A)
show("C1bis-2a - motif absent refuse (422)", s_nomotif == 422, s_nomotif)
show("C1bis-2b - motif hors liste fermee refuse (422)", s_badmotif == 422, s_badmotif)
show("C1bis-2c - motif vide refuse (422)", s_emptymotif == 422, s_emptymotif)

print("== C1bis-3 : Portee et controle des actifs et salarie ==")
# Salarie hors portee renvoie 404 identique a inexistant (test sur cloture par RH et inexistant sur constat)
s_clot_scope, _ = j("POST", f"/lifecycle/depart/{u2['id']}/cloturer", token=RH_A)
s_clot_inex, _ = j("POST", "/lifecycle/depart/99999/cloturer", token=RH_A)
s_const_inex, _ = j("POST", "/lifecycle/non-restitue", {"user_id": 99999, "asset_ids": [a1["id"]], "motif": "perte"}, token=IT_A)
show("C1bis-3a - salarie hors portee renvoie 404 identique a inexistant", s_clot_scope == 404 and s_clot_inex == 404 and s_const_inex == 404, (s_clot_scope, s_clot_inex, s_const_inex))

# Constat sur u1 mais avec a3 (actif affecte a u2)
s_autre_actif, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a3["id"]], "motif": "perte"}, token=IT_A)
show("C1bis-3b - actif d'un autre salarie refuse (409)", s_autre_actif == 409, s_autre_actif)

# Constat sur u_actif (salarie actif, pas en_depart)
s, a_actif = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "numero_serie": "ZZEX-SN-ACT", "entite_id": EA})
j("POST", "/assignments", {"user_id": u_actif["id"], "asset_ids": [a_actif["id"]], "sans_charte": True})
s_non_depart, _ = j("POST", "/lifecycle/non-restitue", {"user_id": u_actif["id"], "asset_ids": [a_actif["id"]], "motif": "vol"}, token=IT_A)
show("C1bis-3c - salarie hors en_depart refuse (409)", s_non_depart == 409, s_non_depart)

print("== C1bis-4 : Constat partiel, constat total, passage a sorti et reserve ==")
# 1er constat partiel sur a1
s_ok1, r_ok1 = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a1["id"]], "motif": "perte"}, token=IT_A)
show("C1bis-4a - constat partiel reussi (200)", s_ok1 == 200 and a1["id"] in r_ok1.get("actifs_constates", []), r_ok1)

# Verification etat intermediaire de u1 : encore en_depart, 1 materiel restant
_, p_inter = parcours(u1["id"], IT_A)
show(
    "C1bis-4b - apres constat partiel : salarie reste en_depart, etape 3 courante avec 1 restant",
    p_inter["salarie"]["statut"] == "en_depart"
    and etat(p_inter, "restitution") == "courante"
    and len(p_inter["materiel_a_recuperer"]) == 1
    and p_inter["materiel_a_recuperer"][0]["id"] == a2["id"],
    (p_inter["salarie"]["statut"], etat(p_inter, "restitution"), len(p_inter["materiel_a_recuperer"])),
)

# 2eme constat sur a2 (dernier actif de u1)
s_ok2, r_ok2 = j("POST", "/lifecycle/non-restitue", {"user_id": u1["id"], "asset_ids": [a2["id"]], "motif": "vol"}, token=IT_A)
show("C1bis-4c - constat du dernier actif reussi et salarie passe a sorti", s_ok2 == 200 and r_ok2.get("statut_salarie") == "sorti", r_ok2)

with Session(engine) as session:
    asg_u1 = session.exec(select(Assignment).where(Assignment.user_id == u1["id"])).first()
show(
    "C1bis-4cbis - affectation soldee par constat : statut restitue sans date_restitution",
    asg_u1 is not None and asg_u1.statut == "restitue" and asg_u1.date_restitution is None,
    (asg_u1.statut if asg_u1 else None, asg_u1.date_restitution if asg_u1 else None),
)

# Verification parcours u1 final : termine avec reserve (2 materiels non restitues et 1 acces a retirer)
_, p_final_it = parcours(u1["id"], IT_A)
_, p_final_rh = parcours(u1["id"], RH_A)
_, p_final_lec = parcours(u1["id"], LEC_A)

res_attendues = ["1 acces a retirer", "2 materiel(s) non restitue(s)"]
show(
    "C1bis-4d - parcours termine avec reserve (2 materiels non restitues et 1 acces)",
    p_final_it["salarie"]["statut"] == "sorti"
    and etat(p_final_it, "restitution") == "fait"
    and etape(p_final_it, "restitution")["detail"] == "Non restitue (constat)"
    and etat(p_final_it, "sorti") == "fait"
    and sorted(p_final_it["reserves"]) == sorted(res_attendues)
    and p_final_it["etape_courante"] is None
    and p_final_it["prochaine_action"] is None,
    (p_final_it["etapes"], p_final_it["reserves"]),
)

# Verification minimisation : motif visible seulement par IT
show(
    "C1bis-4e - motif de non-restitution visible uniquement de l'informatique",
    "materiels_non_restitues" in p_final_it
    and len(p_final_it["materiels_non_restitues"]) == 2
    and "motif" in p_final_it["materiels_non_restitues"][0]
    and "materiels_non_restitues" not in p_final_rh
    and "materiels_non_restitues" not in p_final_lec,
    ("IT has nr:", "materiels_non_restitues" in p_final_it, "RH has nr:", "materiels_non_restitues" in p_final_rh),
)

# Verification journal pour le constat
j_textes = [e["texte"] for e in p_final_it.get("journal", [])]
show(
    "C1bis-4f - le journal contient le constat sans mention de motif ni nom de compte",
    any("Constat de non-restitution" in t for t in j_textes)
    and not any("perte" in t or "vol" in t or "sec_ex" in t for t in j_textes),
    j_textes,
)

print("== C1bis-5 : Statut de l'actif non_restitue dans le reste de l'application ==")
# a1 doit etre non_restitue
s, a1_get = j("GET", f"/assets/{a1['id']}", token=IT_A)
show("C1bis-5a - actif conserve dans l'inventaire avec statut non_restitue", s == 200 and a1_get.get("statut") == "non_restitue", a1_get.get("statut"))

# Exclu des previsions de renouvellement
s, prevs = j("GET", "/previsions", token=IT_A)
prev_items = [item for bloc in prevs.get("repartition", []) for item in bloc.get("items", [])]
show("C1bis-5b - actif non_restitue absent des previsions", a1["id"] not in [i.get("id") for i in prev_items], prev_items)

# Reassignation impossible
s_reassign, _ = j("POST", "/assignments", {"user_id": u2["id"], "asset_ids": [a1["id"]], "sans_charte": True}, token=IT_A)
show("C1bis-5c - reassignation de l'actif non_restitue refusee (409)", s_reassign == 409, s_reassign)

# Modification manuelle du statut refusee
s_mod, _ = j("PUT", f"/assets/{a1['id']}", {**a1_get, "statut": "stock"}, token=IT_A)
show("C1bis-5d - modification manuelle de statut depuis non_restitue refusee (409)", s_mod == 409, s_mod)

# Passage direct manuel vers non_restitue refuse
s, a_test = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "numero_serie": "ZZEX-TEST-NR", "entite_id": EA})
s_mod_to_nr, _ = j("PUT", f"/assets/{a_test['id']}", {**a_test, "statut": "non_restitue"}, token=IT_A)
show("C1bis-5e - positionnement manuel du statut non_restitue refuse (409)", s_mod_to_nr == 409, s_mod_to_nr)

# Reforme en lot refuse un actif non_restitue
s_ref, r_ref = j("POST", "/assets/reforme-lot", {"ids": [a1["id"]], "simulation": True}, token=IT_A)
show("C1bis-5f - reforme d'un actif non_restitue refusee", a1["id"] in [ref["id"] for ref in r_ref.get("refuses", [])], r_ref)

print("== C1bis-6 : Cloture d'un depart sans materiel ==")
# u_sans est en_depart sans materiel
# Refus role lecture
s_clot_lec, _ = j("POST", f"/lifecycle/depart/{u_sans['id']}/cloturer", token=LEC_A)
show("C1bis-6a - cloture refusee au role lecture (403)", s_clot_lec == 403, s_clot_lec)

# Refus si le salarie detient encore du materiel (u2 detient a3)
s_clot_held, _ = j("POST", f"/lifecycle/depart/{u2['id']}/cloturer", token=IT_GL)
show("C1bis-6b - cloture refusee si le salarie a du materiel detenu (409)", s_clot_held == 409, s_clot_held)

# Refus si le salarie n'est pas en_depart (u_actif)
s_clot_actif, _ = j("POST", f"/lifecycle/depart/{u_actif['id']}/cloturer", token=IT_A)
show("C1bis-6c - cloture refusee pour un salarie actif (409)", s_clot_actif == 409, s_clot_actif)

# Cloture par RH sur u_sans
s_clot_rh, r_clot_rh = j("POST", f"/lifecycle/depart/{u_sans['id']}/cloturer", token=RH_A)
show("C1bis-6d - cloture acceptee pour les RH sur un salarie sans materiel (200)", s_clot_rh == 200 and r_clot_rh.get("statut") == "sorti", r_clot_rh)

# Re-cloture refusee (deja sorti)
s_reclot, _ = j("POST", f"/lifecycle/depart/{u_sans['id']}/cloturer", token=RH_A)
show("C1bis-6e - re-cloture d'un salarie deja sorti refusee (409)", s_reclot == 409, s_reclot)

# Cloture par informatique sur un autre salarie u_sans2
s, u_sans2 = j("POST", "/users", {"matricule": "ZZEX-US2", "nom": "ZZEXUS2", "prenom": "Sans2", "entite_id": EA, "statut": "actif"})
j("POST", f"/lifecycle/depart/{u_sans2['id']}", {"date_sortie": sortie_future})
s_clot_it, r_clot_it = j("POST", f"/lifecycle/depart/{u_sans2['id']}/cloturer", token=IT_A)
show("C1bis-6f - cloture acceptee pour l'informatique sur salarie sans materiel (200)", s_clot_it == 200 and r_clot_it.get("statut") == "sorti", r_clot_it)

print("== C1bis-7 : Journal d'audit (sans donnees personnelles ni numeros de serie) ==")
with Session(engine) as session:
    logs_constat = session.exec(select(AuditLog).where(AuditLog.action == "constat_non_restitution")).all()
    logs_cloture = session.exec(select(AuditLog).where(AuditLog.action == "depart_cloture")).all()

show(
    "C1bis-7a - presence des logs d'audit pour constat et cloture",
    len(logs_constat) > 0 and len(logs_cloture) > 0,
    f"{len(logs_constat)} constats, {len(logs_cloture)} clotures",
)

no_personal = True
for l in logs_constat + logs_cloture:
    txt = (l.target or "") + " " + (l.detail or "")
    if "Alice" in txt or "ZZEXU1" in txt or "ZZEX-SN" in txt:
        no_personal = False
        break
show("C1bis-7b - aucun nom de salarie ni numero de serie dans les logs d'audit", no_personal)

print("== Cas limite 1 : Constat partiel suivi d'une restitution signee du reste ==")
s, u_mix = j("POST", "/users", {"matricule": "ZZEX-UM", "nom": "ZZEXUM", "prenom": "Mixte", "entite_id": EA, "statut": "actif"})
s, am1 = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "numero_serie": "ZZEX-SN-M1", "entite_id": EA})
s, am2 = j("POST", "/assets", {"type": "Casque", "marque": "ZZEX", "numero_serie": "ZZEX-SN-M2", "entite_id": EA})
j("POST", "/assignments", {"user_id": u_mix["id"], "asset_ids": [am1["id"], am2["id"]], "sans_charte": True})
j("POST", f"/lifecycle/depart/{u_mix['id']}", {"date_sortie": sortie_future})

# Constat sur am1
j("POST", "/lifecycle/non-restitue", {"user_id": u_mix["id"], "asset_ids": [am1["id"]], "motif": "perte"}, token=IT_A)
# Restitution signee sur am2
j("POST", "/lifecycle/restituer", {"user_id": u_mix["id"], "asset_ids": [am2["id"]], **SIGN}, token=IT_A)

_, p_mix = parcours(u_mix["id"], IT_A)
show(
    "Cas limite 1 - mix constat et restitution : etape 3 = 'Restitue (signe) et non restitue (constat)', salarie sorti",
    p_mix["salarie"]["statut"] == "sorti"
    and etat(p_mix, "restitution") == "fait"
    and etape(p_mix, "restitution")["detail"] == "Restitue (signe) et non restitue (constat)"
    and "1 materiel(s) non restitue(s)" in p_mix["reserves"],
    (etape(p_mix, "restitution")["detail"], p_mix["reserves"]),
)

print("== C1bis-8 : Purge RGPD et reversibilite de la migration ==")
# 1. Purge RGPD
s, u_pg = j("POST", "/users", {"matricule": "ZZEX-UPG", "nom": "ZZEXUPG", "prenom": "Purger", "entite_id": EA, "statut": "actif"})
s, a_pg = j("POST", "/assets", {"type": "PC", "marque": "ZZEX", "numero_serie": "ZZEX-SN-PG", "entite_id": EA})
j("POST", "/assignments", {"user_id": u_pg["id"], "asset_ids": [a_pg["id"]], "sans_charte": True})
# Sortie passee pour que le salarie soit candidat a la purge
date_old = (date.today() - timedelta(days=400)).isoformat()
j("POST", f"/lifecycle/depart/{u_pg['id']}", {"date_sortie": date_old})
j("POST", "/lifecycle/non-restitue", {"user_id": u_pg["id"], "asset_ids": [a_pg["id"]], "motif": "refus_de_restituer"}, token=IT_A)

with Session(engine) as session:
    # Verifie presence des colonnes avant purge
    links_before = session.exec(select(AssignmentAsset).where(AssignmentAsset.asset_id == a_pg["id"])).all()
    has_nr_data = any(l.non_restitue_le is not None and l.motif_non_restitution == "refus_de_restituer" for l in links_before)
    purger(session, "test_admin", [u_pg["id"]])

    # Verifie absence de la ligne assignment_asset apres purge
    links_after = session.exec(select(AssignmentAsset).where(AssignmentAsset.asset_id == a_pg["id"])).all()
    asset_after = session.get(Asset, a_pg["id"])

s_purg, _ = parcours(u_pg["id"], IT_A)
show(
    "C1bis-8a - RGPD purge supprime les donnees non_restitue d'affectation et laisse l'actif non_restitue dans l'inventaire",
    has_nr_data and len(links_after) == 0 and asset_after is not None and asset_after.statut == AssetStatus.non_restitue and s_purg == 404,
    f"links_before={has_nr_data}, links_after={len(links_after)}, parcours_code={s_purg}",
)

# 2. Test Alembic de retour arriere (downgrade refuse si donnees non_restitue existantes)
cfg = Config("/app/alembic.ini")
downgrade_refused = False
try:
    command.downgrade(cfg, "-1")
except RuntimeError as exc:
    downgrade_refused = "non_restitue" in str(exc)
except Exception:
    downgrade_refused = False

show("C1bis-8b - descente de migration refusee si des actifs ont le statut non_restitue", downgrade_refused)

# Nettoyage temporaire des actifs non_restitue pour tester la migration aller-retour complete
with Session(engine) as session:
    for a in session.exec(select(Asset).where(Asset.statut == AssetStatus.non_restitue)).all():
        a.statut = AssetStatus.stock
        session.add(a)
    session.commit()

migration_cycle_ok = False
try:
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    migration_cycle_ok = True
except Exception as e:
    migration_cycle_ok = False
    print("Erreur cycle migration:", e)

show("C1bis-8c - cycle de migration descente puis remontee reussi sans donnees", migration_cycle_ok)

print("== Bilan de la suite depart_exception_check ==")
print(f"Total echecs : {fails}")
if fails > 0:
    sys.exit(1)
print("Tous les tests du lot 1bis ont reussi.")
