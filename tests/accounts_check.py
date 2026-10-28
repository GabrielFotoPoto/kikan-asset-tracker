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

"""Tests de la gestion des comptes : creation, mot de passe provisoire, revocation de sessions, garde-fous.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/accounts_check.py

Cree des comptes sec_ac* (nettoyage : tests/cleanup_test_data.sql). Fichier ASCII uniquement.
Code de sortie 1 si un test echoue.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:150] if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def j(method, path, body=None, token=None):
    s, b = call(method, path, body, token)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def login(user, pw):
    s, r = j("POST", "/auth/login", {"username": user, "password": pw})
    return (r["access_token"], r) if s == 200 else (None, r)


def detail(r):
    return r.get("detail", "") if isinstance(r, dict) else str(r)


ADM, _ = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")
s, me = j("GET", "/auth/me", token=ADM)
ADMIN_ID = me["id"]
PROV_RE = re.compile(r"^[A-Za-z0-9]{4}(-[A-Za-z0-9]{4}){3}$")
STRONG = "Un-Mot-De-Passe-Solide-2026"
secrets_seen = []


def create(body):
    return j("POST", "/auth/accounts", body, ADM)


print("== Roles ==")
s, r = create({"username": "sec_acrh", "role": "rh"})
RH_ID, RH_PROV = r["id"], r["mot_de_passe_provisoire"]
secrets_seen.append(RH_PROV)
s, r2 = j("POST", "/auth/change-password", {"old_password": RH_PROV, "new_password": STRONG}, login("sec_acrh", RH_PROV)[0])
RH = r2["access_token"]
s, r = create({"username": "sec_aclect", "role": "lecture", "password": STRONG})
LECT, _ = login("sec_aclect", STRONG)
for name, tok in (("RH", RH), ("lecture", LECT)):
    show(f"{name} : liste des comptes refusee (403)", j("GET", "/auth/accounts", token=tok)[0] == 403)
    show(f"{name} : creation refusee (403)", j("POST", "/auth/accounts", {"username": "sec_acnope", "role": "rh"}, tok)[0] == 403)
    show(f"{name} : modification refusee (403)", j("PUT", f"/auth/accounts/{ADMIN_ID}", {"actif": False}, tok)[0] == 403)
    show(f"{name} : reinitialisation refusee (403)", j("POST", f"/auth/accounts/{ADMIN_ID}/reset-password", None, tok)[0] == 403)
show("sans jeton : refuse (401)", j("GET", "/auth/accounts")[0] == 401 and j("POST", f"/auth/accounts/{ADMIN_ID}/reset-password")[0] == 401)

print("== Identifiant ==")
for name, uname in (("trop court", "ab"), ("espace", "sec ac bad"), ("debut par un tiret", "-sec_acbad"),
                    ("65 caracteres", "s" * 65), ("caractere accentue", "sec_ac" + chr(233) + chr(233)),
                    ("caractere special", "sec_ac$bad"), ("vide", "")):
    s, r = create({"username": uname, "role": "rh"})
    show(f"identifiant refuse : {name}", s == 422, f"HTTP {s}")
s, up = create({"username": "SEC_ACUpper", "role": "lecture"})
show("majuscules ramenees en minuscules", s == 201 and up["username"] == "sec_acupper", up.get("username"))
s, r = create({"username": "sec_acUPPER", "role": "rh"})
show("doublon en casse differente -> 409", s == 409, detail(r))
s, r = create({"username": "Admin", "role": "rh"})
show("ne peut pas doubler 'admin' avec une autre casse", s == 409, detail(r))
s, r = create({"username": "sec_acmail", "role": "rh", "email": "pas-un-mail"})
show("e-mail invalide -> 422", s == 422)
s, r = create({"username": "sec_acnom", "role": "rh", "nom_affiche": "  Alice    Durand  ", "email": " alice@exemple.fr "})
show("nom nettoye et e-mail accepte", s == 201 and r["nom_affiche"] == "Alice Durand" and r["email"] == "alice@exemple.fr", r)
NOM_ID = r["id"]

print("== Mot de passe provisoire ==")
s, c = create({"username": "sec_acprov", "role": "rh", "nom_affiche": "Test Provisoire"})
PROV, PID = c["mot_de_passe_provisoire"], c["id"]
secrets_seen.append(PROV)
show("mot de passe provisoire genere (XXXX-XXXX-XXXX-XXXX)", s == 201 and PROV_RE.match(PROV or "") is not None, PROV and PROV[:4] + "...")
show("changement impose, derniere connexion vide", c["must_change_password"] is True and c["derniere_connexion"] is None)
s, lst = j("GET", "/auth/accounts", token=ADM)
row = next(a for a in lst if a["id"] == PID)
show("la liste ne contient jamais le mot de passe", "mot_de_passe_provisoire" not in row and PROV not in json.dumps(lst))
s, c2 = create({"username": "sec_acprov2", "role": "rh"})
show("deux comptes : deux mots de passe differents", c2["mot_de_passe_provisoire"] != PROV)
secrets_seen.append(c2["mot_de_passe_provisoire"])
s, r = create({"username": "sec_acweak", "role": "rh", "password": "court"})
show("mot de passe fourni trop court -> 400", s == 400, detail(r))
s, r = create({"username": "sec_acleg", "role": "rh", "password": STRONG})
show("mot de passe fourni (scripts) : pas de changement force", s == 201 and r["must_change_password"] is False and r["mot_de_passe_provisoire"] is None)

print("== Connexion avec le mot de passe provisoire ==")
T0, lr = login("sec_acprov", PROV)
show("connexion acceptee, changement signale", T0 is not None and lr["must_change_password"] is True, lr if T0 is None else "")
T0u, _ = login("SEC_ACPROV", PROV)
show("connexion insensible a la casse de l'identifiant", T0u is not None)
s, me2 = j("GET", "/auth/me", token=T0)
show("/auth/me accessible, avec l'indicateur", s == 200 and me2["must_change_password"] is True)
for path in ("/users", "/assets", "/entites", "/stats", "/reports/holdings?format=json", "/audit"):
    s, r = j("GET", path, token=T0)
    show(f"GET {path} bloque tant que le mot de passe est provisoire (403)", s == 403 and "mot de passe" in detail(r), f"HTTP {s}")
s, r = j("POST", "/users", {"prenom": "a", "nom": "b"}, T0)
show("ecritures bloquees aussi (403)", s == 403)
s, lst = j("GET", "/auth/accounts", token=ADM)
show("derniere connexion renseignee", next(a for a in lst if a["id"] == PID)["derniere_connexion"] is not None)

print("== Changement du mot de passe ==")
s, r = j("POST", "/auth/change-password", {"old_password": "faux-faux-faux-1", "new_password": STRONG}, T0)
show("ancien mot de passe incorrect -> 400", s == 400)
s, r = j("POST", "/auth/change-password", {"old_password": PROV, "new_password": PROV}, T0)
show("nouveau identique a l'ancien -> 400", s == 400 and "different" in detail(r), detail(r))
s, r = j("POST", "/auth/change-password", {"old_password": PROV, "new_password": "court"}, T0)
show("nouveau trop court -> 400", s == 400)
s, r = j("POST", "/auth/change-password", {"old_password": PROV, "new_password": STRONG}, T0)
T1 = r.get("access_token")
show("changement accepte, nouveau jeton renvoye", s == 200 and T1 and r["must_change_password"] is False, r if s != 200 else "")
show("l'ancien jeton est revoque (401)", j("GET", "/auth/me", token=T0)[0] == 401)
show("le nouveau jeton ouvre l'acces", j("GET", "/users", token=T1)[0] == 200)
show("l'ancien mot de passe ne fonctionne plus", login("sec_acprov", PROV)[0] is None)
T2, lr2 = login("sec_acprov", STRONG)
show("connexion avec le nouveau mot de passe, sans changement force", T2 is not None and lr2["must_change_password"] is False)

print("== Revocation des sessions ==")
show("session ouverte avant changements", j("GET", "/users", token=T2)[0] == 200)
s, r = j("PUT", f"/auth/accounts/{PID}", {"role": "lecture"}, ADM)
show("changement de role accepte", s == 200 and r["role"] == "lecture")
show("changement de role : session ouverte revoquee (401)", j("GET", "/users", token=T2)[0] == 401)
T3, _ = login("sec_acprov", STRONG)
s, r = j("POST", "/users", {"prenom": "a", "nom": "b"}, T3)
show("nouvelle session : droits du nouveau role (ecriture refusee)", j("GET", "/users", token=T3)[0] == 200 and s == 403)
s, r = j("PUT", f"/auth/accounts/{PID}", {"actif": False}, ADM)
show("desactivation : session revoquee aussitot (401)", s == 200 and j("GET", "/users", token=T3)[0] == 401)
show("desactivation : connexion refusee", login("sec_acprov", STRONG)[0] is None)
s, r = j("PUT", f"/auth/accounts/{PID}", {"actif": True}, ADM)
T4, _ = login("sec_acprov", STRONG)
show("reactivation : connexion de nouveau possible", s == 200 and T4 is not None)
s, r = j("PUT", f"/auth/accounts/{PID}", {"password": "Autre-Mot-De-Passe-2026"}, ADM)
show("mot de passe change par l'API : session revoquee", s == 200 and j("GET", "/users", token=T4)[0] == 401)
s, r = j("PUT", f"/auth/accounts/{NOM_ID}", {"nom_affiche": "Alice Martin", "email": ""}, ADM)
show("modification du nom, e-mail efface", s == 200 and r["nom_affiche"] == "Alice Martin" and r["email"] is None, r)
s, r = j("PUT", f"/auth/accounts/{NOM_ID}", {"email": "mauvais"}, ADM)
show("e-mail invalide a la modification -> 422", s == 422)

print("== Reinitialisation ==")
s, c3 = create({"username": "sec_acreset", "role": "rh"})
secrets_seen.append(c3["mot_de_passe_provisoire"])
RT, _ = login("sec_acreset", c3["mot_de_passe_provisoire"])
s, r = j("POST", "/auth/change-password", {"old_password": c3["mot_de_passe_provisoire"], "new_password": STRONG}, RT)
RT = r["access_token"]
show("compte operationnel avant reinitialisation", j("GET", "/users", token=RT)[0] == 200)
s, rs = j("POST", f"/auth/accounts/{c3['id']}/reset-password", None, ADM)
NEWP = rs.get("mot_de_passe_provisoire")
secrets_seen.append(NEWP)
show("reinitialisation : nouveau mot de passe provisoire", s == 200 and PROV_RE.match(NEWP or "") and NEWP != c3["mot_de_passe_provisoire"])
show("reinitialisation : session ouverte revoquee", j("GET", "/users", token=RT)[0] == 401)
show("reinitialisation : l'ancien mot de passe ne marche plus", login("sec_acreset", STRONG)[0] is None)
RT2, lr3 = login("sec_acreset", NEWP)
show("reinitialisation : changement impose a la connexion", RT2 is not None and lr3["must_change_password"] is True and j("GET", "/users", token=RT2)[0] == 403)
show("reinitialisation d'un compte inconnu -> 404", j("POST", "/auth/accounts/999999/reset-password", None, ADM)[0] == 404)

print("== Garde-fous ==")
s, r = j("PUT", f"/auth/accounts/{ADMIN_ID}", {"actif": False}, ADM)
show("on ne peut pas desactiver son propre compte (409)", s == 409 and "propre" in detail(r), detail(r))
s, me3 = j("GET", "/auth/me", token=ADM)
show("le compte courant reste actif", me3["actif"] is True and j("GET", "/auth/accounts", token=ADM)[0] == 200)
s, r = j("PUT", "/auth/accounts/999999", {"actif": False}, ADM)
show("compte inconnu -> 404", s == 404)

print("== Journal d'audit ==")
s, log = j("GET", "/audit?limit=500", token=ADM)
acts = {x["action"] for x in log}
show("creation, modification, reinitialisation et changement journalises",
     {"compte_cree", "compte_modifie", "mot_de_passe_reinitialise", "mot_de_passe_change"} <= acts, sorted(a for a in acts if "compte" in a or "mot_de" in a))
blob = json.dumps(log)
show("journal : aucun mot de passe (provisoire ou choisi)", not any(p and p in blob for p in secrets_seen) and STRONG not in blob)
mods = [x for x in log if x["action"] == "compte_modifie" and x["target"] == "sec_acprov"]
show("journal : modifications decrites par noms de champs", any(x["detail"] in ("role", "actif", "password") for x in mods), [x["detail"] for x in mods])

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
