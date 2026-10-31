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

"""Parcours d'arrivee (GET /arrivee/{id}) : avancement par etape, portee par entite, donnees renvoyees.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/arrivee_check.py

Organisation de test : un groupe ZZAR-G avec deux filiales (A, B). Cree des donnees ZZAR et des comptes sec_ar*
(nettoyage : tests/cleanup_test_data.sql). L'etape de signature n'est pas rejouee ici (voir signature_check.py).
Code de sortie 1 si un test echoue. ASCII uniquement.
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
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:200] if detail else ""))


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


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        accs = j("GET", "/auth/accounts")[1]
        acc = next(a for a in accs if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


def parcours(uid, token):
    return j("GET", "/arrivee/%d" % uid, token=token)


def etat(r, cle):
    return next((e["etat"] for e in r.get("etapes", []) if e["cle"] == cle), None)


print("== Organisation de test ==")
ent = {}
for code, parent in [("ZZAR-G", None), ("ZZAR-A", "ZZAR-G"), ("ZZAR-B", "ZZAR-G")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZAR-A"], ent["ZZAR-B"]
users = {}
for key, eid in [("A", EA), ("B", EB)]:
    s, r = j("POST", "/users", {"matricule": "ZZAR-U" + key, "nom": "ZZARNom" + key, "prenom": "Zoe", "entite_id": eid,
                                  "statut": "prevu", "date_arrivee": "2026-12-01"})
    users[key] = r
show("2 salaries prevus crees (A et B)", all(isinstance(u, dict) and "id" in u for u in users.values()), users)
UA, UB = users["A"]["id"], users["B"]["id"]
s, asset = j("POST", "/assets", {"type": "ZZAR type", "marque": "ZZAR", "modele": "M1", "numero_serie": "ZZAR-SN-A1", "entite_id": EA})
s, app = j("POST", "/applications", {"nom": "ZZAR app", "entite_id": None})
s, choix = j("GET", "/besoins/choix")
CAT = choix[0]["nom"] if isinstance(choix, list) and choix else None
show("un actif, une application et une categorie de besoin disponibles", "id" in asset and "id" in app and CAT, (asset, app, choix))

print("== Comptes ==")
account("sec_ar_it", "informatique")
account("sec_ar_rh0", "rh")
account("sec_ar_rhA", "rh", portee_globale=False, entites=[EA])
account("sec_ar_rhB", "rh", portee_globale=False, entites=[EB])
account("sec_ar_lecA", "lecture", portee_globale=False, entites=[EA])
IT, R0, RA, RB, LA = (login(n, PW) for n in ("sec_ar_it", "sec_ar_rh0", "sec_ar_rhA", "sec_ar_rhB", "sec_ar_lecA"))
show("connexions de test", all([IT, R0, RA, RB, LA]))

print("== Acces ==")
s, b = call("GET", "/arrivee/%d" % UA)
show("sans jeton : refuse", s in (401, 403), s)
s, r = parcours(999999, IT)
show("salarie inconnu : 404", s == 404, s)
s, r = j("GET", "/besoins", token=RA)
show("prealable : un RH ne peut pas lire le suivi des besoins", s == 403, s)

print("== Etapes : salarie sans besoin ==")
s, r = parcours(UA, RA)
show("un RH lit le parcours de son salarie", s == 200, s)
show("etapes : fiche faite, le reste a faire", [e["etat"] for e in r["etapes"]] == ["fait", "a_faire", "a_faire", "a_faire", "a_faire"],
     [e["etat"] for e in r["etapes"]])
show("etape courante = besoins, prochaine action pour les RH", r["etape_courante"] == "besoins" and r["prochaine_action"]["qui"] == "rh", r["prochaine_action"])

print("== Etapes : besoin saisi par les RH ==")
s, bes = j("POST", "/besoins", {"user_id": UA, "type": CAT}, token=RA)
show("un RH saisit un besoin", s == 201, bes)
s, r = parcours(UA, RA)
show("besoins fait, preparation a faire", etat(r, "besoins") == "fait" and etat(r, "preparation") == "a_faire", [e["etat"] for e in r["etapes"]])
show("prochaine action : l'informatique prepare, lien vers ses besoins",
     r["prochaine_action"]["qui"] == "informatique" and r["prochaine_action"]["vers"] == "/besoins?user=%d" % UA, r["prochaine_action"])
show("le RH voit le besoin et son statut", r["besoins"] and r["besoins"][0]["type"] == CAT and r["besoins"][0]["statut"] == "demande", r["besoins"])

print("== Etapes : preparation, remise, acces ==")
s, _ = j("POST", "/besoins/%d/statut" % bes["id"], {"statut": "en_preparation"})
show("l'informatique passe le besoin en preparation", s == 200, s)
s, r = parcours(UA, IT)
show("besoin en preparation : etape en cours", etat(r, "preparation") == "en_cours", [e["etat"] for e in r["etapes"]])
s, asg = j("POST", "/assignments", {"user_id": UA, "asset_ids": [asset["id"]], "besoin_ids": [bes["id"]], "sans_charte": True})
show("remise creee avec le besoin", s in (200, 201) and "id" in asg, asg)
s, r = parcours(UA, IT)
show("besoin satisfait : preparation faite, remise en cours",
     etat(r, "preparation") == "fait" and etat(r, "remise") == "en_cours", [e["etat"] for e in r["etapes"]])
show("prochaine action : faire signer cette remise", r["prochaine_action"]["vers"] == "/signer/remise/%d" % asg["id"], r["prochaine_action"])
s, ua = j("POST", "/users/%d/applications" % UA, {"application_id": app["id"], "acces": True})
s, r = parcours(UA, IT)
show("acces accorde : etape faite", etat(r, "acces") == "fait", [e["etat"] for e in r["etapes"]])
show("le journal cite l'acces et reste borne", any("ZZAR app" in e["texte"] for e in r["journal"]) and len(r["journal"]) <= 12, r["journal"][:3])
quand = [e["quand"] for e in r["journal"]]
show("journal du plus recent au plus ancien", quand == sorted(quand, reverse=True), quand[:3])

print("== Remise directe, sans besoin saisi ==")
s, uc = j("POST", "/users", {"matricule": "ZZAR-UC", "nom": "ZZARNomC", "prenom": "Zoe", "entite_id": EA, "statut": "prevu"})
s, asset2 = j("POST", "/assets", {"type": "ZZAR type", "marque": "ZZAR", "modele": "M2", "numero_serie": "ZZAR-SN-C1", "entite_id": EA})
s, asg2 = j("POST", "/assignments", {"user_id": uc["id"], "asset_ids": [asset2["id"]], "sans_charte": True})
s, r = parcours(uc["id"], RA)
show("remise sans besoin : besoins et preparation sans objet, remise a signer",
     [e["etat"] for e in r["etapes"]] == ["fait", "fait", "fait", "en_cours", "a_faire"] and r["etape_courante"] == "remise",
     [e["etat"] for e in r["etapes"]])

print("== Besoin annule ignore ==")
s, bes2 = j("POST", "/besoins", {"user_id": UA, "type": CAT}, token=RA)
s, _ = j("POST", "/besoins/%d/statut" % bes2["id"], {"statut": "annule"})
show("le second besoin est annule", s == 200, s)
s, r = parcours(UA, IT)
show("un besoin annule ne change pas l'avancement", etat(r, "besoins") == "fait" and etat(r, "preparation") == "fait" and "1 besoin" in next(e for e in r["etapes"] if e["cle"] == "besoins")["detail"],
     [e["detail"] for e in r["etapes"]])

print("== Portee par entite ==")
for who, tok, uid, attendu in [("RH A, salarie A", RA, UA, 200), ("RH A, salarie B", RA, UB, 404), ("RH B, salarie A", RB, UA, 404),
                               ("RH B, salarie B", RB, UB, 200), ("lecture A, salarie A", LA, UA, 200), ("lecture A, salarie B", LA, UB, 404),
                               ("RH sans portee, salarie A", R0, UA, 404), ("informatique, salarie B", IT, UB, 200)]:
    s, r = parcours(uid, tok)
    show("portee - " + who, s == attendu, s)

print("== Donnees renvoyees ==")
s, b = call("GET", "/arrivee/%d" % UA, token=RA)
texte = b.decode()
for interdit in ("cree_par", "traite_par", "numero_serie", "ZZAR-SN", "sec_ar", "commentaire", "email", "assignment_id"):
    show("la reponse ne contient pas : " + interdit, interdit not in texte)
s, r = parcours(UA, RA)
show("champs du salarie limites", set(r["salarie"]) == {"id", "nom", "prenom", "matricule", "service", "entite_id", "statut", "date_arrivee"}, sorted(r["salarie"]))

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
