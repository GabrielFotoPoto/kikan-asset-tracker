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

"""Tests du lot G7 (#182) : API d'integration /v1/tickets*, droits, portee, idempotence, securite et canal email."""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
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


def j(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            return e.code, raw.decode("utf-8", "replace")


def multipart_upload(path, filename, content_bytes, content_type, token):
    boundary = "----KikanG7Boundary2026"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, raw.decode("utf-8", "replace")


def login(u, p):
    s, r = j("POST", "/auth/login", {"username": u, "password": p})
    assert s == 200, (s, r)
    return r["access_token"]


def make_token(nom, source, droits, *, globale=False, entites=None):
    s, r = j("POST", "/integrations/tokens", {
        "nom": nom, "source": source, "droits": droits,
        "portee_globale": globale, "entites": entites or [], "jours": 30,
    }, tok_it)
    assert s in (200, 201), (s, r)
    return r["jeton"]


tok_it = login(ADMIN_USER, ADMIN_PASS)

print("== 1. Setup entites, salaries et jetons API ==")
s, ent_a = j("POST", "/entites", {"code": "ZZG7A", "nom": "ZZ G7 Entite A"}, tok_it)
assert s in (200, 201), ent_a
s, ent_b = j("POST", "/entites", {"code": "ZZG7B", "nom": "ZZ G7 Entite B"}, tok_it)
assert s in (200, 201), ent_b

_, u_a = j("POST", "/users", {
    "matricule": "ZZG7-A1", "nom": "ZZG7_ALICE", "prenom": "ZZ_Alice",
    "email": "zzg7.alice@exemple.test", "entite_id": ent_a["id"],
}, tok_it)
_, u_dup1 = j("POST", "/users", {
    "matricule": "ZZG7-D1", "nom": "ZZG7_DUP1", "prenom": "ZZ_Dup1",
    "email": "zzg7.dup@exemple.test", "entite_id": ent_a["id"],
}, tok_it)
_, u_dup2 = j("POST", "/users", {
    "matricule": "ZZG7-D2", "nom": "ZZG7_DUP2", "prenom": "ZZ_Dup2",
    "email": "zzg7.dup@exemple.test", "entite_id": ent_a["id"],
}, tok_it)
_, u_b = j("POST", "/users", {
    "matricule": "ZZG7-B1", "nom": "ZZG7_BOB", "prenom": "ZZ_Bob",
    "email": "zzg7.bob@exemple.test", "entite_id": ent_b["id"],
}, tok_it)

tok_ro_a = make_token("ZZ G7 RO A", "zz_g7", ["tickets_lecture"], entites=[ent_a["id"]])
tok_rw_a = make_token("ZZ G7 RW A", "zz_g7", ["tickets_lecture", "tickets_ecriture"], entites=[ent_a["id"]])
tok_int_a = make_token("ZZ G7 INT A", "zz_g7", ["tickets_lecture", "tickets_ecriture", "tickets_interne"], entites=[ent_a["id"]])
tok_rw_b = make_token("ZZ G7 RW B", "zz_g7_b", ["tickets_lecture", "tickets_ecriture"], entites=[ent_b["id"]])

print("== 2. Droits et isolation de session ==")
s, _ = j("GET", "/v1/tickets", token=tok_it)
show("jeton de session refuse sur /v1/tickets (401)", s == 401, s)
s, nats = j("GET", "/v1/tickets/natures", token=tok_ro_a)
show("GET /v1/tickets/natures -> 200", s == 200 and any(n["code"] == "panne_materiel" for n in nats), s)
s, _ = j("PUT", "/v1/tickets/EXT-RO", {
    "nature_code": "panne_materiel", "titre": "ZZ RO interdit", "demandeur_matricule": "ZZG7-A1",
}, tok_ro_a)
show("PUT /v1/tickets sans tickets_ecriture -> 403", s == 403, s)

print("== 3. Creation idempotente, dry_run, recherche salarie et canal email ==")
s, dry = j("PUT", "/v1/tickets/EXT-DRY-1?dry_run=1", {
    "nature_code": "panne_materiel", "titre": "ZZ Dry run ticket", "demandeur_matricule": "ZZG7-A1",
}, tok_rw_a)
show("PUT ?dry_run=1 -> simulation cree, rien ecrit",
     s == 200 and dry["simulation"] is True and dry["resultat"] == "cree" and dry["id"] is None, dry)
s, lst0 = j("GET", "/v1/tickets", token=tok_ro_a)
show("apres dry_run, 0 ticket en base", s == 200 and len(lst0) == 0, lst0)

# Creation canal api (demandeur_verifie=True)
s, c1 = j("PUT", "/v1/tickets/EXT-API-1", {
    "nature_code": "panne_materiel", "titre": "ZZ Panne ecran API",
    "description": "ZZ Description publique", "criticite": "haute",
    "demandeur_matricule": "ZZG7-A1",
}, tok_rw_a)
show("PUT /v1/tickets/EXT-API-1 -> cree (canal=api, demandeur_verifie=True)",
     s == 200 and c1["resultat"] == "cree" and c1["canal"] == "api" and c1["demandeur_verifie"] is True, c1)
ref1 = c1["reference"]

# Re-soumission identique -> inchange (idempotence)
s, c1_again = j("PUT", "/v1/tickets/EXT-API-1", {
    "nature_code": "panne_materiel", "titre": "ZZ Panne ecran API",
    "description": "ZZ Description publique", "criticite": "haute",
    "demandeur_matricule": "ZZG7-A1",
}, tok_rw_a)
show("idempotence : meme id_externe -> inchange sans doublon",
     s == 200 and c1_again["resultat"] == "inchange" and c1_again["reference"] == ref1, c1_again)

# Mise a jour criticite -> modifie
s, c1_upd = j("PUT", "/v1/tickets/EXT-API-1", {
    "nature_code": "panne_materiel", "titre": "ZZ Panne ecran API",
    "criticite": "critique", "demandeur_matricule": "ZZG7-A1",
}, tok_rw_a)
show("mise a jour criticite -> modifie", s == 200 and c1_upd["resultat"] == "modifie", c1_upd)

# Canal email : 0 fiche -> 422, 2 fiches -> 422, 1 fiche -> cree + demandeur_verifie=False
s_0, _ = j("PUT", "/v1/tickets/MAIL-0", {
    "nature_code": "autre", "titre": "ZZ Mail inconnu", "canal": "email",
    "demandeur_email": "zzg7.inconnu@exemple.test",
}, tok_rw_a)
show("canal email : 0 fiche active -> 422", s_0 == 422, s_0)

s_2, _ = j("PUT", "/v1/tickets/MAIL-2", {
    "nature_code": "autre", "titre": "ZZ Mail doublon", "canal": "email",
    "demandeur_email": "zzg7.dup@exemple.test",
}, tok_rw_a)
show("canal email : 2 fiches actives -> 422", s_2 == 422, s_2)

s_1, m1 = j("PUT", "/v1/tickets/MAIL-MSG-42", {
    "nature_code": "demande_service", "titre": "ZZ Demande par mail", "canal": "email",
    "demandeur_email": "zzg7.alice@exemple.test",
}, tok_rw_a)
show("canal email : 1 fiche active -> cree avec demandeur_verifie=False",
     s_1 == 200 and m1["resultat"] == "cree" and m1["canal"] == "email" and m1["demandeur_verifie"] is False, m1)
s_1b, m1b = j("PUT", "/v1/tickets/MAIL-MSG-42", {
    "nature_code": "demande_service", "titre": "ZZ Demande par mail", "canal": "email",
    "demandeur_email": "zzg7.alice@exemple.test",
}, tok_rw_a)
show("canal email : meme Message-ID soumis 2 fois -> 1 seul ticket (inchange)",
     s_1b == 200 and m1b["resultat"] == "inchange" and m1b["id"] == m1["id"], m1b)

print("== 4. Portee par entite (404 hors perimetre) ==")
s_b, cb = j("PUT", "/v1/tickets/EXT-B-1", {
    "nature_code": "autre", "titre": "ZZ Ticket entite B", "demandeur_matricule": "ZZG7-B1",
}, tok_rw_b)
assert s_b == 200, cb
s_oos, _ = j("GET", f"/v1/tickets/{cb['reference']}", token=tok_ro_a)
show("jeton entite A ne voit pas ticket entite B (404)", s_oos == 404, s_oos)
s_lst_a, lst_a = j("GET", "/v1/tickets", token=tok_ro_a)
show("liste entite A exclut ticket entite B",
     s_lst_a == 200 and all(t["reference"] != cb["reference"] for t in lst_a), lst_a)

print("== 5. Transitions statut et commentaires (publics vs internes) ==")
s_bad, _ = j("POST", f"/v1/tickets/{ref1}/statut", {"statut": "ferme"}, tok_rw_a)
show("transition interdite nouveau -> ferme (409)", s_bad == 409, s_bad)
s_ok, t_ec = j("POST", f"/v1/tickets/{ref1}/statut", {"statut": "en_cours"}, tok_rw_a)
show("transition autorisee nouveau -> en_cours (200)", s_ok == 200 and t_ec["statut"] == "en_cours", t_ec)

s_cp, _ = j("POST", f"/v1/tickets/{ref1}/commentaires", {"contenu": "Commentaire public API", "interne": False}, tok_rw_a)
show("ajout commentaire public (201)", s_cp == 201, s_cp)
s_ci_no, _ = j("POST", f"/v1/tickets/{ref1}/commentaires", {"contenu": "Note interne refusee", "interne": True}, tok_rw_a)
show("ajout note interne sans tickets_interne -> 403", s_ci_no == 403, s_ci_no)
s_ci_ok, _ = j("POST", f"/v1/tickets/{ref1}/commentaires", {"contenu": "NOTE_INTERNE_SECRETE", "interne": True}, tok_int_a)
show("ajout note interne avec tickets_interne -> 201", s_ci_ok == 201, s_ci_ok)

s_d1, d_no_int = j("GET", f"/v1/tickets/{ref1}", token=tok_ro_a)
s_d2, d_with_int = j("GET", f"/v1/tickets/{ref1}", token=tok_int_a)
show("notes internes masquees sans tickets_interne, visibles avec",
     s_d1 == 200 and s_d2 == 200
     and all(not c["interne"] for c in d_no_int["commentaires"])
     and any(c["interne"] and c["contenu"] == "NOTE_INTERNE_SECRETE" for c in d_with_int["commentaires"]),
     (len(d_no_int["commentaires"]), len(d_with_int["commentaires"])))

print("== 6. Protection securite (signale/incident sans texte libre ni dossier securite) ==")
s_sec, c_sec = j("PUT", "/v1/tickets/EXT-SEC-1", {
    "nature_code": "message_suspect", "titre": "ZZ PHISHING_TITRE_SECRET",
    "description": "ZZ PHISHING_DESC_SECRETE", "signaler_securite": True,
    "demandeur_matricule": "ZZG7-A1",
}, tok_rw_a)
assert s_sec == 200, c_sec
ref_sec = c_sec["reference"]
j("POST", f"/v1/tickets/{ref_sec}/commentaires", {"contenu": "COMMENTAIRE_SEC_SECRET", "interne": True}, tok_int_a)
# Escalade en incident + cause_racine cote IT
j("POST", f"/tickets/{c_sec['id']}/securite/niveau", {"niveau_securite": "incident", "sous_categorie": "phishing"}, tok_it)
j("PUT", f"/tickets/{c_sec['id']}/securite", {"cause_racine": "CAUSE_RACINE_ULTRA_SECRETE"}, tok_it)

s_gsec, d_sec = j("GET", f"/v1/tickets/{ref_sec}", token=tok_int_a)
blob_sec = json.dumps(d_sec)
show("ticket incident : texte libre, commentaires et dossier securite totalement masques",
     s_gsec == 200 and d_sec["texte_masque"] is True and d_sec["titre"] is None and d_sec["description"] is None
     and d_sec["commentaires"] == []
     and "PHISHING_TITRE_SECRET" not in blob_sec
     and "PHISHING_DESC_SECRETE" not in blob_sec
     and "COMMENTAIRE_SEC_SECRET" not in blob_sec
     and "CAUSE_RACINE_ULTRA_SECRETE" not in blob_sec
     and "ticket_security_details" not in blob_sec, d_sec)

# Classement sans_suite -> texte libre de nouveau visible
j("POST", f"/tickets/{c_sec['id']}/securite/niveau", {"niveau_securite": "sans_suite"}, tok_it)
s_gss, d_ss = j("GET", f"/v1/tickets/{ref_sec}", token=tok_ro_a)
show("ticket sans_suite : texte libre de nouveau accessible",
     s_gss == 200 and d_ss["texte_masque"] is False and d_ss["titre"] == "ZZ PHISHING_TITRE_SECRET", d_ss)

print("== 7. Pieces jointes via /v1/tickets/{reference}/pieces-jointes ==")
s_up, pj = multipart_upload(f"/v1/tickets/{ref1}/pieces-jointes", "journal.txt", b"Log applicatif test G7", "text/plain", tok_rw_a)
show("POST piece jointe TXT valide -> 201", s_up == 201 and pj["mime_type"] == "text/plain", pj)
s_lpj, lpj = j("GET", f"/v1/tickets/{ref1}/pieces-jointes", token=tok_ro_a)
show("GET pieces jointes renvoie la PJ deposee", s_lpj == 200 and len(lpj) == 1, lpj)
s_svg, _ = multipart_upload(f"/v1/tickets/{ref1}/pieces-jointes", "xss.svg", b"<svg></svg>", "image/svg+xml", tok_rw_a)
show("POST piece jointe SVG interdite -> 415/422", s_svg in (415, 422), s_svg)

print("== 8. MTTA non fausse par /v1 et suppression ExternalLink a l'anonymisation ==")
s_cm, cm = j("PUT", "/v1/tickets/EXT-API-MTTA", {
    "nature_code": "panne_materiel", "titre": "ZZ MTTA /v1",
    "description": "Test premiere reponse API", "criticite": "moyenne",
    "demandeur_matricule": "ZZG7-A1", "canal": "email",
}, tok_rw_a)
ref_mtta = cm["reference"]
j("POST", f"/v1/tickets/{ref_mtta}/commentaires", {"contenu": "Relais reponse salarie via API", "interne": False}, tok_rw_a)
s_det_mtta, det_mtta = j("GET", f"/tickets/{cm['id']}", token=tok_it)
show("Commentaire public via /v1 ne renseigne pas premiere_reponse_le (MTTA non fausse)",
     s_det_mtta == 200 and det_mtta["premiere_reponse_le"] is None, det_mtta.get("premiere_reponse_le"))

# Anonymisation directe du ticket -> ExternalLink supprime immediatement
j("POST", f"/v1/tickets/{ref_mtta}/statut", {"statut": "en_cours"}, tok_rw_a)
j("POST", f"/v1/tickets/{ref_mtta}/statut", {"statut": "resolu"}, tok_rw_a)
j("POST", f"/v1/tickets/{ref_mtta}/statut", {"statut": "ferme"}, tok_rw_a)
from app.db import engine as _eng
from app.models import ExternalLink as _ExtLink, Ticket as _Tkt
from app import tickets as _tickets_svc
from sqlmodel import Session as _Sess, select as _sel
with _Sess(_eng) as _s:
    _t = _s.get(_Tkt, cm["id"])
    _tickets_svc.anonymiser_ticket(_s, _t)
    _s.commit()
    _links_left = _s.exec(_sel(_ExtLink).where(_ExtLink.objet == "ticket", _ExtLink.kikan_id == cm["id"])).all()
show("Anonymisation d'un ticket supprime immediatement ses ExternalLink", len(_links_left) == 0, len(_links_left))

print("== 9. Coherence salarie / materiel sur PUT /v1/tickets/{id_externe} ==")
_, u_v1_b = j("POST", "/users", {
    "matricule": "ZZG7-A2", "nom": "ZZG7_A2", "prenom": "ZZ_A2",
    "email": "zzg7.a2@exemple.test", "entite_id": ent_a["id"],
}, tok_it)
_, a_v1_1 = j("POST", "/assets", {
    "identifiant_interne": "ZZG7-PC-1", "type": "PC portable", "marque": "Dell", "modele": "Lat5440",
    "numero_serie": "ZZG7-SN-1", "entite_id": ent_a["id"],
}, tok_it)
_, a_v1_2 = j("POST", "/assets", {
    "identifiant_interne": "ZZG7-PC-2", "type": "PC portable", "marque": "HP", "modele": "Elite840",
    "numero_serie": "ZZG7-SN-2", "entite_id": ent_a["id"],
}, tok_it)
j("POST", "/assignments", {"user_id": u_a["id"], "asset_ids": [a_v1_1["id"]], "sans_charte": True}, tok_it)
j("POST", "/assignments", {"user_id": u_v1_b["id"], "asset_ids": [a_v1_2["id"]], "sans_charte": True}, tok_it)

s_v1_own, d_v1_own = j("PUT", "/v1/tickets/EXT-MAT-OWN", {
    "nature_code": "panne_materiel", "titre": "ZZ V1 Materiel du salarie",
    "demandeur_matricule": "ZZG7-A1", "asset_identifiant": "ZZG7-PC-1",
}, tok_rw_a)
show("PUT /v1 : materiel du salarie accepte (200)", s_v1_own == 200 and d_v1_own["resultat"] == "cree", d_v1_own)

s_v1_409, _ = j("PUT", "/v1/tickets/EXT-MAT-OTHER", {
    "nature_code": "panne_materiel", "titre": "ZZ V1 Materiel autre salarie",
    "demandeur_matricule": "ZZG7-A1", "asset_identifiant": "ZZG7-PC-2",
}, tok_rw_a)
show("PUT /v1 : materiel d'un autre salarie refuse sans flag (409)", s_v1_409 == 409, s_v1_409)

s_v1_hors, d_v1_hors = j("PUT", "/v1/tickets/EXT-MAT-OTHER", {
    "nature_code": "panne_materiel", "titre": "ZZ V1 Materiel autre salarie confirme",
    "demandeur_matricule": "ZZG7-A1", "asset_identifiant": "ZZG7-PC-2",
    "materiel_hors_affectation": True,
}, tok_rw_a)
from app.models import AuditLog as _AudLog
with _Sess(_eng) as _s:
    _aud_v1 = _s.exec(_sel(_AudLog).where(_AudLog.action == "ticket_materiel_hors_affectation", _AudLog.target == d_v1_hors.get("reference"))).first()
show("PUT /v1 : materiel_hors_affectation=True accepte (200) et trace en audit",
     s_v1_hors == 200 and d_v1_hors["resultat"] == "cree" and _aud_v1 is not None, (s_v1_hors, _aud_v1.detail if _aud_v1 else None))

# Mise a jour sur ticket existant /v1 vers materiel d'un autre salarie
s_v1_upd_409, _ = j("PUT", "/v1/tickets/EXT-MAT-OWN", {
    "nature_code": "panne_materiel", "titre": "ZZ V1 Materiel du salarie",
    "demandeur_matricule": "ZZG7-A1", "asset_identifiant": "ZZG7-PC-2",
}, tok_rw_a)
s_v1_upd_ok, d_v1_upd_ok = j("PUT", "/v1/tickets/EXT-MAT-OWN", {
    "nature_code": "panne_materiel", "titre": "ZZ V1 Materiel du salarie",
    "demandeur_matricule": "ZZG7-A1", "asset_identifiant": "ZZG7-PC-2",
    "materiel_hors_affectation": True,
}, tok_rw_a)
show("PUT /v1 (maj) : autre salarie refuse (409) puis accepte avec materiel_hors_affectation=True (200)",
     s_v1_upd_409 == 409 and s_v1_upd_ok == 200 and d_v1_upd_ok["resultat"] == "modifie", (s_v1_upd_409, d_v1_upd_ok))

print("== 10. Reprise en_attente -> en_cours sur commentaire demandeur /v1 ==")
s_rep, c_rep = j("PUT", "/v1/tickets/EXT-API-REPRISE", {
    "nature_code": "panne_materiel", "titre": "ZZ Reprise en_attente /v1",
    "description": "Test reprise automatique sur reponse salarie", "criticite": "moyenne",
    "demandeur_matricule": "ZZG7-A1", "canal": "email",
}, tok_rw_a)
ref_rep = c_rep["reference"]
j("POST", f"/v1/tickets/{ref_rep}/statut", {"statut": "en_cours"}, tok_rw_a)
j("POST", f"/v1/tickets/{ref_rep}/statut", {"statut": "en_attente"}, tok_rw_a)

# 1) Commentaire public IT -> reste en_attente
s_c_it, _ = j("POST", f"/v1/tickets/{ref_rep}/commentaires", {
    "contenu": "Relance IT via API", "interne": False, "auteur_type": "it",
}, tok_rw_a)
s_det_it, det_it = j("GET", f"/tickets/{c_rep['id']}", token=tok_it)
show("Commentaire public auteur_type=it sur /v1 ne reprend pas un ticket en_attente",
     s_c_it == 201 and s_det_it == 200 and det_it["statut"] == "en_attente", (s_c_it, det_it.get("statut")))

# 2) Note interne -> reste en_attente meme avec auteur_type=demandeur
s_c_int, _ = j("POST", f"/v1/tickets/{ref_rep}/commentaires", {
    "contenu": "Note interne API", "interne": True, "auteur_type": "demandeur",
}, tok_int_a)
s_det_int, det_int = j("GET", f"/tickets/{c_rep['id']}", token=tok_it)
show("Note interne sur /v1 ne reprend pas un ticket en_attente",
     s_c_int == 201 and s_det_int == 200 and det_int["statut"] == "en_attente", (s_c_int, det_int.get("statut")))

# 3) Commentaire public demandeur -> reprend en_cours et cumule duree_attente_sec
s_c_dem, _ = j("POST", f"/v1/tickets/{ref_rep}/commentaires", {
    "contenu": "Reponse salarie via API", "interne": False, "auteur_type": "demandeur",
}, tok_rw_a)
s_det_dem, det_dem = j("GET", f"/tickets/{c_rep['id']}", token=tok_it)
show("Commentaire public auteur_type=demandeur sur /v1 reprend en_attente -> en_cours",
     s_c_dem == 201 and s_det_dem == 200 and det_dem["statut"] == "en_cours"
     and det_dem["en_attente_depuis"] is None and (det_dem["duree_attente_sec"] or 0) >= 0,
     (s_c_dem, det_dem.get("statut"), det_dem.get("en_attente_depuis"), det_dem.get("duree_attente_sec")))

print(f"\nResultat : {ok_count} OK, {fail_count} FAIL")
sys.exit(1 if fail_count else 0)
