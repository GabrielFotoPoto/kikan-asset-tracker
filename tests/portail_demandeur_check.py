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

"""Suite de tests du lot G4a : portail salarie (role demandeur), isolation stricte, liste blanche et audit pseudonyme."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, "/app")

from sqlmodel import Session, select
from app.auth import ALLOWED_FOR_DEMANDEUR, create_access_token
from app.db import engine
from app.main import app
from app.models import Account, AuditLog, EmployeeStatus, PasswordResetToken, Role, Ticket, User

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "ChangeMoi123!")

fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}  {name}" + (f" ({detail})" if detail else ""))


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "X-Kikan-Request": "1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(B + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw
        return e.code, payload


def login(u, p):
    st, d = call("POST", "/auth/login", {"username": u, "password": p})
    return st, d


def main():
    st, d_it = login(ADMIN_USER, ADMIN_PASS)
    assert st == 200, f"Login IT echoue: {st} {d_it}"
    tok_it = d_it["access_token"]

    # Creer entite + 2 salaries actifs A et B + 1 actif
    _, ent = call("POST", "/entites", {"code": "ZZDM", "nom": "ZZDM Entite"}, tok_it)
    eid = ent["id"]
    _, ua = call("POST", "/users", {
        "matricule": "ZZDMA", "nom": "ZZDM_Alice", "prenom": "Alice",
        "email": "zzdm.alice@example.invalid", "entite_id": eid,
    }, tok_it)
    _, ub = call("POST", "/users", {
        "matricule": "ZZDMB", "nom": "ZZDM_Bob", "prenom": "Bob",
        "email": "zzdm.bob@example.invalid", "entite_id": eid,
    }, tok_it)
    _, ast_a = call("POST", "/assets", {
        "identifiant_interne": "ZZDM-PC-A", "type": "PC portable",
        "marque": "Lenovo", "modele": "T14", "numero_serie": "ZZDM-SN-A", "entite_id": eid,
    }, tok_it)
    _, ast_b = call("POST", "/assets", {
        "identifiant_interne": "ZZDM-PC-B", "type": "PC portable",
        "marque": "Dell", "modele": "5440", "numero_serie": "ZZDM-SN-B", "entite_id": eid,
    }, tok_it)
    # Affecter ast_a a Alice
    call("POST", "/assignments", {"user_id": ua["id"], "asset_ids": [ast_a["id"]]}, tok_it)

    # 1. Provisionnement local unitaire (A) et en lot (B)
    st_pa, pa = call("POST", f"/users/{ua['id']}/compte-demandeur", {"mode": "mot_de_passe"}, tok_it)
    show("Provisionnement unitaire demandeur A (201)", st_pa == 201 and pa.get("mot_de_passe_provisoire"), str(pa))
    st_pb, pb = call("POST", "/users/comptes-demandeurs-lot", {"ids": [ua["id"], ub["id"]]}, tok_it)
    show("Provisionnement en lot : A ignore (deja cree), B cree",
         st_pb == 201 and len(pb["crees"]) == 1 and len(pb["ignores"]) == 1, str(pb))

    # Connexion + changement mot de passe impose
    st_la, la = login(pa["username"], pa["mot_de_passe_provisoire"])
    show("Connexion A avec MDP provisoire (must_change_password=True)", st_la == 200 and la["must_change_password"] is True)
    st_ch, ch_a = call("POST", "/auth/change-password", {
        "old_password": pa["mot_de_passe_provisoire"], "new_password": "NouveauMotDePasseA2026!",
    }, la["access_token"])
    show("Changement de mot de passe A", st_ch == 200)
    tok_a = ch_a["access_token"]

    b_info = pb["crees"][0]
    _, lb = login(b_info["username"], b_info["mot_de_passe_provisoire"])
    _, ch_b = call("POST", "/auth/change-password", {
        "old_password": b_info["mot_de_passe_provisoire"], "new_password": "NouveauMotDePasseB2026!",
    }, lb["access_token"])
    tok_b = ch_b["access_token"]

    # 2. Portee /auth/me toujours vide pour demandeur
    st_me, me_a = call("GET", "/auth/me", token=tok_a)
    show("Portee par entite vide pour demandeur", st_me == 200 and me_a["portee"]["globale"] is False and me_a["portee"]["vide"] is True)

    # 3. Mon materiel (lecture seule)
    st_mat, mat_a = call("GET", "/mon-espace/materiel", token=tok_a)
    show("GET /mon-espace/materiel renvoie uniquement le materiel d'Alice",
         st_mat == 200 and len(mat_a) == 1 and mat_a[0]["id"] == ast_a["id"], str(mat_a))

    # 4. Creation ticket par demandeur A (avec son actif OK, actif de B -> 404)
    st_bad_ast, _ = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZDM Actif interdit", "asset_id": ast_b["id"],
    }, tok_a)
    show("Demandeur A ne peut pas ouvrir de ticket sur un actif non affecte (404)", st_bad_ast == 404, f"got {st_bad_ast}")

    st_ta, ta = call("POST", "/tickets", {
        "nature_code": "message_suspect", "titre": "ZZDM Ticket Alice", "asset_id": ast_a["id"],
    }, tok_a)
    show("Demandeur A ouvre son ticket (portail, bool signalement_securite, sans maj_le)",
         st_ta == 201 and ta.get("signalement_securite") is True and "maj_le" not in ta and "niveau_securite" not in ta, str(ta))

    st_tb, tb = call("POST", "/tickets", {
        "nature_code": "autre", "titre": "ZZDM Ticket Bob",
    }, tok_b)
    # Ticket interne IT (user_id=None)
    st_tit, tit = call("POST", "/tickets", {
        "nature_code": "autre", "titre": "ZZDM Ticket Interne IT",
    }, tok_it)

    # Note interne IT sur le ticket d'Alice (ne doit JAMAIS etre visible par Alice)
    call("POST", f"/tickets/{ta['id']}/commentaires", {"contenu": "ZZDM Secret interne IT", "interne": True}, tok_it)
    call("POST", f"/tickets/{ta['id']}/commentaires", {"contenu": "ZZDM Reponse publique IT", "interne": False}, tok_it)

    # 5. Isolation stricte inter-salaries
    st_la_list, list_a = call("GET", "/tickets", token=tok_a)
    ids_a = {t["id"] for t in list_a.get("items", [])}
    show("Liste demandeur A : uniquement ses tickets (ni Bob, ni interne IT)",
         st_la_list == 200 and ids_a == {ta["id"]}, str(ids_a))

    st_det_a, det_a = call("GET", f"/tickets/{ta['id']}", token=tok_a)
    show("Detail demandeur A : aucune note interne ni maj_le",
         st_det_a == 200 and len(det_a["commentaires"]) == 1 and "Secret interne" not in json.dumps(det_a) and "maj_le" not in det_a)

    for label, method, path, body in (
        ("lire ticket Bob", "GET", f"/tickets/{tb['id']}", None),
        ("commenter ticket Bob", "POST", f"/tickets/{tb['id']}/commentaires", {"contenu": "coucou"}),
        ("changer statut ticket Bob", "POST", f"/tickets/{tb['id']}/statut", {"statut": "annule"}),
        ("lire ticket interne IT", "GET", f"/tickets/{tit['id']}", None),
    ):
        st_x, _ = call(method, path, body, tok_a)
        show(f"Isolation demandeur A ({label}) -> 404", st_x == 404, f"got {st_x}")

    st_int_forb, _ = call("POST", f"/tickets/{ta['id']}/commentaires", {"contenu": "hack", "interne": True}, tok_a)
    show("Demandeur A ne peut pas poster de note interne (403)", st_int_forb == 403, f"got {st_int_forb}")

    # Reprise auto en_attente -> en_cours sur reponse publique du demandeur
    call("POST", f"/tickets/{tb['id']}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{tb['id']}/statut", {"statut": "en_attente"}, tok_it)
    call("POST", f"/tickets/{tb['id']}/commentaires", {"contenu": "Voici la precision"}, tok_b)
    _, tb_check = call("GET", f"/tickets/{tb['id']}", token=tok_it)
    show("Reponse demandeur sur ticket en_attente repasse en_cours", tb_check["statut"] == "en_cours")

    # 6. Inventaire COMPLET de toutes les routes de l'application avec jeton demandeur
    non_public_exempt = {
        "/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
        "/auth/login", "/auth/forgot", "/auth/reset", "/auth/sso/config",
        "/auth/sso/start", "/auth/sso/callback", "/auth/sso/exchange",
        "/branding/icone",
    }
    leaks = []
    tested_routes = 0
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if not path or path in ALLOWED_FOR_DEMANDEUR or path in non_public_exempt:
            continue
        if path.startswith("/v1"):
            continue
        method = "GET" if "GET" in methods else sorted(methods - {"HEAD", "OPTIONS"})[0]
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        st_r, _ = call(method, concrete, {} if method in ("POST", "PUT", "PATCH") else None, tok_a)
        tested_routes += 1
        if st_r != 403:
            leaks.append((method, path, st_r))
    show(f"Inventaire complet routes hors liste blanche ({tested_routes} routes) -> toutes 403", len(leaks) == 0, str(leaks[:5]))

    # Page A propos accessible en lecture au demandeur, mais /apropos/mise-a-jour reste 403
    st_ap, ap_data = call("GET", "/apropos", token=tok_a)
    st_ap_maj, _ = call("GET", "/apropos/mise-a-jour", token=tok_a)
    show("GET /apropos accessible au demandeur (200) et /apropos/mise-a-jour refuse (403)",
         st_ap == 200 and isinstance(ap_data, dict) and "version" in ap_data and st_ap_maj == 403,
         f"{st_ap},{st_ap_maj}")

    # Methodes IT interdites sur chemins partages + creation demandeur via /auth/accounts refusee
    for label, method, path, body in (
        ("POST /tickets/natures", "POST", "/tickets/natures", {"code": "zz_hack", "libelle": "Hack"}),
        ("PUT /tickets/{id}", "PUT", f"/tickets/{ta['id']}", {"criticite": "critique"}),
        ("DELETE PJ", "DELETE", f"/tickets/{ta['id']}/pieces-jointes/1", None),
    ):
        st_m, _ = call(method, path, body, tok_a)
        show(f"Methode IT interdite au demandeur ({label}) -> 403", st_m == 403, f"got {st_m}")
    st_acc_dem, _ = call("POST", "/auth/accounts", {"username": "zz_bypass", "role": "demandeur"}, tok_it)
    show("POST /auth/accounts refuse role=demandeur (422)", st_acc_dem == 422, f"got {st_acc_dem}")

    # 7. Cas obligatoire : compte demandeur avec user_id = NULL -> aucun ticket visible
    with Session(engine) as s:
        acc_null = Account(
            username="sec_dm_null@example.invalid", role=Role.demandeur, actif=True,
            hashed_password="x", portee_globale=False, user_id=None,
        )
        s.add(acc_null)
        s.commit()
        s.refresh(acc_null)
        tok_null = create_access_token(acc_null.username, Role.demandeur.value, 0, act=f"dem-{acc_null.id}")
    st_n1, _ = call("GET", "/tickets", token=tok_null)
    st_n2, _ = call("GET", f"/tickets/{tit['id']}", token=tok_null)
    show("Demandeur avec user_id NULL bloque (403 sur liste et ticket interne IT)", st_n1 == 403 and st_n2 == 403, f"{st_n1},{st_n2}")

    # 8. Cas obligatoire : salarie passe sorti -> acces coupe a la requete suivante
    with Session(engine) as s:
        u_obj = s.get(User, ub["id"])
        u_obj.statut = EmployeeStatus.sorti
        u_obj.date_sortie = date(2020, 1, 1)
        s.add(u_obj)
        s.commit()
    st_sorti, _ = call("GET", "/tickets", token=tok_b)
    show("Salarie passe sorti : acces coupe a la requete suivante (403)", st_sorti == 403, f"got {st_sorti}")

    # 9. AuditLog : aucune ligne ne contient l'identifiant ni l'e-mail du demandeur
    with Session(engine) as s:
        logs = s.exec(select(AuditLog).order_by(AuditLog.id.desc()).limit(300)).all()
    blob = " ".join(f"{x.actor} {x.target or ''} {x.detail or ''}" for x in logs).lower()
    show("AuditLog ne contient jamais l'identifiant ni l'e-mail des demandeurs",
         "zzdm.alice@example.invalid" not in blob and "zzdm.bob@example.invalid" not in blob)
    show("AuditLog contient le libelle pseudonyme dem-<id>", f"dem-{pa['account_id']}" in blob)

    # 10. Purge RGPD d'un salarie sorti -> supprime le compte demandeur et ses tokens
    st_pg, _ = call("POST", "/rgpd/purge", {"ids": [ub["id"]]}, tok_it)
    with Session(engine) as s:
        acc_b_after = s.get(Account, b_info["account_id"])
    show("Purge RGPD salarie sorti supprime son compte demandeur", st_pg == 200 and acc_b_after is None)

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
