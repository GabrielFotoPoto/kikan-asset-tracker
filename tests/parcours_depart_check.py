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

"""Parcours de depart (GET /parcours/depart/{id}) : Lot 1 de SPEC.md 6.3bis.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kiktest-api python - < tests/parcours_depart_check.py

Cree des donnees ZZDP et des comptes sec_dp_* (nettoyage : tests/cleanup_test_data.sql).
Couvre les 19 criteres d'acceptation du lot 1. Code de sortie 1 si un test echoue. ASCII uniquement.
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
from sqlalchemy import event  # noqa: E402
from sqlmodel import Session, func, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Account, Asset, Assignment, AssignmentAsset, AuditLog, Signature, User, UserApplication  # noqa: E402
from app.purge import add_months  # noqa: E402
from app.routers.parcours import parcours_depart  # noqa: E402
from app.scope import compute_scope  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
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
    return j("GET", "/parcours/depart/%d" % uid, token=token)


def etape(r, cle):
    return next((e for e in r.get("etapes", []) if e["cle"] == cle), None)


def etat(r, cle):
    e = etape(r, cle)
    return e["etat"] if e else None


print("== Organisation et comptes de test ==")
ent = {}
for code, parent in [("ZZDP-G", None), ("ZZDP-A", "ZZDP-G"), ("ZZDP-B", "ZZDP-G")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZDP-A"], ent["ZZDP-B"]

account("sec_dp_it", "informatique")
account("sec_dp_rh0", "rh")
account("sec_dp_rhA", "rh", portee_globale=False, entites=[EA])
account("sec_dp_rhB", "rh", portee_globale=False, entites=[EB])
account("sec_dp_lecA", "lecture", portee_globale=False, entites=[EA])
IT, R0, RA, RB, LA = (login(n, PW) for n in ("sec_dp_it", "sec_dp_rh0", "sec_dp_rhA", "sec_dp_rhB", "sec_dp_lecA"))
show("connexions de test (IT, RH sans portee, RH A, RH B, lecture A)", all([IT, R0, RA, RB, LA]))

s, b_anon = call("GET", "/parcours/depart/1")
show("sans jeton : refuse (401)", s in (401, 403), s)

print("== Critere 14 : salarie actif ou prevu (aucun depart declare) ==")
s, u_prev = j("POST", "/users", {
    "matricule": "ZZDP-UPREV", "nom": "ZZDPPrev", "prenom": "Paul",
    "email": "paul.zzdp@exemple.test", "service": "ZZDP-Svc",
    "entite_id": EA, "statut": "prevu", "date_arrivee": "2026-12-01",
})
s, u_act = j("POST", "/users", {
    "matricule": "ZZDP-UACT", "nom": "ZZDPAct", "prenom": "Alice",
    "email": "alice.zzdp@exemple.test", "service": "ZZDP-Svc",
    "entite_id": EA, "statut": "actif",
})
for label, uid in [("prevu", u_prev["id"]), ("actif", u_act["id"])]:
    s, r = parcours(uid, RA)
    etats_autres = [e["etat"] for e in r.get("etapes", []) if e["cle"] != "depart"]
    show(
        f"C14 - salarie {label} : HTTP 200, etape 1 courante, autres a_venir",
        s == 200 and etat(r, "depart") == "courante" and r.get("etape_courante") == "depart"
        and all(x == "a_venir" for x in etats_autres)
        and r.get("prochaine_action", {}).get("vers") == f"/sorties?user={uid}",
        (s, [e["etat"] for e in r.get("etapes", [])]),
    )

print("== Critere 3 : portee par entite et 404 identique ==")
s, u_b = j("POST", "/users", {
    "matricule": "ZZDP-UB", "nom": "ZZDPNomB", "prenom": "Bruno",
    "entite_id": EB, "statut": "actif",
})
s_inex, b_inex = call("GET", "/parcours/depart/99999999", token=RA)
s_hors, b_hors = call("GET", f"/parcours/depart/{u_b['id']}", token=RA)
s_r0, b_r0 = call("GET", f"/parcours/depart/{u_act['id']}", token=R0)
s_la_b, b_la_b = call("GET", f"/parcours/depart/{u_b['id']}", token=LA)
show(
    "C3 - RH hors portee : 404 et corps identique a un id inexistant",
    s_inex == 404 and s_hors == 404 and b_inex == b_hors and s_r0 == 404 and s_la_b == 404,
    (s_inex, s_hors, b_inex.decode(), b_hors.decode()),
)

print("== Preparation du salarie principal (2 actifs, 1 acces actif, 1 acces retire) ==")
s, a1 = j("POST", "/assets", {
    "identifiant_interne": "ZZDP-PC-01", "type": "Ordinateur portable",
    "marque": "ZZDPMarque", "modele": "ModX1", "numero_serie": "ZZDP-SN-001", "entite_id": EA,
})
s, a2 = j("POST", "/assets", {
    "identifiant_interne": "ZZDP-ECR-02", "type": "Ecran",
    "marque": "ZZDPMarque", "modele": "ModE2", "numero_serie": "ZZDP-SN-002", "entite_id": EA,
})
s, app1 = j("POST", "/applications", {"nom": "ZZDP-App-Active", "entite_id": None})
s, app2 = j("POST", "/applications", {"nom": "ZZDP-App-Retiree", "entite_id": None})
UA = u_act["id"]
s, asg1 = j("POST", "/assignments", {"user_id": UA, "asset_ids": [a1["id"], a2["id"]], "sans_charte": True})
j("POST", f"/assignments/{asg1['id']}/sign", SIGN)
j("POST", f"/users/{UA}/applications", {"application_id": app1["id"], "acces": True})
j("POST", f"/users/{UA}/applications", {"application_id": app2["id"], "acces": True})
j("POST", f"/users/{UA}/applications", {"application_id": app2["id"], "acces": False})

print("== Critere 15 : non-regression sur GET /lifecycle/holdings/{id} et POST /lifecycle/depart/{id} ==")
s_h_rh, h_rh = j("GET", f"/lifecycle/holdings/{UA}", token=RA)
s_h_it, h_it = j("GET", f"/lifecycle/holdings/{UA}", token=IT)
s_h_hors, _ = j("GET", f"/lifecycle/holdings/{u_b['id']}", token=RA)
s_h_lec, h_lec = j("GET", f"/lifecycle/holdings/{UA}", token=LA)
show(
    "C15a - GET /lifecycle/holdings/{id} inchange (IT/RH/lecture autorises dans portee, hors portee 404)",
    s_h_rh == 200 and len(h_rh) == 2 and s_h_it == 200 and len(h_it) == 2
    and s_h_lec == 200 and len(h_lec) == 2 and s_h_hors == 404,
    (s_h_rh, s_h_it, s_h_hors, s_h_lec),
)
sortie_future = (date.today() + timedelta(days=10)).isoformat()
s_dep_lec, _ = j("POST", f"/lifecycle/depart/{UA}", {"date_sortie": sortie_future}, token=LA)
s_dep_hors, _ = j("POST", f"/lifecycle/depart/{u_b['id']}", {"date_sortie": sortie_future}, token=RA)
s_dep_rh, dep_rh = j("POST", f"/lifecycle/depart/{UA}", {"date_sortie": sortie_future}, token=RA)
show(
    "C15b - POST /lifecycle/depart/{id} inchange (RH dans portee 200, hors portee 404, lecture 403)",
    s_dep_lec == 403 and s_dep_hors == 404 and s_dep_rh == 200
    and dep_rh.get("statut") == "en_depart" and len(dep_rh.get("materiel_a_recuperer", [])) == 2,
    (s_dep_lec, s_dep_hors, s_dep_rh, dep_rh),
)

print("== Critere 1 : salarie en_depart avec 2 actifs et 1 acces actif ==")
s, r_rh = parcours(UA, RA)
e_restit = etape(r_rh, "restitution")
show(
    "C1 - etape 3 (restitution) courante et detail annonce 2 materiel(s) restant(s)",
    s == 200 and etat(r_rh, "depart") == "fait" and etat(r_rh, "materiel") == "fait"
    and etat(r_rh, "restitution") == "courante" and r_rh["etape_courante"] == "restitution"
    and e_restit is not None and "2 materiel(s) restant(s)" in e_restit["detail"]
    and "sur" not in e_restit["detail"]
    and etat(r_rh, "acces") == "a_venir" and r_rh["acces_restants"] == 1,
    e_restit,
)

print("== Critere 4 & Critere 7 : donnees de materiel visibles aux RH, absence de matricule et d'email ==")
mats = r_rh.get("materiel_a_recuperer", [])
show(
    "C4 - RH dans sa portee voit type, marque, modele et numero_serie du materiel a recuperer",
    len(mats) == 2 and all(
        set(m.keys()) == {"id", "identifiant_interne", "type", "marque", "modele", "numero_serie"} for m in mats
    ) and {m["numero_serie"] for m in mats} == {"ZZDP-SN-001", "ZZDP-SN-002"},
    mats,
)
for role_label, tok in [("IT", IT), ("RH", RA), ("lecture", LA)]:
    _, raw_bytes = call("GET", f"/parcours/depart/{UA}", token=tok)
    raw_txt = raw_bytes.decode()
    parsed = json.loads(raw_txt)
    show(
        f"C4/C7 - ni matricule ni email dans la reponse ({role_label})",
        "matricule" not in parsed["salarie"] and "email" not in parsed["salarie"]
        and "ZZDP-UACT" not in raw_txt and "alice.zzdp@exemple.test" not in raw_txt
        and set(parsed["salarie"].keys()) == {"id", "nom", "prenom", "service", "entite_id", "statut", "date_sortie"},
        sorted(parsed["salarie"].keys()),
    )

print("== Critere 5 : etape 6 (purge) presente pour IT, absente pour RH et lecture ==")
_, b_rh_raw = call("GET", f"/parcours/depart/{UA}", token=RA)
_, b_la_raw = call("GET", f"/parcours/depart/{UA}", token=LA)
_, r_it = parcours(UA, IT)
_, r_la = parcours(UA, LA)
cles_it = [e["cle"] for e in r_it["etapes"]]
cles_rh = [e["cle"] for e in r_rh["etapes"]]
cles_la = [e["cle"] for e in r_la["etapes"]]
show(
    "C5a - etape purge presente pour informatique (6 etapes), absente pour RH et lecture (5 etapes)",
    cles_it == ["depart", "materiel", "restitution", "acces", "sorti", "purge"]
    and cles_rh == ["depart", "materiel", "restitution", "acces", "sorti"]
    and cles_la == ["depart", "materiel", "restitution", "acces", "sorti"],
    (cles_it, cles_rh, cles_la),
)
show(
    "C5b - la reponse d'un RH et du role lecture ne contient jamais date_purge_possible",
    "date_purge_possible" not in b_rh_raw.decode() and "date_purge_possible" not in b_la_raw.decode(),
)

print("== Critere 6 : role lecture voit le parcours avec prochaine_action.autorise = false ==")
show(
    "C6 - role lecture : prochaine_action.autorise est False (et True pour RH et IT)",
    r_la["prochaine_action"] is not None and r_la["prochaine_action"]["autorise"] is False
    and r_rh["prochaine_action"]["autorise"] is True and r_it["prochaine_action"]["autorise"] is True,
    (r_la["prochaine_action"], r_rh["prochaine_action"]),
)

print("== Critere 8 : aucune ecriture en base lors de GET /parcours/depart/{id} ==")
TABLES_SURVEILLEES = (User, Asset, Assignment, AssignmentAsset, Signature, UserApplication, AuditLog)


def snapshot_db(uid):
    with Session(engine) as ss:
        u = ss.get(User, uid)
        counts = {m.__tablename__: ss.exec(select(func.count()).select_from(m)).one() for m in TABLES_SURVEILLEES}
        return u.maj_le, counts


maj_before, counts_before = snapshot_db(UA)
for _ in range(3):
    parcours(UA, IT)
    parcours(UA, RA)
    parcours(UA, LA)
maj_after, counts_after = snapshot_db(UA)
show(
    "C8 - GET /parcours/depart/{id} ne modifie ni maj_le ni aucune des 7 tables surveillees",
    maj_before == maj_after and counts_before == counts_after,
    (str(maj_before), str(maj_after), counts_before, counts_after),
)

print("== Critere 11 : date de l'etape 6 = date_sortie + retention_apres_sortie_mois (sans delai_grace), toujours a_venir ==")
j("PUT", "/rgpd/retention", {"mois": 18, "delai_grace_jours": 45})
_, r_it_ret = parcours(UA, IT)
e_purge = etape(r_it_ret, "purge")
attendu_purge = add_months(date.fromisoformat(sortie_future), 18).isoformat()
show(
    "C11a - avant l'echeance : etat a_venir, detail 'Purge possible a partir du <date>' (sans delai de grace)",
    e_purge is not None and e_purge.get("etat") == "a_venir"
    and e_purge.get("date_purge_possible") == attendu_purge
    and f"Purge possible a partir du {attendu_purge}" == e_purge.get("detail"),
    e_purge,
)
j("PUT", "/rgpd/retention", {"mois": 12, "delai_grace_jours": 30})

print("== Critere 17 : date de sortie depassee indique le retard en jours ==")
sortie_passee = (date.today() - timedelta(days=5)).isoformat()
j("POST", f"/lifecycle/depart/{UA}", {"date_sortie": sortie_passee}, token=RA)
_, r_retard = parcours(UA, RA)
e_rest_ret = etape(r_retard, "restitution")
show(
    "C17 - date_sortie passee de 5 jours : detail et retard_jours = 5",
    e_rest_ret is not None and e_rest_ret.get("retard_jours") == 5
    and "en retard de 5 jour(s)" in e_rest_ret.get("detail", ""),
    e_rest_ret,
)

print("== Critere 13 & Critere 2 : restitution en deux signatures distinctes (2 -> 1 -> 0 et sorti avec reserve) ==")
s_r1, _ = j("POST", "/lifecycle/restituer", {"user_id": UA, "asset_ids": [a1["id"]], **SIGN}, token=RA)
_, r_apres_1 = parcours(UA, RA)
e_rest_1 = etape(r_apres_1, "restitution")
show(
    "C13a - apres 1re restitution signee : 1 materiel(s) restant(s), toujours en_depart",
    s_r1 == 201 and r_apres_1["salarie"]["statut"] == "en_depart"
    and etat(r_apres_1, "restitution") == "courante"
    and "1 materiel(s) restant(s)" in e_rest_1.get("detail", "")
    and len(r_apres_1["materiel_a_recuperer"]) == 1
    and r_apres_1["materiel_a_recuperer"][0]["id"] == a2["id"],
    e_rest_1,
)

s_r2, _ = j("POST", "/lifecycle/restituer", {"user_id": UA, "asset_ids": [a2["id"]], **SIGN}, token=RA)
_, r_apres_2 = parcours(UA, RA)
show(
    "C13b & C2 - apres 2nde restitution signee : salarie sorti, parcours termine, reserve '1 acces a retirer'",
    s_r2 == 201 and r_apres_2["salarie"]["statut"] == "sorti"
    and etat(r_apres_2, "restitution") == "fait"
    and etat(r_apres_2, "sorti") == "fait"
    and r_apres_2["etape_courante"] is None
    and r_apres_2["prochaine_action"] is None
    and r_apres_2["materiel_a_recuperer"] == []
    and r_apres_2["reserves"] == ["1 acces a retirer"],
    (r_apres_2["salarie"]["statut"], r_apres_2["etape_courante"], r_apres_2["reserves"]),
)

print("== Critere 19 : journal horodate uniquement sur faits stockes, sans donnees sensibles ni 'depart declare' ni retrait d'acces deduit ==")
journal = r_apres_2.get("journal", [])
journal_txt = json.dumps(journal)
show(
    "C19a - journal contient les restitutions signees et les retours par type, et omet le retrait d'acces sans date stockee",
    any(x["texte"] == "Restitution signee et scellee" for x in journal)
    and any(x["texte"] == "Materiel restitue : Ordinateur portable" for x in journal)
    and any(x["texte"] == "Materiel restitue : Ecran" for x in journal)
    and not any("Acces applicatif retire" in x["texte"] for x in journal),
    journal,
)
show(
    "C19b - journal sans 'depart declare', ni nom de compte/temoin, ni nom d'application, ni numero de serie",
    "depart" not in journal_txt.lower()
    and "sec_dp" not in journal_txt
    and "admin" not in journal_txt.lower()
    and "ZZDP-App" not in journal_txt
    and "ZZDP-SN" not in journal_txt
    and "ZZDP-PC" not in journal_txt,
    journal_txt,
)

print("== Critere 12 : salarie en_depart sans aucun materiel detenu ==")
s, u_sans = j("POST", "/users", {
    "matricule": "ZZDP-USANS", "nom": "ZZDPSans", "prenom": "Sophie",
    "entite_id": EA, "statut": "actif",
})
j("POST", f"/lifecycle/depart/{u_sans['id']}", {"date_sortie": sortie_future}, token=RA)
s, r_sans = parcours(u_sans["id"], RA)
_, r_sans_la = parcours(u_sans["id"], LA)
show(
    "C12 - salarie en_depart sans materiel : etape 2 sans_objet, etape 3 fait, cloture disponible, prochaine_action autorisee pour RH mais pas pour lecture",
    s == 200 and etat(r_sans, "materiel") == "sans_objet"
    and etat(r_sans, "restitution") == "fait"
    and etape(r_sans, "restitution")["detail"] == "Aucun materiel"
    and etat(r_sans, "sorti") == "a_venir"
    and etape(r_sans, "sorti")["detail"] == "En attente de cloture"
    and r_sans.get("message_attente") is None
    and r_sans.get("etape_courante") is None
    and r_sans.get("prochaine_action", {}).get("action_id") == "cloturer_depart"
    and r_sans.get("prochaine_action", {}).get("autorise") is True
    and r_sans_la.get("prochaine_action", {}).get("autorise") is False,
    (r_sans.get("etapes"), r_sans.get("prochaine_action"), r_sans_la.get("prochaine_action")),
)

print("== Critere 16 : un role ne recoit aucune donnee qu'il n'obtient pas deja via les routes existantes ==")
_, u_fiche = j("GET", f"/users/{u_sans['id']}", token=LA)
_, r_sans_la = parcours(u_sans["id"], LA)
show(
    "C16 - les champs salarie de /parcours/depart sont un sous-ensemble strict de GET /users/{id} et sans purge pour RH/lecture",
    set(r_sans_la["salarie"].keys()).issubset(set(u_fiche.keys()))
    and "purge" not in [e["cle"] for e in r_sans_la["etapes"]]
    and "purge" not in [e["cle"] for e in r_rh["etapes"]],
    (sorted(r_sans_la["salarie"].keys()), [e["cle"] for e in r_sans_la["etapes"]]),
)

print("== Critere 18 : nombre de requetes SQL borne et independant du nombre d'actifs (IT global et RH restreint) ==")
s, u_1 = j("POST", "/users", {"matricule": "ZZDP-UQ1", "nom": "ZZDPQ1", "prenom": "Un", "entite_id": EA, "statut": "actif"})
s, u_10 = j("POST", "/users", {"matricule": "ZZDP-UQ10", "nom": "ZZDPQ10", "prenom": "Dix", "entite_id": EA, "statut": "actif"})
s, aq1 = j("POST", "/assets", {"type": "PC", "marque": "ZZDP", "numero_serie": "ZZDP-SN-Q0", "entite_id": EA})
j("POST", "/assignments", {"user_id": u_1["id"], "asset_ids": [aq1["id"]], "sans_charte": True})
j("POST", f"/lifecycle/depart/{u_1['id']}", {"date_sortie": sortie_future})

ids_10 = []
for k in range(1, 11):
    _, ak = j("POST", "/assets", {"type": "PC", "marque": "ZZDP", "numero_serie": f"ZZDP-SN-Q{k}", "entite_id": EA})
    ids_10.append(ak["id"])
j("POST", "/assignments", {"user_id": u_10["id"], "asset_ids": ids_10, "sans_charte": True})
j("POST", f"/lifecycle/depart/{u_10['id']}", {"date_sortie": sortie_future})


def count_queries(uid, username):
    cnt = [0]

    def before_exec(conn, cursor, statement, parameters, context, executemany):
        cnt[0] += 1

    with Session(engine) as ss:
        acc = ss.exec(select(Account).where(Account.username == username)).first()
        event.listen(engine, "before_cursor_execute", before_exec)
        try:
            sc = compute_scope(ss, acc)
            parcours_depart(uid, session=ss, account=acc, scope=sc)
        finally:
            event.remove(engine, "before_cursor_execute", before_exec)
    return cnt[0]


q1_it = count_queries(u_1["id"], "sec_dp_it")
q10_it = count_queries(u_10["id"], "sec_dp_it")
q1_rh = count_queries(u_1["id"], "sec_dp_rha")
q10_rh = count_queries(u_10["id"], "sec_dp_rha")
show(
    "C18a - IT (portee globale) : nombre de requetes SQL constant entre 1 actif et 10 actifs (<= 6 requetes)",
    q1_it == q10_it and q1_it <= 6,
    f"1 actif: {q1_it} requetes, 10 actifs: {q10_it} requetes",
)
show(
    "C18b - RH (portee limitee a une entite) : nombre de requetes SQL constant entre 1 actif et 10 actifs (<= 8 requetes)",
    q1_rh == q10_rh and q1_rh <= 8,
    f"1 actif: {q1_rh} requetes, 10 actifs: {q10_rh} requetes",
)

print("== Critere 11b & Critere 10 : etape 6 apres la date de purge (reste a_venir, 'depuis le') puis 404 apres purge RGPD ==")
s, u_purge = j("POST", "/users", {"matricule": "ZZDP-UPG", "nom": "ZZDPPurge", "prenom": "Pia", "entite_id": EA, "statut": "actif"})
s, apg = j("POST", "/assets", {"type": "PC", "marque": "ZZDP", "numero_serie": "ZZDP-SN-PG", "entite_id": EA})
s, asg_pg = j("POST", "/assignments", {"user_id": u_purge["id"], "asset_ids": [apg["id"]], "sans_charte": True})
j("POST", f"/assignments/{asg_pg['id']}/sign", SIGN)
j("POST", f"/lifecycle/depart/{u_purge['id']}", {"date_sortie": "2019-01-01"})
j("POST", "/lifecycle/restituer", {"user_id": u_purge["id"], **SIGN})
s_av, r_av = parcours(u_purge["id"], IT)
e_pg_echu = etape(r_av, "purge")
show(
    "C11b - apres l'echeance de retention : l'etape 6 reste a_venir avec 'Purge possible depuis le 2020-01-01'",
    s_av == 200 and e_pg_echu is not None and e_pg_echu.get("etat") == "a_venir"
    and e_pg_echu.get("detail") == "Purge possible depuis le 2020-01-01"
    and e_pg_echu.get("date_purge_possible") == "2020-01-01",
    e_pg_echu,
)
s_pg, r_pg = j("POST", "/rgpd/purge", {"ids": [u_purge["id"]]}, token=IT)
s_ap_it, _ = parcours(u_purge["id"], IT)
s_ap_rh, _ = parcours(u_purge["id"], RA)
show(
    "C10 - apres purge RGPD, GET /parcours/depart/{id} renvoie 404 (IT et RH)",
    s_av == 200 and s_pg == 200 and r_pg.get("count") == 1 and s_ap_it == 404 and s_ap_rh == 404,
    (s_av, s_pg, s_ap_it, s_ap_rh),
)

print("== Critere 9 : GET /arrivee/{id} fonctionne a l'identique ==")
s_arr, r_arr = j("GET", f"/arrivee/{u_prev['id']}", token=RA)
show(
    "C9 - GET /arrivee/{id} repond 200 avec ses 5 etapes habituelles",
    s_arr == 200 and [e["cle"] for e in r_arr.get("etapes", [])] == ["fiche", "besoins", "preparation", "remise", "acces"],
    [e["cle"] for e in r_arr.get("etapes", [])],
)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
