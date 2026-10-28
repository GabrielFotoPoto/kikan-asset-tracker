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

"""Etancheite du cloisonnement par entite (B2) : comptes RH et lecture limites a des entites.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/scope_check.py

Organisation de test : un groupe ZZSC-G avec trois filiales (A, B, C) et un site sous A. Cree des donnees ZZSC et des
comptes sec_sc* (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. ASCII uniquement.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


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


def ids_of(rows):
    return {r["id"] for r in rows}


def account(name, role, **scope):
    body = {"username": name, "password": PW, "role": role, **scope}
    s, r = j("POST", "/auth/accounts", body)
    if s == 409:
        accs = j("GET", "/auth/accounts")[1]
        acc = next(a for a in accs if a["username"] == name.lower())
        s, r = j("PUT", "/auth/accounts/%d" % acc["id"], {"actif": True, "role": role, "password": PW, **scope})
    return s, r


def upload(path, fields, token):
    bnd = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode())
    parts.append(('--%s\r\nContent-Disposition: form-data; name="file"; filename="c.md"\r\nContent-Type: text/markdown\r\n\r\n'
                  '# Charte ZZSC\n\nTexte de test.\r\n--%s--\r\n' % (bnd, bnd)).encode())
    req = urllib.request.Request(B + path, data=b"".join(parts), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + bnd})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


print("== Organisation de test ==")
ent = {}
for code, parent in [("ZZSC-G", None), ("ZZSC-A", "ZZSC-G"), ("ZZSC-B", "ZZSC-G"), ("ZZSC-C", "ZZSC-G"), ("ZZSC-A1", "ZZSC-A")]:
    s, r = j("POST", "/entites", {"code": code, "nom": code, "code_parent": parent})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB, EC, EA1, EG = ent["ZZSC-A"], ent["ZZSC-B"], ent["ZZSC-C"], ent["ZZSC-A1"], ent["ZZSC-G"]
show("5 entites creees", len(ent) == 5)

users = {}
for key, eid in [("A", EA), ("A1", EA1), ("B", EB), ("N", None)]:
    s, r = j("POST", "/users", {"matricule": "ZZSC-" + key, "nom": "ZZSC" + key, "prenom": "ZZSC-" + key, "entite_id": eid})
    users[key] = r
show("salaries A, A1 (site), B et sans entite", all(isinstance(u, dict) and "id" in u for u in users.values()), users)

assets, asg = {}, {}
for key, eid in [("A", EA), ("B", EB), ("N", None)]:
    s, r = j("POST", "/assets", {"type": "ZZSC type", "marque": "ZZSC", "modele": "M" + key, "numero_serie": "ZZSC-SN-" + key,
                                   "identifiant_interne": "ZZSC-ID-" + key, "entite_id": eid})
    assets[key] = r
for key in ("A", "B"):
    s, r = j("POST", "/assignments", {"user_id": users[key]["id"], "asset_ids": [assets[key]["id"]]})
    asg[key] = r
show("materiel et remises creees", all("id" in a for a in assets.values()) and all("id" in a for a in asg.values()), (assets, asg))

apps = {}
for key, eid in [("A", EA), ("B", EB), ("C", None)]:
    s, r = j("POST", "/applications", {"nom": "ZZSC app " + key, "entite_id": eid})
    apps[key] = r

print("== Comptes et portee ==")
s, r = account("sec_sc_it", "informatique")
show("compte informatique cree : global", s in (200, 201) and r["portee_globale"] is True, r)
s, r = account("sec_sc_it2", "informatique", portee_globale=False, entites=[EA])
show("informatique cloisonne refuse (toujours administrateur)", s == 400, r)
s, r = account("sec_sc_rh0", "rh")
show("RH sans portee a la creation : aucune portee", s in (200, 201) and r["portee_globale"] is False and r["entites"] == [], r)
s, r = account("sec_sc_rhA", "rh", portee_globale=False, entites=[EA])
show("RH limite a l'entite A", s in (200, 201) and r["entites"] == [EA], r)
account("sec_sc_rhB", "rh", portee_globale=False, entites=[EB])
s, r = account("sec_sc_rhG", "rh", portee_globale=True)
show("RH global", r.get("portee_globale") is True, r)
account("sec_sc_lecA", "lecture", portee_globale=False, entites=[EA])
s, r = account("sec_sc_bad", "rh", portee_globale=False, entites=[999999])
show("entite inconnue dans la portee -> 400", s == 400, r)
s, r = account("sec_sc_bad2", "rh", portee_globale=True, entites=[EA])
show("globale + entites -> 400", s == 400, r)

IT, R0, RA, RB, RG, LA = (login(n, PW) for n in ("sec_sc_it", "sec_sc_rh0", "sec_sc_rhA", "sec_sc_rhB", "sec_sc_rhG", "sec_sc_lecA"))
show("connexions de test", all([IT, R0, RA, RB, RG, LA]))
s, me = j("GET", "/auth/me", token=RA)
show("/auth/me : portee effective = A et son site", me["portee"]["entites"] == sorted([EA, EA1]) and not me["portee"]["globale"], me.get("portee"))
s, me = j("GET", "/auth/me", token=IT)
show("/auth/me informatique : globale", me["portee"]["globale"] is True)
s, me = j("GET", "/auth/me", token=R0)
show("/auth/me RH sans portee : vide", me["portee"]["vide"] is True)

print("== Salaries ==")
for who, tok, expect in [("informatique", IT, {"A", "A1", "B", "N"}), ("RH global", RG, {"A", "A1", "B", "N"}),
                         ("RH A", RA, {"A", "A1"}), ("RH B", RB, {"B"}), ("lecture A", LA, {"A", "A1"}), ("RH sans portee", R0, set())]:
    s, rows = j("GET", "/users", token=tok)
    mine = {k for k, u in users.items() if u["id"] in ids_of(rows)}
    show("liste salaries - " + who, s == 200 and mine == expect, sorted(mine))
s, r = j("GET", "/users/%d" % users["B"]["id"], token=RA)
show("salarie d'une autre filiale -> 404", s == 404, r)
s, r = j("GET", "/users/%d" % users["N"]["id"], token=RA)
show("salarie sans entite : invisible d'un compte cloisonne", s == 404)
s, r = j("GET", "/users/%d" % users["A1"]["id"], token=RA)
show("salarie du site (sous-entite) visible", s == 200)
s, r = j("GET", "/users?entite_id=%d" % EB, token=RA)
show("filtre entite hors portee : liste vide", s == 200 and r == [])
s, r = j("PUT", "/users/%d" % users["B"]["id"], {"matricule": "ZZSC-B", "nom": "X", "prenom": "X", "entite_id": EB}, token=RA)
show("modifier un salarie hors portee -> 404", s == 404)
s, r = j("PUT", "/users/%d" % users["A"]["id"], {"matricule": "ZZSC-A", "nom": "ZZSCA", "prenom": "ZZSC-A", "entite_id": EB}, token=RA)
show("deplacer un salarie vers une entite hors portee -> 403", s == 403, r)
s, r = j("POST", "/users", {"matricule": "ZZSC-NEW1", "nom": "N", "prenom": "ZZSC-N", "entite_id": EB}, token=RA)
show("creer un salarie hors portee -> 403", s == 403, r)
s, r = j("POST", "/users", {"matricule": "ZZSC-NEW2", "nom": "N", "prenom": "ZZSC-N"}, token=RA)
show("creer un salarie sans entite (compte cloisonne) -> 403", s == 403, r)
s, r = j("POST", "/users", {"matricule": "ZZSC-NEW3", "nom": "N", "prenom": "ZZSC-N", "entite_id": EA1}, token=RA)
show("creer un salarie dans le site -> 201", s == 201, r)
s, r = j("POST", "/users", {"matricule": "ZZSC-NEW4", "nom": "N", "prenom": "ZZSC-N", "entite_id": EA}, token=LA)
show("lecture : ecriture refusee", s == 403)
s, r = j("POST", "/users", {"matricule": "ZZSC-NEW5", "nom": "N", "prenom": "ZZSC-N", "entite_id": EA}, token=R0)
show("RH sans portee : creation refusee", s == 403)
s, r = j("DELETE", "/users/%d" % users["A"]["id"], token=RA)
show("suppression : informatique seulement", s == 403)

print("== Materiel ==")
for who, tok, expect in [("informatique", IT, {"A", "B", "N"}), ("RH A", RA, {"A"}), ("RH B", RB, {"B"}), ("lecture A", LA, {"A"}), ("RH sans portee", R0, set())]:
    s, rows = j("GET", "/assets", token=tok)
    mine = {k for k, a in assets.items() if a["id"] in ids_of(rows)}
    show("liste materiel - " + who, s == 200 and mine == expect, sorted(mine))
s, r = j("GET", "/assets/%d" % assets["B"]["id"], token=RA)
show("materiel d'une autre filiale -> 404", s == 404)
s, r = j("GET", "/assets/%d" % assets["N"]["id"], token=RA)
show("materiel sans entite -> 404", s == 404)

print("== Remises et documents ==")
s, rows = j("GET", "/assignments", token=RA)
show("liste remises RH A : seulement A", s == 200 and asg["A"]["id"] in ids_of(rows) and asg["B"]["id"] not in ids_of(rows))
s, rows = j("GET", "/assignments", token=R0)
show("liste remises RH sans portee : vide", s == 200 and rows == [])
s, rows = j("GET", "/assignments?user_id=%d" % users["B"]["id"], token=RA)
show("remises d'un salarie hors portee : vide", s == 200 and rows == [])
for path in ("", "/recap", "/document"):
    s, r = j("GET", "/assignments/%d%s" % (asg["B"]["id"], path), token=RA)
    show("remise hors portee %s -> 404" % (path or "(detail)"), s == 404, s)
s, r = j("GET", "/assignments/%d" % asg["A"]["id"], token=RA)
show("remise dans la portee lisible", s == 200)
s, r = j("POST", "/assignments", {"user_id": users["A"]["id"], "asset_ids": [assets["N"]["id"]]}, token=RA)
show("creer une remise : informatique seulement", s == 403)

print("== Sorties et restitutions ==")
for path in ("/holdings/%d", "/recap/%d"):
    s, r = j("GET", "/lifecycle" + path % users["B"]["id"], token=RA)
    show("lifecycle %s hors portee -> 404" % path[:-3], s == 404)
    s, r = j("GET", "/lifecycle" + path % users["A"]["id"], token=RA)
    show("lifecycle %s dans la portee" % path[:-3], s == 200)
s, r = j("POST", "/lifecycle/depart/%d" % users["B"]["id"], {"date_sortie": "2026-12-31"}, token=RA)
show("declarer le depart hors portee -> 404", s == 404)
s, r = j("POST", "/lifecycle/restituer", {"user_id": users["B"]["id"], "consent": True}, token=RA)
show("restituer hors portee -> 404", s == 404)
s, r = j("POST", "/lifecycle/depart/%d" % users["A1"]["id"], {"date_sortie": "2026-12-31"}, token=RA)
show("declarer le depart dans la portee", s == 200)

print("== Applications et acces ==")
s, rows = j("GET", "/applications", token=RA)
got = ids_of(rows)
show("applications RH A : A et catalogue commun, pas B", apps["A"]["id"] in got and apps["C"]["id"] in got and apps["B"]["id"] not in got)
s, r = j("GET", "/applications/%d" % apps["B"]["id"], token=RA)
show("application d'une autre filiale -> 404", s == 404)
s, r = j("GET", "/applications/%d" % apps["C"]["id"], token=RA)
show("application commune lisible", s == 200)
s, r = j("POST", "/users/%d/applications" % users["A"]["id"], {"application_id": apps["A"]["id"], "acces": True}, token=RA)
show("attribuer un acces dans la portee", s == 201, r)
ua = r.get("id") if isinstance(r, dict) else None
s, r = j("POST", "/users/%d/applications" % users["A"]["id"], {"application_id": apps["B"]["id"], "acces": True}, token=RA)
show("application hors portee -> 404", s == 404)
s, r = j("POST", "/users/%d/applications" % users["B"]["id"], {"application_id": apps["C"]["id"], "acces": True}, token=RA)
show("acces d'un salarie hors portee -> 404", s == 404)
s, r = j("GET", "/users/%d/applications" % users["B"]["id"], token=RA)
show("lecture des acces d'un salarie hors portee -> 404", s == 404)
s, r = j("POST", "/users/%d/applications" % users["B"]["id"], {"application_id": apps["C"]["id"], "acces": True})
ub = r["id"]
s, r = j("DELETE", "/user-applications/%d" % ub, token=RA)
show("supprimer l'acces d'un salarie hors portee -> 404", s == 404)
s, r = j("DELETE", "/user-applications/%d" % ua, token=RA)
show("supprimer un acces dans la portee", s == 204)

print("== Entites et chartes ==")
s, rows = j("GET", "/entites", token=RA)
show("liste des entites RH A : A et son site", ids_of(rows) == {EA, EA1}, sorted(ids_of(rows)))
s, rows = j("GET", "/entites", token=R0)
show("liste des entites RH sans portee : vide", rows == [])
s, r = j("GET", "/entites/%d" % EB, token=RA)
show("entite hors portee -> 404", s == 404)
s, r = j("POST", "/entites", {"code": "ZZSC-X", "nom": "X"}, token=RA)
show("creer une entite : informatique seulement", s == 403)

pol = {}
for key, eid in [("G", None), ("A", EA), ("B", EB)]:
    fields = {"titre": "ZZSC charte " + key}
    if eid:
        fields["entite_id"] = str(eid)
    s, r = upload("/policies", fields, ADM)
    pol[key] = r
s, rows = j("GET", "/policies", token=RA)
got = ids_of(rows)
show("chartes RH A : globale et A, pas B", pol["G"]["id"] in got and pol["A"]["id"] in got and pol["B"]["id"] not in got)
for suffix in ("/fichier", "/source", "/page/1"):
    s, r = j("GET", "/policies/%d%s" % (pol["B"]["id"], suffix), token=RA)
    show("charte d'une autre filiale %s -> 404" % suffix, s == 404, s)
s, r = j("GET", "/policies/%d/fichier" % pol["G"]["id"], token=RA)
show("charte globale lisible", s == 200)
s, r = j("GET", "/policies/applicable?entite_id=%d" % EB, token=RA)
show("charte applicable d'une entite hors portee : rien", s == 200 and r is None, r)
s, r = j("GET", "/policies/applicable?entite_id=%d" % EA1, token=RA)
show("charte applicable du site : celle de A (heritage)", s == 200 and r and r["id"] == pol["A"]["id"], r)
s, r = j("POST", "/policies/%d/archiver" % pol["A"]["id"], token=RA)
show("archiver une charte : informatique seulement", s == 403)

print("== Rapports et statistiques ==")
s, r = j("GET", "/reports/holdings?format=json", token=RA)
mats = {x["matricule"] for x in r["rows"]}
show("rapport RH A : seulement ses salaries", "ZZSC-A" in mats and "ZZSC-B" not in mats, sorted(mats))
s, r = j("GET", "/reports/holdings?format=json&entite_id=%d" % EB, token=RA)
show("rapport filtre sur une entite hors portee : vide", r["count"] == 0)
s, r = j("GET", "/reports/holdings?format=json", token=R0)
show("rapport RH sans portee : vide", r["count"] == 0)
s, r = j("GET", "/reports/holdings?format=json", token=IT)
mats = {x["matricule"] for x in r["rows"]}
show("rapport informatique : tout", {"ZZSC-A", "ZZSC-B"} <= mats)
for fmt in ("csv", "xlsx", "pdf"):
    s, r = call("GET", "/reports/holdings?format=" + fmt, token=RA)
    show("export %s RH A sans fuite de l'autre filiale" % fmt, s == 200 and (fmt != "csv" or b"ZZSC-B" not in r), s)
s, r = j("GET", "/stats", token=RA)
show("statistiques RH A : materiel de A seulement", s == 200 and r["actifs_total"] == 1, r.get("actifs_total"))
s, r = j("GET", "/stats", token=R0)
show("statistiques RH sans portee : zero", r["actifs_total"] == 0 and r["taux_equipement"]["salaries_actifs"] == 0)
s, r = j("GET", "/stats", token=IT)
show("statistiques informatique : tout", r["actifs_total"] >= 3)

print("== Pages reservees ==")
for path in ("/auth/accounts", "/audit", "/rgpd/retention", "/parametres/types", "/storage/status", "/import/specs", "/auth/sso/admin/etat"):
    for who, tok in (("RH A", RA), ("lecture", LA), ("RH global", RG)):
        s, r = j("GET", path, token=tok)
        show("%s reservee a l'informatique (%s)" % (path, who), s in (403, 404), s)

print("== Changement de portee a chaud ==")
acc_a = next(a for a in j("GET", "/auth/accounts")[1] if a["username"] == "sec_sc_rha")
s, r = j("GET", "/users/%d" % users["B"]["id"], token=RA)
show("avant : salarie B invisible", s == 404)
s, r = j("PUT", "/auth/accounts/%d" % acc_a["id"], {"entites": [EA, EB]})
show("portee etendue a A et B", s == 200 and r["entites"] == [EA, EB], r)
s, r = j("GET", "/users/%d" % users["B"]["id"], token=RA)
show("apres : effet immediat", s == 200)
s, r = j("PUT", "/auth/accounts/%d" % acc_a["id"], {"portee_globale": True})
RA = login("sec_sc_rhA", PW)
s, r = j("GET", "/users/%d" % users["N"]["id"], token=RA)
show("passage en global : salarie sans entite visible", s == 200)
j("PUT", "/auth/accounts/%d" % acc_a["id"], {"portee_globale": False, "entites": [EA]})
s, r = j("PUT", "/auth/accounts/%d" % acc_a["id"], {"role": "informatique"})
show("promotion informatique : devient global", s == 200 and r["portee_globale"] is True and r["entites"] == [], r)
s, r = j("PUT", "/auth/accounts/%d" % acc_a["id"], {"role": "rh"})
show("retrogradation RH : repart sans portee", s == 200 and r["portee_globale"] is False and r["entites"] == [], r)
RA = login("sec_sc_rhA", PW)
s, rows = j("GET", "/users", token=RA)
show("apres retrogradation : ne voit rien", s == 200 and not (ids_of(rows) & {u["id"] for u in users.values()}))

print("== Inventaire des routes ==")
sys.path.insert(0, "/app")
from app.main import app  # noqa: E402

DATA = ("/users", "/assets", "/assignments", "/lifecycle", "/user-applications", "/applications", "/entites", "/policies",
        "/reports", "/stats", "/besoins")
unscoped = []
for route in app.routes:
    path = getattr(route, "path", "")
    if not hasattr(route, "dependant") or "GET" not in (getattr(route, "methods", None) or ()):
        continue
    if not path.startswith(DATA) or "/catalogue" in path:
        continue
    names, stack = [], list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        names.append(getattr(d.call, "__name__", ""))
        stack.extend(d.dependencies)
    if "scope_dep" not in names:
        unscoped.append(path)
show("toute route de lecture de donnees passe par le filtre de portee", not unscoped, unscoped[:6])

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
