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

"""Revue des droits d'acces (C2) : rapport, anomalies, campagne, decisions, perimetre par entite, cloture scellee, retraits, rappels.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kiktest-api python - < tests/revue_check.py

Cree des donnees marquees ZZRV (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
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
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login(user, pw):
    s, b, _ = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


ADM = login(os.environ.get("TEST_ADMIN_USER", "admin"), os.environ.get("TEST_ADMIN_PASSWORD", ""))
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None, token=None):
    s, b, _ = call(method, path, body, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def account(name, role, **scope):
    s, r = j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, **scope})
    return login(name, PW)


from sqlmodel import Session, select  # noqa: E402
from app import mailer, reminders, revue_acces  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import RevueLigne  # noqa: E402

print("== Organisation de test ==")
ent = {}
for code in ("ZZRV-A", "ZZRV-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    ent[code] = r["id"]
EA, EB = ent["ZZRV-A"], ent["ZZRV-B"]
apps = {}
for nom in ("ZZRV-ERP", "ZZRV-Ancien"):
    s, r = j("POST", "/applications", {"nom": nom, "description": "essai", "actif": True})
    apps[nom] = r
users = {}
for key, (prenom, entite, statut, sortie) in {"a1": ("ZZRVun", EA, "actif", None), "a2": ("ZZRVdeux", EA, "actif", None), "b1": ("ZZRVtrois", EB, "actif", None),
                                               "sortiA": ("ZZRVsorti", EA, "sorti", "2019-01-01")}.items():
    body = {"nom": "Essai", "prenom": prenom, "matricule": "ZZRV-" + key, "entite_id": entite, "statut": statut}
    if sortie:
        body["date_sortie"] = sortie
    s, r = j("POST", "/users", body)
    users[key] = r
for key, nom in (("a1", "ZZRV-ERP"), ("a1", "ZZRV-Ancien"), ("a2", "ZZRV-ERP"), ("b1", "ZZRV-ERP"), ("sortiA", "ZZRV-ERP")):
    j("POST", f"/users/{users[key]['id']}/applications", {"application_id": apps[nom]["id"], "acces": True, "note": "profil standard"})
j("PUT", f"/applications/{apps['ZZRV-Ancien']['id']}", {"nom": "ZZRV-Ancien", "description": "essai", "actif": False})
RHA = account("sec_rv_rhA", "rh", portee_globale=False, entites=[EA])
RHB = account("sec_rv_rhB", "rh", portee_globale=False, entites=[EB])
RH0 = account("sec_rv_rh0", "rh", portee_globale=False, entites=[])
LECA = account("sec_rv_lecA", "lecture", portee_globale=False, entites=[EA])
show("comptes de test crees", all((RHA, RHB, RH0, LECA)))
ZZ = lambda rows: [r for r in rows if str(r.get("matricule", "")).startswith("ZZRV-")]

print("== Anomalies ==")
s, an = j("GET", "/revues/anomalies")
mine = ZZ(an["anomalies"])
show("anomalies : salarie sorti et application desactivee", s == 200 and {(x["matricule"], x["anomalie"]) for x in mine}
     == {("ZZRV-sortiA", "salarie sorti"), ("ZZRV-a1", "application desactivee")}, [(x["matricule"], x["anomalie"]) for x in mine])
s, an = j("GET", "/revues/anomalies", token=RHA)
show("un RH ne voit que les anomalies de son perimetre", {x["matricule"] for x in ZZ(an["anomalies"])} == {"ZZRV-sortiA", "ZZRV-a1"})
s, an = j("GET", "/revues/anomalies", token=RHB)
show("un RH d'une autre entite n'en voit aucune", ZZ(an["anomalies"]) == [])
s, an = j("GET", "/revues/anomalies", token=RH0)
show("un RH sans perimetre ne voit rien", s == 200 and an["count"] == 0, an)

print("== Rapport : qui a acces a quoi ==")
s, rep = j("GET", "/revues/acces")
rows = ZZ(rep["rows"])
show("rapport complet (5 acces)", s == 200 and len(rows) == 5, len(rows))
s, repA = j("GET", "/revues/acces", token=RHA)
show("rapport d'un RH limite a son entite (4 acces)", len(ZZ(repA["rows"])) == 4 and all(r["entite"] == "ZZRV-A" for r in ZZ(repA["rows"])))
s, repF = j("GET", f"/revues/acces?application_id={apps['ZZRV-ERP']['id']}")
show("filtre par application", len(ZZ(repF["rows"])) == 4 and all(r["application"] == "ZZRV-ERP" for r in ZZ(repF["rows"])))
s, _ = j("GET", f"/revues/acces?entite_id={EB}", token=RHA)
show("filtrer sur une entite hors perimetre -> 404", s == 404, s)
s, b, h = call("GET", "/revues/acces?format=csv", token=ADM)
text = b.decode("utf-8")
show("export CSV (BOM, separateur ;, en-tete)", s == 200 and text.startswith("﻿Matricule;Salarie") and "ZZRV-a1" in text, text[:60])
s, b, h = call("GET", "/revues/acces?format=xlsx", token=ADM)
show("export Excel", s == 200 and b[:2] == b"PK" and "spreadsheetml" in h.get("Content-Type", ""), h.get("Content-Type"))

print("== Droits ==")
body = {"titre": "ZZRV revue", "echeance": str(date.today() + timedelta(days=3)), "entite_ids": [], "application_ids": [apps["ZZRV-ERP"]["id"], apps["ZZRV-Ancien"]["id"]]}
for name, tok in (("RH", RHA), ("lecture", LECA)):
    s, _ = j("POST", "/revues", body, tok)
    show(f"{name} ne lance pas de revue (403)", s == 403, s)
s, _ = call("GET", "/revues")[0], None
show("liste des revues sans jeton -> 401", s == 401, s)

print("== Rappel annuel avant toute revue ==")
with Session(engine) as ss:
    st = revue_acces.etat_rappels(ss)
    show("revue annuelle a lancer (acces existants, aucune revue cloturee)", st["annuelle"] is True and st["revue_ouverte"] is False, st)

print("== Lancement de la campagne ==")
s, rev = j("POST", "/revues", body)
show("revue lancee : 5 acces a traiter", s == 201 and rev["total"] == 5 and rev["a_traiter"] == 5 and rev["anomalies"] == 2, rev)
RID = rev["id"]
s, _ = j("POST", "/revues", body)
show("une seule revue en cours a la fois (409)", s == 409, s)
s, one = j("GET", f"/revues/{RID}")
show("detail : perimetre, compteurs", s == 200 and one["statut"] == "en_cours" and one["a_traiter"] == 5 and one["perimetre"]["entites"] == [], one)

print("== Cloisonnement des lignes ==")
s, la = j("GET", f"/revues/{RID}/lignes", token=RHA)
show("RH A : 4 lignes, aucune de l'entite B", s == 200 and la["total"] == 4 and all(l["matricule"] != "ZZRV-b1" for l in la["lignes"]), la.get("total"))
s, lb = j("GET", f"/revues/{RID}/lignes", token=RHB)
show("RH B : 1 ligne", lb["total"] == 1 and lb["lignes"][0]["matricule"] == "ZZRV-b1", lb.get("total"))
s, _ = j("GET", f"/revues/{RID}", token=RH0)
show("RH sans perimetre : revue introuvable (404)", s == 404, s)
s, li = j("GET", f"/revues/{RID}/lignes?anomalies=true", token=RHA)
show("filtre sur les anomalies (2 lignes)", li["total"] == 2, li.get("total"))
s, lq = j("GET", f"/revues/{RID}/lignes?q=ZZRVdeux", token=RHA)
show("recherche par nom (1 ligne)", lq["total"] == 1, lq.get("total"))
s, lec = j("GET", f"/revues/{RID}/lignes", token=LECA)
show("le role lecture consulte la revue de son perimetre", s == 200 and lec["total"] == 4)
s, lst = j("GET", "/revues", token=RHB)
show("liste des revues : compteurs limites au perimetre", s == 200 and lst[0]["total"] == 1, lst)

print("== Decisions ==")
byk = {(l["matricule"], l["application"]): l["id"] for l in la["lignes"]}
byb = {(l["matricule"], l["application"]): l["id"] for l in lb["lignes"]}
s, r = j("POST", f"/revues/{RID}/decisions", {"ids": [byk[("ZZRV-a1", "ZZRV-ERP")], byk[("ZZRV-a2", "ZZRV-ERP")]], "decision": "maintenu"}, RHA)
show("RH A maintient 2 acces", s == 200 and r["mises_a_jour"] == 2, r)
s, _ = j("POST", f"/revues/{RID}/decisions", {"ids": [byb[("ZZRV-b1", "ZZRV-ERP")]], "decision": "maintenu"}, RHA)
show("RH A ne decide pas sur l'entite B (404)", s == 404, s)
s, _ = j("POST", f"/revues/{RID}/decisions", {"ids": [byk[("ZZRV-a1", "ZZRV-ERP")]], "decision": "maintenu"}, LECA)
show("le role lecture ne decide pas (403)", s == 403, s)
s, _ = j("POST", f"/revues/{RID}/decisions", {"ids": [byk[("ZZRV-a1", "ZZRV-ERP")]], "decision": "peut-etre"}, RHA)
show("decision inconnue refusee (400)", s == 400, s)
s, _ = j("POST", f"/revues/{RID}/decisions", {"ids": [], "decision": "maintenu"}, RHA)
show("liste vide refusee (422)", s == 422, s)
s, r = j("POST", f"/revues/{RID}/decisions", {"ids": [byk[("ZZRV-sortiA", "ZZRV-ERP")], byk[("ZZRV-a1", "ZZRV-Ancien")]], "decision": "a_retirer",
                                               "commentaire": "Salarie parti / application arretee"}, RHA)
show("RH A marque 2 acces a retirer, avec commentaire", s == 200 and r["mises_a_jour"] == 2, r)
s, one = j("GET", f"/revues/{RID}")
show("compteurs : 2 maintenus, 2 a retirer, 1 a traiter", (one["maintenu"], one["a_retirer"], one["a_traiter"]) == (2, 2, 1), one)
s, r = j("POST", f"/revues/{RID}/cloturer", token=RHA)
show("un RH ne cloture pas (403)", s == 403, s)
s, r = j("POST", f"/revues/{RID}/cloturer")
show("cloture refusee tant qu'une ligne reste a traiter (409)", s == 409 and "1 acces" in json.dumps(r), r)
s, _ = j("GET", f"/revues/{RID}/rapport")
show("pas de rapport avant la cloture (404)", s == 404, s)
s, r = j("POST", f"/revues/{RID}/decisions", {"ids": [byb[("ZZRV-b1", "ZZRV-ERP")]], "decision": "maintenu"}, RHB)
show("RH B traite sa ligne", s == 200, r)

print("== Cloture et rapport scelle ==")
s, r = j("POST", f"/revues/{RID}/cloturer")
show("cloture : 2 acces passes a non, empreinte du rapport", s == 200 and r["acces_retires"] == 2 and len(r["empreinte"]) == 64, r)
s, b, h = call("GET", f"/revues/{RID}/rapport", token=ADM)
show("rapport PDF scelle (signature PAdES), empreinte conforme", s == 200 and b[:4] == b"%PDF" and b"/ByteRange" in b and hashlib.sha256(b).hexdigest() == r["empreinte"], (s, len(b)))
s, _, _ = call("GET", f"/revues/{RID}/rapport", token=RHA)
show("le rapport scelle est reserve a l'informatique (403)", s == 403, s)
s, ua = j("GET", f"/users/{users['sortiA']['id']}/applications")
show("l'acces du salarie sorti est passe a non (historique conserve)", any(x.get("application_id") == apps["ZZRV-ERP"]["id"] and x.get("acces") is False for x in ua), ua)
s, ua = j("GET", f"/users/{users['a2']['id']}/applications")
show("un acces maintenu reste actif", any(x.get("acces") is True for x in ua), ua)
s, _ = j("POST", f"/revues/{RID}/decisions", {"ids": [byk[("ZZRV-a2", "ZZRV-ERP")]], "decision": "a_retirer"}, RHA)
show("plus de decision apres la cloture (409)", s == 409, s)
s, _ = j("POST", f"/revues/{RID}/cloturer")
show("double cloture refusee (409)", s == 409, s)
s, one = j("GET", f"/revues/{RID}")
show("revue cloturee : statut, cloturee par, rapport", one["statut"] == "cloturee" and one["rapport"] is True and one["cloture_par"], one)
s, an = j("GET", "/revues/anomalies")
show("plus d'anomalie sur ces acces apres les retraits", ZZ(an["anomalies"]) == [], [(x["matricule"], x["anomalie"]) for x in ZZ(an["anomalies"])])

print("== Retraits a confirmer dans les applications ==")
s, rt = j("GET", "/revues/retraits")
mine = [x for x in rt if str(x.get("matricule", "")).startswith("ZZRV-")]
show("2 retraits a confirmer", s == 200 and len(mine) == 2 and {x["application"] for x in mine} == {"ZZRV-ERP", "ZZRV-Ancien"}, mine)
s, _ = j("GET", "/revues/retraits", token=RHA)
show("liste des retraits reservee a l'informatique (403)", s == 403, s)
s, r = j("POST", "/revues/retraits/confirmer", {"ids": [x["id"] for x in mine]}, RHA)
show("confirmation par un RH refusee (403)", s == 403, s)
s, r = j("POST", "/revues/retraits/confirmer", {"ids": [x["id"] for x in mine]})
show("retraits confirmes", s == 200 and r["confirmes"] == 2, r)
s, rt = j("GET", "/revues/retraits")
show("plus aucun retrait en attente", [x for x in rt if str(x.get("matricule", "")).startswith("ZZRV-")] == [])

print("== Journal ==")
s, log = j("GET", "/audit?limit=500")
log = log if isinstance(log, list) else log.get("items", [])
acts = {x.get("action") for x in log}
show("lancement, decisions, cloture et retraits sont journalises", {"revue_lancee", "revue_decision", "revue_cloturee", "revue_retrait_confirme"} <= acts, sorted(a for a in acts if str(a).startswith("revue")))
blob = json.dumps([x for x in log if str(x.get("action", "")).startswith("revue")])
show("le journal de revue ne contient ni nom ni commentaire", "ZZRVsorti" not in blob and "Essai" not in blob and "Salarie parti" not in blob)

print("== Rappels par e-mail ==")
with Session(engine) as ss:
    cfg = mailer.load_config(ss)
    show("le rappel de revue est actif par defaut", cfg.revue is True)
    st = revue_acces.etat_rappels(ss)
    show("revue annuelle : plus a lancer apres une cloture recente", st["annuelle"] is False and st["retraits_en_attente"] == 0, st)
    items = reminders.collect(ss, cfg, date.today())["revue"]
    show("aucun rappel de revue a ce stade", items == [], items)
s, rev2 = j("POST", "/revues", {"titre": "ZZRV echeance proche", "echeance": str(date.today() + timedelta(days=2)), "application_ids": [apps["ZZRV-ERP"]["id"]]})
show("seconde revue lancee (acces maintenus restants)", s == 201 and rev2["total"] >= 3, rev2)
with Session(engine) as ss:
    cfg = mailer.load_config(ss)
    items = reminders.collect(ss, cfg, date.today())["revue"]
    texte = " | ".join(x["ligne"] for x in items)
    show("rappel : echeance proche avec des acces a traiter", any(x["cle"] == "revue:echeance" for x in items), texte)
    show("le rappel ne contient ni nom ni matricule", "ZZRV" not in texte and "Essai" not in texte)
    cfg.revue = False
    show("rappel desactivable", reminders.collect(ss, cfg, date.today())["revue"] == [])
    # Retraits non confirmes depuis plus d'une semaine
    first = ss.get(__import__("app.models", fromlist=["RevueAcces"]).RevueAcces, RID)
    ligne = ss.exec(select(RevueLigne).where(RevueLigne.revue_id == RID)).first()
    ligne.retrait = "a_faire"
    first.cloture_le = datetime.utcnow() - timedelta(days=10)
    ss.add(ligne)
    ss.add(first)
    ss.commit()
    st = revue_acces.etat_rappels(ss)
    show("retrait non confirme depuis plus de 7 jours : compte pour le rappel", st["retraits_en_attente"] == 1, st)

print("== Purge RGPD ==")
with Session(engine) as ss:
    avant = len(ss.exec(select(RevueLigne).where(RevueLigne.user_id == users["sortiA"]["id"])).all())
s, pv = j("GET", "/rgpd/purge-preview")
show("le salarie sorti en 2019 est a purger", users["sortiA"]["id"] in {c["id"] for c in pv["candidats"]} and avant >= 1, avant)
s, r = j("POST", "/rgpd/purge", {"ids": [users["sortiA"]["id"]]})
show("la purge ne bute pas sur ses lignes de revue", s == 200 and r["count"] == 1, (s, r))
with Session(engine) as ss:
    apres = len(ss.exec(select(RevueLigne).where(RevueLigne.user_id == users["sortiA"]["id"])).all())
show("les lignes de revue du salarie purge sont supprimees", apres == 0, apres)

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
