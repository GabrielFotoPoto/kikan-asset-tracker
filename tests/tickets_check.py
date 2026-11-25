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

"""Suite de tests du lot G1 : socle tickets natif (IT), droits, workflow, SMTP, purge RGPD et verrous."""
import email
import json
import os
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "/app")

from sqlmodel import Session, select
from app.db import engine
from app.models import Account, Ticket, TicketComment, User
from app import tickets as tickets_svc

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
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw
        return e.code, payload


def login(username, password):
    st, d = call("POST", "/auth/login", {"username": username, "password": password})
    assert st == 200 and d and d.get("access_token"), f"Login {username} echoue: {st} {d}"
    return d["access_token"]


# Faux serveur SMTP en memoire pour verifier les notifications sans texte libre
RECUS = []


class FakeSMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 fake.local ESMTP\r\n")
        in_data = False
        buf = []
        rcpt = None
        while True:
            line = self.rfile.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if in_data:
                if text.strip() == ".":
                    RECUS.append({"to": rcpt, "body": "".join(buf)})
                    buf = []
                    in_data = False
                    self.wfile.write(b"250 OK\r\n")
                else:
                    buf.append(text)
                continue
            up = text.strip().upper()
            if up.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-fake.local\r\n250 OK\r\n")
            elif up.startswith("MAIL FROM"):
                self.wfile.write(b"250 OK\r\n")
            elif up.startswith("RCPT TO"):
                rcpt = text.strip()
                self.wfile.write(b"250 OK\r\n")
            elif up == "DATA":
                in_data = True
                self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
            elif up == "QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"250 OK\r\n")


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def main():
    tok_it = login(ADMIN_USER, ADMIN_PASS)

    # Comptes rh et lecture pour verifier le refus 403
    for uname, role in (("sec_tkt_rh", "rh"), ("sec_tkt_lec", "lecture")):
        call("POST", "/auth/accounts", {
            "username": uname, "password": "TestPassword123!", "role": role, "nom_affiche": uname,
        }, tok_it)
    tok_rh = login("sec_tkt_rh", "TestPassword123!")
    tok_lec = login("sec_tkt_lec", "TestPassword123!")

    # 1. Droits d'acces : rh et lecture -> 403 sur toutes les routes /tickets* et /rgpd/purge-tickets
    for label, tok in (("rh", tok_rh), ("lecture", tok_lec)):
        for method, path, payload in (
            ("GET", "/tickets", None),
            ("GET", "/tickets/compteurs", None),
            ("GET", "/tickets/natures", None),
            ("GET", "/parametres/tickets", None),
            ("POST", "/tickets", {"nature_code": "autre", "titre": "ZZTK Interdit"}),
            ("POST", "/rgpd/purge-tickets", {"ids": []}),
        ):
            st, _ = call(method, path, payload, token=tok)
            show(f"Acces refuse 403 ({label} {method} {path})", st == 403, f"got {st}")

    # 2. Catalogue des natures initial
    st, natures = call("GET", "/tickets/natures", token=tok_it)
    codes = {n["code"] for n in (natures or [])}
    show("Catalogue initial de 8 natures present", st == 200 and len(codes) >= 8 and "panne_materiel" in codes and "message_suspect" in codes)

    # 3. Creer entite, salarie et actif de test
    st, ent = call("POST", "/entites", {"code": "ZZTK", "nom": "ZZTK Entite"}, tok_it)
    ent_id = ent["id"] if st in (200, 201) else None
    st, usr = call("POST", "/users", {
        "matricule": "ZZTK001", "nom": "ZZTK_Dupont", "prenom": "Alice",
        "email": "alice.zztk@example.invalid", "entite_id": ent_id,
    }, tok_it)
    uid = usr["id"]
    st, ast = call("POST", "/assets", {
        "identifiant_interne": "ZZTK-PC-01", "type": "PC portable",
        "marque": "Lenovo", "modele": "ThinkPad T14", "numero_serie": "ZZTK-SN-001",
        "entite_id": ent_id,
    }, tok_it)
    aid = ast["id"]

    # 4. Creation ticket + numerotation TKT-AAAA-NNNN + entite figee + copie materiel
    st1, t1 = call("POST", "/tickets", {
        "nature_code": "panne_materiel",
        "titre": "ZZTK Ecran noir au demarrage",
        "description": "ZZTK SecretDescriptionNePasEnvoyerParMail",
        "criticite": "haute",
        "user_id": uid,
        "asset_id": aid,
    }, tok_it)
    show("Creation ticket IT", st1 == 201 and t1["reference"].startswith(f"TKT-{date.today().year}-"), str(t1))
    show("Entite figee et materiel copie", t1["entite_id"] == ent_id and t1["materiel_marque"] == "Lenovo" and t1["materiel_modele"] == "ThinkPad T14")

    # 5. Recherche Ctrl+K (/search) : visible IT uniquement, absent pour rh et lecture
    st, s_it = call("GET", f"/search?q={urllib.parse.quote(t1['reference'])}", token=tok_it)
    st_r, s_rh = call("GET", f"/search?q={urllib.parse.quote(t1['reference'])}", token=tok_rh)
    st_l, s_lec = call("GET", f"/search?q={urllib.parse.quote(t1['reference'])}", token=tok_lec)
    show("Ctrl+K renvoie le ticket a informatique", st == 200 and len(s_it.get("tickets", [])) == 1)
    show("Ctrl+K ne renvoie pas tickets a rh ni lecture", st_r == 200 and "tickets" not in s_rh and st_l == 200 and "tickets" not in s_lec)

    # 6. Transitions + MTTA + pause en_attente + reouverture + cloture
    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)
    show("Transition nouveau -> en_cours + premiere_reponse_le", st == 200 and t1["statut"] == "en_cours" and t1["premiere_reponse_le"] is not None)

    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_attente"}, tok_it)
    show("Transition en_cours -> en_attente", st == 200 and t1["en_attente_depuis"] is not None)
    time.sleep(1.1)
    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)
    show("Reprise en_attente -> en_cours cumule duree_attente_sec", st == 200 and t1["duree_attente_sec"] >= 1 and t1["en_attente_depuis"] is None)

    # 7. Note interne vs commentaire public + SMTP sans texte libre + anti-rafale
    smtp_srv = ReusableTCPServer(("127.0.0.1", 2526), FakeSMTPHandler)
    th = threading.Thread(target=smtp_srv.serve_forever, daemon=True)
    th.start()
    try:
        call("PUT", "/mail/config", {
            "actif": True, "hote": "127.0.0.1", "port": 2526, "securite": "aucune",
            "expediteur": "kikan@example.invalid",
        }, tok_it)
        tickets_svc.reset_mail_limits()
        RECUS.clear()

        maj_pub_avant = t1["maj_publique_le"]
        st, _ = call("POST", f"/tickets/{t1['id']}/commentaires", {
            "contenu": "ZZTK Note interne confidentielle", "interne": True,
        }, tok_it)
        time.sleep(0.3)
        _, t1_after_int = call("GET", f"/tickets/{t1['id']}", token=tok_it)
        show("Note interne ne modifie pas maj_publique_le", st == 201 and t1_after_int["maj_publique_le"] == maj_pub_avant)
        show("Note interne ne declenche aucun e-mail", len(RECUS) == 0, f"recus={len(RECUS)}")

        # Passage en resolu -> e-mail sobre sans titre ni description, annoncant cloture auto
        st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "resolu"}, tok_it)
        time.sleep(0.4)
        decoded = ""
        if RECUS:
            msg_mail = email.message_from_string(RECUS[0]["body"])
            payload = msg_mail.get_payload(decode=True)
            decoded = (payload.decode("utf-8", errors="replace") if payload else RECUS[0]["body"]) + " " + str(msg_mail.get("Subject", ""))
        show("Passage en resolu envoie e-mail sans texte libre",
             st == 200 and len(RECUS) == 1
             and t1["reference"] in decoded
             and "ZZTK Ecran noir" not in decoded
             and "ZZTK SecretDescription" not in decoded
             and "clos automatiquement" in decoded,
             f"recus={len(RECUS)}")

        # Anti-rafale : commentaire public juste apres ne renvoie pas un 2e e-mail au meme destinataire
        st, _ = call("POST", f"/tickets/{t1['id']}/commentaires", {
            "contenu": "ZZTK Complement public", "interne": False,
        }, tok_it)
        time.sleep(0.3)
        show("Anti-rafale bloque un 2e e-mail immediat sur meme ticket", st == 201 and len(RECUS) == 1, f"recus={len(RECUS)}")
    finally:
        call("PUT", "/mail/config", {"actif": False}, tok_it)
        smtp_srv.shutdown()
        smtp_srv.server_close()

    # Reouverture puis resolution et cloture
    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "en_cours"}, tok_it)
    show("Reouverture resolu -> en_cours incremente nb_reouvertures", st == 200 and t1["nb_reouvertures"] == 1)
    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "resolu"}, tok_it)
    st, t1 = call("POST", f"/tickets/{t1['id']}/statut", {"statut": "ferme"}, tok_it)
    show("Cloture resolu -> ferme", st == 200 and t1["ferme_le"] is not None)
    st_bad, _ = call("POST", f"/tickets/{t1['id']}/commentaires", {"contenu": "Apres cloture"}, tok_it)
    show("Commentaire refuse sur ticket ferme (409)", st_bad == 409, f"got {st_bad}")

    # 8. Signalement securite : nature auto-securite + cloture manuelle et auto refusees
    st, t_sec = call("POST", "/tickets", {
        "nature_code": "message_suspect",
        "titre": "ZZTK Phishing detecte",
        "criticite": "critique",
        "user_id": uid,
    }, tok_it)
    show("Nature message_suspect passe niveau_securite=signale", st == 201 and t_sec["niveau_securite"] == "signale")
    call("POST", f"/tickets/{t_sec['id']}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{t_sec['id']}/statut", {"statut": "resolu"}, tok_it)
    st_cl, _ = call("POST", f"/tickets/{t_sec['id']}/statut", {"statut": "ferme"}, tok_it)
    show("Cloture manuelle refusee sur ticket signale (409)", st_cl == 409, f"got {st_cl}")

    # 9. Cloture automatique (delai atteint, desactivee a 0, jamais sur signale)
    st, t_auto = call("POST", "/tickets", {
        "nature_code": "autre", "titre": "ZZTK Auto close", "criticite": "faible",
    }, tok_it)
    call("POST", f"/tickets/{t_auto['id']}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{t_auto['id']}/statut", {"statut": "resolu"}, tok_it)
    with Session(engine) as s:
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
        for tid in (t_auto["id"], t_sec["id"]):
            tk = s.get(Ticket, tid)
            tk.resolu_le = old
            s.add(tk)
        s.commit()
    # Desactivee a 0
    call("PUT", "/parametres/tickets", {"cloture_auto_jours": 0, "delais_cibles_heures": {"faible": 120}}, tok_it)
    with Session(engine) as s:
        n0 = tickets_svc.cloturer_tickets_resolus_echus(s)
    show("Cloture auto desactivee a 0 ne ferme rien", n0 == 0)
    # Activee a 7 jours
    call("PUT", "/parametres/tickets", {"cloture_auto_jours": 7, "delais_cibles_heures": {"faible": 120}}, tok_it)
    with Session(engine) as s:
        n7 = tickets_svc.cloturer_tickets_resolus_echus(s)
        tk_auto = s.get(Ticket, t_auto["id"])
        tk_sec = s.get(Ticket, t_sec["id"])
    show("Cloture auto ferme le ticket ordinaire mais jamais le ticket signale",
         n7 >= 1 and tk_auto.statut == "ferme" and tk_sec.statut == "resolu")

    # 10. Purge RGPD des tickets clos : anonymisation complete, MTTA/MTTR figes, numero jamais reattribue
    mtta_avant, mttr_avant = t1["mtta_sec"], t1["mttr_sec"]
    ref_avant = t1["reference"]
    with Session(engine) as s:
        tk1 = s.get(Ticket, t1["id"])
        tk1.ferme_le = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=800)
        s.add(tk1)
        s.commit()
    st, prev = call("GET", "/rgpd/purge-preview", token=tok_it)
    show("Preview RGPD liste le ticket clos echu", st == 200 and any(x["id"] == t1["id"] for x in prev.get("tickets_clos", [])))
    st, res_p = call("POST", "/rgpd/purge-tickets", {"ids": [t1["id"]]}, tok_it)
    show("Purge tickets clos reussie", st == 200 and res_p.get("anonymises") == 1)

    with Session(engine) as s:
        tk1 = s.get(Ticket, t1["id"])
        nb_c = len(s.exec(select(TicketComment).where(TicketComment.ticket_id == t1["id"])).all())
    show("Ticket anonymise : ANON-id, champs libres/liens NULL, commentaires supprimes, dates au 1er du mois, KPI figes",
         tk1.reference == f"ANON-{t1['id']}"
         and tk1.titre is None and tk1.description is None
         and tk1.user_id is None and tk1.asset_id is None
         and tk1.cree_par_account_id is None and tk1.assigne_a_account_id is None
         and tk1.materiel_marque == "Lenovo"
         and tk1.cree_le.day == 1 and tk1.cree_le.hour == 0
         and tk1.mtta_sec == mtta_avant and tk1.mttr_sec == mttr_avant
         and nb_c == 0)

    # Le numero TKT-AAAA-NNNN n'est jamais reattribue
    st, t_next = call("POST", "/tickets", {"nature_code": "autre", "titre": "ZZTK Next Ref"}, tok_it)
    show("Numero de ticket jamais reattribue apres anonymisation", st == 201 and t_next["reference"] != ref_avant)

    # 11. Suppression directe d'un salarie ayant un ticket -> anonymisation dans la meme transaction
    st, u_del = call("POST", "/users", {
        "matricule": "ZZTKDEL", "nom": "ZZTK_ASuppr", "prenom": "Bob", "entite_id": ent_id,
    }, tok_it)
    st, t_del = call("POST", "/tickets", {
        "nature_code": "autre", "titre": "ZZTK Ticket avant suppression user", "user_id": u_del["id"],
    }, tok_it)
    st_d, _ = call("DELETE", f"/users/{u_del['id']}", token=tok_it)
    with Session(engine) as s:
        tk_del = s.get(Ticket, t_del["id"])
    show("Suppression directe salarie anonymise ses tickets dans la transaction",
         st_d == 204 and tk_del.anonymise_le is not None and tk_del.titre is None and tk_del.statut == "ferme")

    # 12. Concurrence : 5 creations simultanees + double transition simultanee
    refs = []
    errors_conc = []
    bar = threading.Barrier(5)

    def create_one(i):
        bar.wait()
        st_c, d_c = call("POST", "/tickets", {"nature_code": "autre", "titre": f"ZZTK Conc {i}"}, tok_it)
        if st_c == 201:
            refs.append(d_c["reference"])
        else:
            errors_conc.append((st_c, d_c))

    threads = [threading.Thread(target=create_one, args=(i,)) for i in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    show("Concurrence : 5 creations simultanees -> 5 references distinctes", len(refs) == 5 and len(set(refs)) == 5 and not errors_conc, f"refs={refs} err={errors_conc}")

    st, t_race = call("POST", "/tickets", {"nature_code": "autre", "titre": "ZZTK Race Transition"}, tok_it)
    race_codes = []
    bar2 = threading.Barrier(2)

    def trans_one():
        bar2.wait()
        st_t, _ = call("POST", f"/tickets/{t_race['id']}/statut", {"statut": "en_cours"}, tok_it)
        race_codes.append(st_t)

    t_a, t_b = threading.Thread(target=trans_one), threading.Thread(target=trans_one)
    t_a.start(); t_b.start(); t_a.join(); t_b.join()
    show("Concurrence : double clic transition -> un 200 et un 409", sorted(race_codes) == [200, 409], str(race_codes))

    # 13. Coherence salarie / materiel (GET /tickets/materiel-salarie, POST /tickets, PUT /tickets/{id}, audit)
    _, u_m1 = call("POST", "/users", {
        "matricule": "ZZTKM1", "nom": "ZZTK_Mat1", "prenom": "Claire",
        "email": "zztk.claire@exemple.test", "entite_id": ent_id,
    }, tok_it)
    _, u_m2 = call("POST", "/users", {
        "matricule": "ZZTKM2", "nom": "ZZTK_Mat2", "prenom": "Denis",
        "email": "zztk.denis@exemple.test", "entite_id": ent_id,
    }, tok_it)
    _, a_m1 = call("POST", "/assets", {
        "identifiant_interne": "ZZTK-PC-M1", "type": "PC portable", "marque": "Dell", "modele": "Lat5440",
        "numero_serie": "ZZTK-SN-M1", "entite_id": ent_id,
    }, tok_it)
    _, a_m2 = call("POST", "/assets", {
        "identifiant_interne": "ZZTK-PC-M2", "type": "PC portable", "marque": "HP", "modele": "Elite840",
        "numero_serie": "ZZTK-SN-M2", "entite_id": ent_id,
    }, tok_it)
    _, a_stk = call("POST", "/assets", {
        "identifiant_interne": "ZZTK-PC-STK", "type": "PC portable", "marque": "Lenovo", "modele": "L14",
        "numero_serie": "ZZTK-SN-STK", "entite_id": ent_id,
    }, tok_it)
    st_rem1, _ = call("POST", "/assignments", {"user_id": u_m1["id"], "asset_ids": [a_m1["id"]], "sans_charte": True}, tok_it)
    st_rem2, _ = call("POST", "/assignments", {"user_id": u_m2["id"], "asset_ids": [a_m2["id"]], "sans_charte": True}, tok_it)
    assert st_rem1 in (200, 201) and st_rem2 in (200, 201)

    st_ms, ms_list = call("GET", f"/tickets/materiel-salarie/{u_m1['id']}", token=tok_it)
    show("GET /tickets/materiel-salarie/{id} renvoie uniquement les actifs affectes (sans PII)",
         st_ms == 200 and [x["id"] for x in ms_list] == [a_m1["id"]] and "email" not in str(ms_list), str(ms_list))
    st_ms_404, _ = call("GET", "/tickets/materiel-salarie/999999", token=tok_it)
    show("GET /tickets/materiel-salarie sur salarie inexistant -> 404", st_ms_404 == 404, f"got {st_ms_404}")
    st_ms_rh, _ = call("GET", f"/tickets/materiel-salarie/{u_m1['id']}", token=tok_rh)
    st_ms_ro, _ = call("GET", f"/tickets/materiel-salarie/{u_m1['id']}", token=tok_lec)
    show("GET /tickets/materiel-salarie refuse a rh et lecture (403)", st_ms_rh == 403 and st_ms_ro == 403, f"{st_ms_rh},{st_ms_ro}")

    st_ok_own, t_own = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZTK Materiel du salarie",
        "user_id": u_m1["id"], "asset_id": a_m1["id"],
    }, tok_it)
    show("POST /tickets : materiel du salarie accepte (201)", st_ok_own == 201, f"got {st_ok_own}")

    st_ok_stk, _ = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZTK Materiel en stock",
        "user_id": u_m1["id"], "asset_id": a_stk["id"],
    }, tok_it)
    show("POST /tickets : materiel non affecte accepte (201)", st_ok_stk == 201, f"got {st_ok_stk}")

    st_ok_free, _ = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZTK Interne IT sans salarie",
        "asset_id": a_m2["id"],
    }, tok_it)
    show("POST /tickets : ticket sans salarie libre (201)", st_ok_free == 201, f"got {st_ok_free}")

    st_409, _ = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZTK Materiel autre salarie refuse",
        "user_id": u_m1["id"], "asset_id": a_m2["id"],
    }, tok_it)
    show("POST /tickets : materiel d'un autre salarie refuse sans case (409)", st_409 == 409, f"got {st_409}")

    st_201_h, t_hors = call("POST", "/tickets", {
        "nature_code": "panne_materiel", "titre": "ZZTK Materiel autre salarie confirme",
        "user_id": u_m1["id"], "asset_id": a_m2["id"], "materiel_hors_affectation": True,
    }, tok_it)
    from app.models import AuditLog
    with Session(engine) as s:
        aud_h = s.exec(
            select(AuditLog).where(
                AuditLog.action == "ticket_materiel_hors_affectation",
                AuditLog.target == t_hors["reference"],
            )
        ).first()
    show("POST /tickets : materiel_hors_affectation=True accepte (201) et trace en audit sans PII",
         st_201_h == 201 and aud_h is not None
         and f"asset_id={a_m2['id']}" in (aud_h.detail or "")
         and "zztk.claire" not in (aud_h.detail or "").lower()
         and "ZZTK_Mat1" not in (aud_h.detail or ""),
         f"st={st_201_h} detail={aud_h.detail if aud_h else None}")

    st_put_409, _ = call("PUT", f"/tickets/{t_own['id']}", {"asset_id": a_m2["id"]}, tok_it)
    st_put_200, _ = call("PUT", f"/tickets/{t_own['id']}", {"asset_id": a_m2["id"], "materiel_hors_affectation": True}, tok_it)
    show("PUT /tickets/{id} : autre salarie refuse (409) puis accepte avec materiel_hors_affectation=True (200)",
         st_put_409 == 409 and st_put_200 == 200, f"{st_put_409},{st_put_200}")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
