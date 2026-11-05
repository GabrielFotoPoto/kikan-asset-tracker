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


"""Suppression de salaries en lot : simulation, garde-fous (affectation, acces, besoin), perimetre, droits, journal RGPD.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/users_suppression_lot_check.py

Cree des donnees marquees ZZUSL et comptes sec_usl* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
PW = "Sec-Test-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=90)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(user, pw):
    s, b = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


T = login(os.environ.get("TEST_ADMIN_USER", "admin"), os.environ.get("TEST_ADMIN_PASSWORD", ""))
if not T:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None, token=None):
    s, b = call(method, path, body, token or T)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def salarie(n, entite_id=None):
    s, u = j("POST", "/users", {"matricule": f"ZZUSL-{n}", "nom": f"NomSecret{n}ZZ", "prenom": f"ZZPrenomSecret{n}",
                                "email": f"zzusl.{n}@exemple.test", "entite_id": entite_id})
    assert s == 201, (s, u)
    return u["id"]


def existe(user_id):
    return j("GET", f"/users/{user_id}")[0] == 200


print("== Simulation ==")
u1, u2, u3 = salarie(1), salarie(2), salarie(3)
s, r = j("POST", "/users/suppression-lot", {"ids": [u1, u2]})
show("la simulation est le comportement par defaut", s == 200 and r["simulation"] is True and sorted(r["supprimes"]) == sorted([u1, u2]), r)
show("la simulation decrit les salaries concernes (matricule, nom, prenom)", len(r["apercu"]) == 2
     and {x["matricule"] for x in r["apercu"]} == {"ZZUSL-1", "ZZUSL-2"}
     and all("nom" in x and "prenom" in x for x in r["apercu"]), r["apercu"])
show("la simulation ne supprime rien", existe(u1) and existe(u2))

print("== Suppression reelle ==")
s, r = j("POST", "/users/suppression-lot", {"ids": [u1, u2, u1], "simulation": False})
show("suppression reelle, doublons ignores, apercu vide", s == 200 and sorted(r["supprimes"]) == sorted([u1, u2])
     and r["refuses"] == [] and r["apercu"] == [], r)
show("les salaries ont disparu", not existe(u1) and not existe(u2))
show("un autre salarie n'est pas touche", existe(u3))

print("== Garde-fous (affectation, acces applicatif, besoin, introuvable) ==")
u_aff, u_app, u_bes = salarie(4), salarie(5), salarie(6)
s, a = j("POST", "/assets", {"identifiant_interne": "ZZUSL-A1", "type": "ZZUSL portable", "marque": "ZZUSL", "modele": "M1", "numero_serie": "ZZUSL-SN-1"})
show("actif cree pour remise", s == 201, a if s != 201 else "")
s, asg = j("POST", "/assignments", {"user_id": u_aff, "asset_ids": [a["id"]], "sans_charte": True})
show("affectation creee", s == 201, asg if s != 201 else "")

s, app_obj = j("POST", "/applications", {"nom": "ZZUSL App"})
show("application creee", s == 201, app_obj if s != 201 else "")
s, ua = j("POST", f"/users/{u_app}/applications", {"application_id": app_obj["id"], "acces": True})
show("acces applicatif cree", s == 201, ua if s != 201 else "")

j("POST", "/parametres/categories-besoin", {"nom": "ZZUSL Cat", "gammes": []})
s, bes = j("POST", "/besoins", {"user_id": u_bes, "type": "ZZUSL Cat"})
show("besoin cree", s == 201, bes if s != 201 else "")

s, r = j("POST", "/users/suppression-lot", {"ids": [u_aff, u_app, u_bes, u3, 99999999], "simulation": False})
raisons = {x["id"]: x["raison"] for x in r["refuses"]} if s == 200 else {}
show("salarie avec affectation refuse avec le libelle standard", s == 200 and u_aff in raisons
     and "affectation(s) de materiel" in raisons[u_aff] and "statut sorti" in raisons[u_aff] and "purge rgpd" in raisons[u_aff].lower(), raisons.get(u_aff))
show("salarie avec acces applicatif refuse avec le libelle standard", u_app in raisons
     and "acces applicatif(s)" in raisons[u_app] and "purge rgpd" in raisons[u_app].lower(), raisons.get(u_app))
show("salarie avec besoin refuse avec le libelle standard", u_bes in raisons
     and "besoin(s) de materiel" in raisons[u_bes] and "purge rgpd" in raisons[u_bes].lower(), raisons.get(u_bes))
show("identifiant inexistant refuse (Salarie introuvable)", raisons.get(99999999) == "Salarie introuvable", raisons.get(99999999))
show("les refus ne contiennent que id et raison (aucune donnee personnelle)",
     all(set(x.keys()) == {"id", "raison"} and "NomSecret" not in json.dumps(x) and "ZZPrenomSecret" not in json.dumps(x) and "ZZUSL-" not in json.dumps(x)
         for x in r["refuses"]), r["refuses"])
show("le salarie sans historique du meme lot est supprime", r.get("supprimes") == [u3] and not existe(u3), r)
show("les salaries refuses sont conserves", existe(u_aff) and existe(u_app) and existe(u_bes))

print("== Limites, droits et perimetre ==")
s, _ = j("POST", "/users/suppression-lot", {"ids": []})
show("liste vide : 422", s == 422, s)
s, _ = j("POST", "/users/suppression-lot", {"ids": list(range(1, 502))})
show("plus de 500 identifiants : 422", s == 422, s)
s, _ = call("POST", "/users/suppression-lot", {"ids": [u_aff]})
show("sans jeton : refuse", s in (401, 403), s)

s, ent_a = j("POST", "/entites", {"code": "ZZUSL-A", "nom": "ZZUSL-A"})
if s == 409:
    ent_a = next(e for e in j("GET", "/entites")[1] if e["code"] == "ZZUSL-A")
s, ent_b = j("POST", "/entites", {"code": "ZZUSL-B", "nom": "ZZUSL-B"})
if s == 409:
    ent_b = next(e for e in j("GET", "/entites")[1] if e["code"] == "ZZUSL-B")
EA, EB = ent_a["id"], ent_b["id"]
u_ea, u_eb = salarie(7, EA), salarie(8, EB)

for uname, role in (("sec_usl_rh", "rh"), ("sec_usl_lec", "lecture")):
    j("POST", "/auth/accounts", {"username": uname, "password": PW, "role": role, "portee_globale": False, "entites": [EA]})
    tok = login(uname, PW)
    s, _ = j("POST", "/users/suppression-lot", {"ids": [u_ea, u_eb], "simulation": False}, token=tok)
    show(f"role {role} refuse (403, reserve a l'informatique)", s == 403, s)
show("les salaries n'ont pas ete touches par les appels refuses", existe(u_ea) and existe(u_eb))

# Verification directe du filtre de perimetre dans delete_users_batch : un Scope restreint a EA refuse u_eb avec "Salarie introuvable" sans rien reveler.
sys.path.insert(0, "/app")
from sqlmodel import Session  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Account, Role  # noqa: E402
from app.routers.users import SuppressionLot, delete_users_batch  # noqa: E402
from app.scope import expand_scope  # noqa: E402

with Session(engine) as sess:
    sc_a = expand_scope(sess, {EA})
    fake_admin = Account(username="sec_usl_admin", password_hash="x", role=Role.informatique)
    sim_sc = delete_users_batch(SuppressionLot(ids=[u_ea, u_eb], simulation=True), session=sess, scope=sc_a, account=fake_admin)
    show("perimetre restreint (simulation) : hors perimetre refuse comme introuvable sans rien reveler",
         sim_sc["supprimes"] == [u_ea] and sim_sc["refuses"] == [{"id": u_eb, "raison": "Salarie introuvable"}], sim_sc)
    app_sc = delete_users_batch(SuppressionLot(ids=[u_ea, u_eb], simulation=False), session=sess, scope=sc_a, account=fake_admin)
    show("perimetre restreint (application) : seul le salarie du perimetre est supprime, hors perimetre intact",
         app_sc["supprimes"] == [u_ea] and app_sc["refuses"] == [{"id": u_eb, "raison": "Salarie introuvable"}]
         and not existe(u_ea) and existe(u_eb), app_sc)

print("== Journal (RGPD) ==")
s, log = j("GET", "/audit?limit=100")
rows = log if isinstance(log, list) else log.get("items", [])
lot_rows = [x for x in rows if x.get("action") == "suppression" and str(x.get("target") or "").startswith("users/") and x.get("detail") == "suppression en lot"]
show("une entree d'audit par salarie supprime en lot", {x["target"] for x in lot_rows} >= {f"users/{u1}", f"users/{u2}", f"users/{u3}", f"users/{u_ea}"}, [x["target"] for x in lot_rows][:6])
dump = json.dumps(lot_rows)
show("RGPD : aucune donnee personnelle (nom, prenom, e-mail, matricule) dans le journal",
     "NomSecret" not in dump and "ZZPrenomSecret" not in dump and "zzusl." not in dump and "ZZUSL-" not in dump, lot_rows[:2])

if fails:
    sys.exit(f"{fails} test(s) en echec")
print("Tous les tests passent.")
