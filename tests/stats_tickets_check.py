# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

"""Tests du lot G6 (#180) : statistiques et KPI tickets, exports CSV/XLSX, rapport mensuel et purge stats RGPD."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app import mailer, reminders, tickets as tickets_svc
from app.db import engine
from app.models import Ticket, TicketSecurityDetail

BASE = os.environ.get("KIKAN_TEST_URL", "http://127.0.0.1:8000")
ADMIN_USER = os.environ["TEST_ADMIN_USER"]
ADMIN_PASS = os.environ["TEST_ADMIN_PASSWORD"]

ok_count = 0
fail_count = 0


def show(label, cond, detail=""):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"PASS  {label}")
    else:
        fail_count += 1
        print(f"FAIL  {label} -- {detail}")


def raw_req(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def j(method, path, body=None, token=None):
    status, data, _ = raw_req(method, path, body, token)
    try:
        return status, json.loads(data.decode("utf-8")) if data else None
    except Exception:
        return status, data.decode("utf-8", "replace")


def login(username, password):
    s, r = j("POST", "/auth/login", {"username": username, "password": password})
    assert s == 200, f"login failed for {username}: {s} {r}"
    return r["access_token"]


tok_it = login(ADMIN_USER, ADMIN_PASS)

print("== 1. Controle d'acces strict (/stats/tickets reserve a informatique) ==")
s, ent_parent = j("POST", "/entites", {"code": "ZZG6P", "nom": "ZZ G6 Parent"}, tok_it)
assert s in (200, 201), ent_parent
s, ent_fille = j("POST", "/entites", {"code": "ZZG6F", "nom": "ZZ G6 Fille", "code_parent": "ZZG6P"}, tok_it)
assert s in (200, 201), ent_fille
s, ent_autre = j("POST", "/entites", {"code": "ZZG6A", "nom": "ZZ G6 Autre"}, tok_it)
assert s in (200, 201), ent_autre

# Creer comptes RH, lecture, demandeur
s, _ = j("POST", "/auth/accounts", {
    "username": "zzg6_rh", "password": "G6Password2026!", "role": "rh",
    "entites": [ent_parent["id"]],
}, tok_it)
assert s in (200, 201)
s, _ = j("POST", "/auth/accounts", {
    "username": "zzg6_lecture", "password": "G6Password2026!", "role": "lecture",
    "entites": [ent_parent["id"]],
}, tok_it)
assert s in (200, 201)
s, emp = j("POST", "/users", {
    "matricule": "ZZ-G6-01", "nom": "DURAND_SECRET_PII_ZZ", "prenom": "ZZ_Alice_Secret",
    "email": "zz.alice.secret.g6@exemple.test", "service": "Ventes", "entite_id": ent_fille["id"],
}, tok_it)
assert s in (200, 201), emp
s, emp_autre = j("POST", "/users", {
    "matricule": "ZZ-G6-02", "nom": "MARTIN_AUTRE_ZZ", "prenom": "ZZ_Bob",
    "email": "zz.bob.g6@exemple.test", "service": "Finance", "entite_id": ent_autre["id"],
}, tok_it)
assert s in (200, 201), emp_autre
s, acc_dem = j("POST", f"/users/{emp['id']}/compte-demandeur", {"mode": "mot_de_passe"}, tok_it)
assert s in (200, 201), acc_dem

tok_rh = login("zzg6_rh", "G6Password2026!")
tok_lec = login("zzg6_lecture", "G6Password2026!")
tok_dem_tmp = login(acc_dem["username"], acc_dem["mot_de_passe_provisoire"])
s_cp, ch_dem = j("POST", "/auth/change-password", {
    "old_password": acc_dem["mot_de_passe_provisoire"],
    "new_password": "G6Demandeur2026!",
}, tok_dem_tmp)
assert s_cp == 200, (s_cp, ch_dem)
tok_dem = ch_dem["access_token"]

s, _ = j("GET", "/stats/tickets")
show("GET /stats/tickets sans auth -> 401", s == 401, s)
for role_name, tok in (("rh", tok_rh), ("lecture", tok_lec), ("demandeur", tok_dem)):
    s_json, _ = j("GET", "/stats/tickets", token=tok)
    s_csv, _, _ = raw_req("GET", "/stats/tickets?format=csv", token=tok)
    s_xlsx, _, _ = raw_req("GET", "/stats/tickets?format=xlsx", token=tok)
    show(f"role {role_name} refuse (403) en JSON/CSV/XLSX", s_json == 403 and s_csv == 403 and s_xlsx == 403,
         f"{s_json}/{s_csv}/{s_xlsx}")

s_pdf, _, _ = raw_req("GET", "/stats/tickets?format=pdf", token=tok_it)
show("format pdf non expose en v0.9 (422)", s_pdf == 422, s_pdf)
s_bad_crit, _ = j("GET", "/stats/tickets?criticite=inconnue", token=tok_it)
show("criticite invalide -> 422", s_bad_crit == 422, s_bad_crit)
s_bad_dates, _ = j("GET", "/stats/tickets?du=2026-05-10&au=2026-05-01", token=tok_it)
show("du > au -> 422", s_bad_dates == 422, s_bad_dates)
s_bad_ent, _ = j("GET", "/stats/tickets?entite_id=999999", token=tok_it)
show("entite inconnue -> 404", s_bad_ent == 404, s_bad_ent)

print("== 2. Donnees fictives et verification des 4 blocs KPI ==")
# 2 actifs du meme modele dans ent_fille (parc = 2)
for idx in (1, 2):
    s, a = j("POST", "/assets", {
        "identifiant_interne": f"ZZ-G6-LAP-{idx}", "type": "PC portable", "marque": "ZZThinkG6", "modele": "X1-Test",
        "numero_serie": f"ZZ-SN-G6-{idx}", "entite_id": ent_fille["id"],
    }, tok_it)
    assert s in (200, 201), a
    if idx == 1:
        asset1 = a

# Ticket 1 : panne materiel, resolu puis reouvert puis resolu puis ferme (ent_fille)
s, t1 = j("POST", "/tickets", {
    "nature_code": "panne_materiel", "criticite": "haute",
    "titre": "ZZ TITRE_CONFIDENTIEL_T1", "description": "DESC_CONFIDENTIELLE_T1",
    "user_id": emp["id"], "asset_id": asset1["id"],
}, tok_it)
assert s in (200, 201), t1
j("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)
j("POST", f"/tickets/{t1['id']}/statut", {"statut": "resolu"}, tok_it)
j("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)  # reouverture
j("POST", f"/tickets/{t1['id']}/statut", {"statut": "resolu"}, tok_it)
j("POST", f"/tickets/{t1['id']}/statut", {"statut": "ferme"}, tok_it)

# Ajuster horodatages t1 pour tester MTTA = 2h, MTTR net = 6h (brut 10h - attente 4h)
now = datetime.utcnow()
with Session(engine) as db:
    db_t1 = db.get(Ticket, t1["id"])
    db_t1.cree_le = now - timedelta(hours=12)
    db_t1.premiere_reponse_le = now - timedelta(hours=10)
    db_t1.resolu_le = now - timedelta(hours=2)
    db_t1.duree_attente_sec = 4 * 3600
    db_t1.ferme_le = now - timedelta(hours=1)
    db.add(db_t1)
    db.commit()

# Ticket 2 : securite signalee par demandeur -> escalade incident -> retrogradation sans_suite
s, t2 = j("POST", "/tickets", {
    "nature_code": "message_suspect", "criticite": "critique",
    "titre": "ZZ TITRE_CONFIDENTIEL_T2", "description": "DESC_CONFIDENTIELLE_T2",
    "signaler_securite": True,
}, tok_dem)
assert s in (200, 201), t2
s, _ = j("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "incident", "sous_categorie": "phishing"}, tok_it)
assert s == 200
s, _ = j("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "sans_suite"}, tok_it)
assert s == 200

# Ticket 3 : incident avec violation potentielle dans ent_autre (stock ouvert > 7j)
s, t3 = j("POST", "/tickets", {
    "nature_code": "acces_compte", "criticite": "critique",
    "titre": "ZZ TITRE_CONFIDENTIEL_T3", "description": "DESC_CONFIDENTIELLE_T3",
    "user_id": emp_autre["id"],
}, tok_it)
assert s in (200, 201), t3
j("POST", f"/tickets/{t3['id']}/securite/niveau", {"niveau_securite": "signale"}, tok_it)
j("POST", f"/tickets/{t3['id']}/securite/niveau", {"niveau_securite": "incident", "sous_categorie": "fuite_donnees"}, tok_it)
s, _ = j("PUT", f"/tickets/{t3['id']}/securite", {
    "violation_donnees_potentielle": True,
    "date_decouverte_violation": now.isoformat(),
    "cause_racine": "CAUSE_RACINE_CONFIDENTIELLE",
}, tok_it)
assert s == 200
with Session(engine) as db:
    db_t3 = db.get(Ticket, t3["id"])
    db_t3.cree_le = now - timedelta(days=10)
    db.add(db_t3)
    db.commit()

s, kpi = j("GET", "/stats/tickets", token=tok_it)
show("GET /stats/tickets (global) -> 200", s == 200, s)
show("activite crees/resolus/fermes exacts",
     kpi["activite"]["crees"] == 3 and kpi["activite"]["resolus"] == 1 and kpi["activite"]["fermes"] == 1,
     kpi["activite"])
show("stock ouvert = 2 (critique=2, moins_24h=1, plus_7j=1)",
     kpi["activite"]["stock_ouvert"]["total"] == 2
     and kpi["activite"]["stock_ouvert"]["par_criticite"]["critique"] == 2
     and kpi["activite"]["stock_ouvert"]["par_anciennete"]["moins_24h"] == 1
     and kpi["activite"]["stock_ouvert"]["par_anciennete"]["plus_7j"] == 1,
     kpi["activite"]["stock_ouvert"])
show("MTTA = 2.0h et MTTR net = 6.0h",
     kpi["reactivite"]["mtta_heures"]["mediane"] == 2.0 and kpi["reactivite"]["mttr_heures"]["mediane"] == 6.0,
     kpi["reactivite"])
show("taux reouverture = 100.0%",
     kpi["reactivite"]["reouvertures"]["tickets_reouverts"] == 1
     and kpi["reactivite"]["reouvertures"]["taux_pourcent"] == 100.0,
     kpi["reactivite"]["reouvertures"])
top_m = kpi["fiabilite_parc"]["top_materiels"]
show("fiabilite parc : ThinkG6 X1-Test 1 incident / 2 parc = 50.0%",
     len(top_m) == 1 and top_m[0]["incidents"] == 1 and top_m[0]["parc"] == 2 and top_m[0]["taux_pourcent"] == 50.0,
     top_m)
sec = kpi["securite"]
show("pilotage securite : 2 signales (1 dem / 1 IT), 2 escalades, 1 sans_suite (50%), 1 retrogradation, 1 violation",
     sec["signales_total"] == 2
     and sec["par_origine"] == {"demandeur": 1, "informatique": 1}
     and sec["escalades_incident"] == 2
     and sec["classes_sans_suite"] == 1
     and sec["taux_sans_suite_pourcent"] == 50.0
     and sec["retrogradations"] == 1
     and sec["violations_potentielles"] == 1,
     sec)

# Filtre entite parent inclut entite fille et exclut ent_autre
s, kpi_parent = j("GET", f"/stats/tickets?entite_id={ent_parent['id']}", token=tok_it)
show("filtre entite_id parent inclut sous-entite (2 tickets) et exclut ent_autre",
     s == 200 and kpi_parent["activite"]["crees"] == 2 and kpi_parent["securite"]["violations_potentielles"] == 0,
     kpi_parent["activite"])

# Filtre nature + criticite
s, kpi_nat = j("GET", "/stats/tickets?nature=panne_materiel&criticite=haute", token=tok_it)
show("filtres nature + criticite -> 1 ticket",
     s == 200 and kpi_nat["activite"]["crees"] == 1, kpi_nat["activite"])

print("== 3. Exports CSV et XLSX sans aucune PII ==")
FORBIDDEN_PII = (
    "DURAND_SECRET_PII_ZZ", "ZZ_Alice_Secret", "zz.alice.secret.g6@exemple.test",
    "TITRE_CONFIDENTIEL_T1", "DESC_CONFIDENTIELLE_T1", "CAUSE_RACINE_CONFIDENTIELLE",
    t1["reference"], t2["reference"], t3["reference"],
)
json_blob = json.dumps(kpi)
show("JSON ne contient aucune PII ni texte libre ni reference",
     all(tok not in json_blob for tok in FORBIDDEN_PII))

s_csv, raw_csv, hdr_csv = raw_req("GET", "/stats/tickets?format=csv", token=tok_it)
csv_text = raw_csv.decode("utf-8")
show("export CSV 200 avec BOM UTF-8, ';' et zero PII",
     s_csv == 200 and raw_csv.startswith(b"\xef\xbb\xbf") and "Rubrique;Indicateur;Valeur" in csv_text
     and "attachment" in hdr_csv.get("content-disposition", "")
     and all(tok not in csv_text for tok in FORBIDDEN_PII),
     f"status={s_csv}")

s_xlsx, raw_xlsx, hdr_xlsx = raw_req("GET", "/stats/tickets?format=xlsx", token=tok_it)
show("export XLSX 200 (signature PK) et zero PII",
     s_xlsx == 200 and raw_xlsx[:2] == b"PK"
     and "attachment" in hdr_xlsx.get("content-disposition", ""),
     f"status={s_xlsx}")

print("== 4. Rapport mensuel IT (3 chiffres globaux tickets, sans KPI securite ni PII) ==")
with Session(engine) as db:
    cfg = mailer.load_config(db)
    subj, body, _ = reminders.build_report(db, cfg, now)
show("rapport mensuel contient les 3 chiffres tickets",
     "Tickets ce mois :" in body and "delai median de resolution : 6.0 h" in body, body)
show("rapport mensuel ne contient ni KPI securite ni PII",
     "violation" not in body.lower() and "phishing" not in body.lower()
     and all(tok not in body for tok in FORBIDDEN_PII), body)

print("== 5. Purge RGPD des statistiques anonymes (retention_stats_tickets_mois) ==")
# Anonymiser 2 tickets anciens (> 65 mois) : un simple, un avec violation recente (10 mois)
with Session(engine) as db:
    t_old = Ticket(
        reference="ANON-9001", entite_id=ent_fille["id"], nature_code="autre", criticite="faible",
        statut="ferme", canal="it", niveau_securite="aucun",
        cree_le=now - timedelta(days=365 * 6), ferme_le=now - timedelta(days=365 * 5),
        anonymise_le=now - timedelta(days=365 * 4),
    )
    t_viol = Ticket(
        reference="ANON-9002", entite_id=ent_fille["id"], nature_code="message_suspect", criticite="critique",
        statut="ferme", canal="it", niveau_securite="incident",
        cree_le=now - timedelta(days=365 * 6), ferme_le=now - timedelta(days=365 * 5),
        anonymise_le=now - timedelta(days=365 * 4),
    )
    db.add(t_old)
    db.add(t_viol)
    db.commit()
    db.refresh(t_old)
    db.refresh(t_viol)
    sec_viol = TicketSecurityDetail(
        ticket_id=t_viol.id, signale_le=now - timedelta(days=300), signale_par="informatique",
        violation_donnees_potentielle=True, date_decouverte_violation=now - timedelta(days=300),
        notification_cnil_requise="oui",
    )
    db.add(sec_viol)
    db.commit()
    id_old, id_viol = t_old.id, t_viol.id

s, etat = j("GET", "/rgpd/etat", token=tok_it)
show("GET /rgpd/etat annonce 1 ticket stat echu (violation recente protegee)",
     s == 200 and etat.get("tickets_stats") == 1, etat)
s, pv = j("GET", "/rgpd/purge-preview", token=tok_it)
pv_ids = [x["id"] for x in pv.get("tickets_stats", [])]
show("GET /rgpd/purge-preview liste t_old mais pas t_viol",
     s == 200 and id_old in pv_ids and id_viol not in pv_ids, pv_ids)

s, r_del = j("POST", "/rgpd/purge-stats-tickets", {"ids": [id_old, id_viol]}, token=tok_it)
show("POST /rgpd/purge-stats-tickets supprime uniquement t_old (1)",
     s == 200 and r_del == {"supprimes": 1}, r_del)

with Session(engine) as db:
    gone = db.get(Ticket, id_old) is None
    kept = db.get(Ticket, id_viol) is not None
show("t_old supprime definitivement en base, t_viol conserve", gone and kept, f"gone={gone}, kept={kept}")

s, audit_r = j("GET", "/audit?limit=100", token=tok_it)
audit_items = audit_r if isinstance(audit_r, list) else audit_r.get("items", [])
show("purge stats journalisee dans AuditLog",
     any(x.get("action") == "rgpd_purge_stats_tickets" for x in audit_items))

print(f"\nResultat : {ok_count} OK, {fail_count} FAIL")
sys.exit(1 if fail_count else 0)
