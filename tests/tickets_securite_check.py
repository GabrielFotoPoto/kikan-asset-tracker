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

"""Suite de tests du lot G2 : evenements de securite, escalade, retrogradation, suivi 72h, etancheite et purge."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

from sqlmodel import Session
from app.db import engine
from app.models import Ticket, TicketSecurityDetail

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
    assert st == 200 and d and d.get("access_token"), f"Login {u} echoue: {st} {d}"
    return d["access_token"]


def main():
    tok_it = login(ADMIN_USER, ADMIN_PASS)
    for uname, role in (("sec_g2_rh", "rh"), ("sec_g2_lec", "lecture")):
        call("POST", "/auth/accounts", {"username": uname, "password": "TestPassword123!", "role": role}, tok_it)
    tok_rh = login("sec_g2_rh", "TestPassword123!")
    tok_lec = login("sec_g2_lec", "TestPassword123!")

    # Creer salarie + compte demandeur
    _, ent = call("POST", "/entites", {"code": "ZZG2", "nom": "ZZG2 Entite"}, tok_it)
    _, usr = call("POST", "/users", {
        "matricule": "ZZG2U", "nom": "ZZG2_Test", "prenom": "Clara",
        "email": "zzg2.clara@example.invalid", "entite_id": ent["id"],
    }, tok_it)
    _, prov = call("POST", f"/users/{usr['id']}/compte-demandeur", {"mode": "mot_de_passe"}, tok_it)
    tok_tmp = login(prov["username"], prov["mot_de_passe_provisoire"])
    _, ch = call("POST", "/auth/change-password", {
        "old_password": prov["mot_de_passe_provisoire"], "new_password": "MotDePasseClara2026!",
    }, tok_tmp)
    tok_dem = ch["access_token"]

    # 1. Signalement par le salarie -> dossier cree des 'signale', portail voit seulement booleen
    st, t1 = call("POST", "/tickets", {
        "nature_code": "message_suspect", "titre": "ZZG2 Phishing recu", "criticite": "haute",
    }, tok_dem)
    show("Signalement salarie cree ticket avec signalement_securite=True", st == 201 and t1.get("signalement_securite") is True)
    st_s, sec1 = call("GET", f"/tickets/{t1['id']}/securite", token=tok_it)
    show("Dossier ticket_security_details cree des le signalement", st_s == 200 and sec1["signale_par"] == "demandeur" and sec1["niveau_securite"] == "signale")

    # 2. Etancheite : demandeur, rh et lecture -> 403 sur GET/PUT /securite et POST /securite/niveau
    for label, tok in (("demandeur", tok_dem), ("rh", tok_rh), ("lecture", tok_lec)):
        st_g, _ = call("GET", f"/tickets/{t1['id']}/securite", token=tok)
        st_u, _ = call("PUT", f"/tickets/{t1['id']}/securite", {"cause_racine": "hack"}, tok)
        st_p, _ = call("POST", f"/tickets/{t1['id']}/securite/niveau", {"niveau_securite": "sans_suite"}, tok)
        show(f"Etancheite dossier securite ({label}) -> 403", st_g == 403 and st_u == 403 and st_p == 403, f"{st_g},{st_u},{st_p}")

    # Annulation refusee sur ticket 'signale' non qualifie (409)
    st_ann_bad, _ = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "annule"}, tok_dem)
    show("Annulation refusee sur ticket signale non qualifie (409)", st_ann_bad == 409, f"got {st_ann_bad}")

    # 3. Escalade en incident + violation de donnees + suivi 72h
    st_esc, sec_esc = call("POST", f"/tickets/{t1['id']}/securite/niveau", {
        "niveau_securite": "incident", "sous_categorie": "phishing",
    }, tok_it)
    show("Escalade signale -> incident + qualification_sec calcule", st_esc == 200 and sec_esc["niveau_securite"] == "incident" and sec_esc["escalade_le"] is not None)

    # Violation sans date_decouverte_violation -> 422
    st_v_bad, _ = call("PUT", f"/tickets/{t1['id']}/securite", {"violation_donnees_potentielle": True}, tok_it)
    show("Violation potentielle exige date_decouverte_violation (422)", st_v_bad == 422, f"got {st_v_bad}")

    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    st_v_ok, sec_v = call("PUT", f"/tickets/{t1['id']}/securite", {
        "violation_donnees_potentielle": True,
        "date_decouverte_violation": now_iso,
        "cause_racine": "ZZG2 Lien malveillant",
        "actions_correctives": "ZZG2 Blocage domaine",
    }, tok_it)
    show("Violation enregistree avec CNIL a_evaluer par defaut",
         st_v_ok == 200 and sec_v["violation_donnees_potentielle"] is True and sec_v["notification_cnil_requise"] == "a_evaluer")

    # 4. Retrogradation refusee tant que violation cochee (409), puis acceptee apres decochage
    st_ret_bad, _ = call("POST", f"/tickets/{t1['id']}/securite/niveau", {"niveau_securite": "sans_suite"}, tok_it)
    show("Retrogradation incident -> sans_suite refusee si violation cochee (409)", st_ret_bad == 409, f"got {st_ret_bad}")

    # Cloture manuelle refusee tant que CNIL vaut a_evaluer (409)
    call("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{t1['id']}/statut", {"statut": "resolu"}, tok_it)
    st_cl_bad, _ = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "ferme"}, tok_it)
    show("Cloture refusee si violation avec CNIL a_evaluer (409)", st_cl_bad == 409, f"got {st_cl_bad}")

    # Aucun retour a 'aucun' (409)
    st_aucun, _ = call("POST", f"/tickets/{t1['id']}/securite/niveau", {"niveau_securite": "aucun"}, tok_it)
    show("Retour au niveau 'aucun' toujours refuse (409)", st_aucun == 409, f"got {st_aucun}")

    # Cloture acceptee des que CNIL tranche ('non')
    call("PUT", f"/tickets/{t1['id']}/securite", {"notification_cnil_requise": "non"}, tok_it)
    st_cl_ok, _ = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "ferme"}, tok_it)
    show("Cloture acceptee une fois notification_cnil_requise tranchee", st_cl_ok == 200)

    # 5. Ticket 2 : incident sans violation -> retrogradation OK, reprise OK, purge efface cause_racine
    _, t2 = call("POST", "/tickets", {"nature_code": "autre", "titre": "ZZG2 Incident sans violation"}, tok_it)
    call("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "signale"}, tok_it)
    call("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "incident"}, tok_it)
    call("PUT", f"/tickets/{t2['id']}/securite", {"cause_racine": "ZZG2 Texte a effacer", "actions_correctives": "ZZG2 Action"}, tok_it)
    st_ret_ok, _ = call("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "sans_suite"}, tok_it)
    st_rep_ok, _ = call("POST", f"/tickets/{t2['id']}/securite/niveau", {"niveau_securite": "incident"}, tok_it)
    show("Retrogradation et reprise sans violation autorisees", st_ret_ok == 200 and st_rep_ok == 200)

    call("POST", f"/tickets/{t2['id']}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{t2['id']}/statut", {"statut": "resolu"}, tok_it)
    call("POST", f"/tickets/{t2['id']}/statut", {"statut": "ferme"}, tok_it)

    # 6. Purge RGPD : t1 (violation=True) conserve cause_racine ; t2 (violation=False) efface cause_racine et dates au mois
    old_close = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=800)
    with Session(engine) as s:
        for tid in (t1["id"], t2["id"]):
            tk = s.get(Ticket, tid)
            tk.ferme_le = old_close
            s.add(tk)
        s.commit()
    call("POST", "/rgpd/purge-tickets", {"ids": [t1["id"], t2["id"]]}, tok_it)
    with Session(engine) as s:
        s1 = s.get(TicketSecurityDetail, t1["id"])
        s2 = s.get(TicketSecurityDetail, t2["id"])
    show("Purge RGPD : incident AVEC violation conserve cause_racine/actions_correctives",
         s1.cause_racine == "ZZG2 Lien malveillant" and s1.qualifie_par_account_id is None and s1.escalade_par_account_id is None)
    show("Purge RGPD : incident SANS violation efface cause_racine/actions_correctives et dates au 1er du mois",
         s2.cause_racine is None and s2.actions_correctives is None and s2.signale_le.day == 1 and s2.signale_le.hour == 0)

    # Purge effective du dossier violation a l'echeance retention_violations_mois
    with Session(engine) as s:
        s1_old = s.get(TicketSecurityDetail, t1["id"])
        s1_old.date_decouverte_violation = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2000)
        s.add(s1_old)
        s.commit()
    call("POST", "/rgpd/purge-tickets", {"ids": []}, tok_it)
    with Session(engine) as s:
        s1_after = s.get(TicketSecurityDetail, t1["id"])
    show("Purge RGPD : dossier violation echu (> retention_violations_mois) efface",
         s1_after.cause_racine is None and s1_after.actions_correctives is None and s1_after.signale_le.day == 1)

    # 7. Rappel 72 h DPO dans reminders.collect / digests (violation potentielle sans notification_dpo_le)
    _, t3 = call("POST", "/tickets", {"nature_code": "autre", "titre": "ZZG2 Rappel DPO 72h"}, tok_it)
    call("POST", f"/tickets/{t3['id']}/securite/niveau", {"niveau_securite": "signale"}, tok_it)
    call("POST", f"/tickets/{t3['id']}/securite/niveau", {"niveau_securite": "incident"}, tok_it)
    call("PUT", f"/tickets/{t3['id']}/securite", {
        "violation_donnees_potentielle": True,
        "date_decouverte_violation": "2026-06-01T08:00:00",
    }, tok_it)
    from app import mailer as _mailer, reminders as _reminders
    with Session(engine) as s:
        items_dpo = _reminders.collect(s, _mailer.load_config(s), datetime.now(timezone.utc).date())
        dpo_lines = [it["ligne"] for it in items_dpo.get("securite_dpo", []) if t3["reference"] in it["ligne"]]
    show("Rappel 72 h DPO detecte un incident avec violation sans notification_dpo_le (sans texte libre)",
         len(dpo_lines) == 1 and "ZZG2 Rappel DPO 72h" not in dpo_lines[0], str(dpo_lines))
    # Une fois notification_dpo_le renseignee, le rappel disparait
    call("PUT", f"/tickets/{t3['id']}/securite", {"notification_dpo_le": "2026-06-01T10:00:00"}, tok_it)
    with Session(engine) as s:
        items_dpo_after = _reminders.collect(s, _mailer.load_config(s), datetime.now(timezone.utc).date())
        dpo_after = [it["ligne"] for it in items_dpo_after.get("securite_dpo", []) if t3["reference"] in it["ligne"]]
    show("Rappel 72 h DPO disparait une fois notification_dpo_le renseignee", len(dpo_after) == 0, str(dpo_after))

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
