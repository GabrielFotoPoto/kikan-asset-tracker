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

"""Tests du lot G5 (#179) : connecteur Active Directory local (LDAP / LDAPS) contre annuaire simule."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import uvicorn
from ldap3 import MOCK_SYNC, Connection, Server

from app import ldap_auth
from app.main import app

ADMIN_USER = os.environ["TEST_ADMIN_USER"]
ADMIN_PASS = os.environ["TEST_ADMIN_PASSWORD"]

TEST_PORT = 18765
BASE = f"http://127.0.0.1:{TEST_PORT}"
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


def login(u, p):
    return j("POST", "/auth/login", {"username": u, "password": p})


_srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error"))
_thr = threading.Thread(target=_srv.run, daemon=True)
_thr.start()
for _ in range(50):
    try:
        urllib.request.urlopen(BASE + "/health", timeout=1)
        break
    except Exception:
        time.sleep(0.1)


# --- Configuration d'un faux annuaire AD ldap3 (MOCK_SYNC) en memoire ---
BASE_DN = "DC=exemple,DC=test"
SVC_DN = "CN=svc-kikan,DC=exemple,DC=test"
SVC_PW = "SvcBindPassword2026!"
GRP_ALLOWED = "CN=Kikan-Demandeurs,OU=Groupes,DC=exemple,DC=test"
GRP_ADMIN = "CN=Domain Admins,CN=Users,DC=exemple,DC=test"

mock_server = Server("ad.exemple.test", port=636, use_ssl=True)
seed_conn = Connection(mock_server, user=SVC_DN, password=SVC_PW, client_strategy=MOCK_SYNC)
seed_conn.strategy.add_entry(BASE_DN, {"objectClass": ["domain"], "dc": "exemple"})
seed_conn.strategy.add_entry(SVC_DN, {"objectClass": ["user"], "userPassword": SVC_PW})
seed_conn.strategy.add_entry("CN=Alice AD,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordAlice2026!",
    "objectGUID": b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10",
    "mail": "zzg5.alice@exemple.test",
    "userPrincipalName": "zzg5.alice@exemple.test",
    "sAMAccountName": "zzg5.alice",
    "displayName": "ZZ Alice AD",
    "memberOf": [GRP_ALLOWED, GRP_ADMIN],  # meme dans Domain Admins -> role demandeur UNIQUEMENT !
})
seed_conn.strategy.add_entry("CN=Bob HorsGroupe,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordBob2026!",
    "objectGUID": b"\x21\x22\x23\x24\x25\x26\x27\x28\x29\x2a\x2b\x2c\x2d\x2e\x2f\x30",
    "mail": "zzg5.bob@exemple.test",
    "sAMAccountName": "zzg5.bob",
    "displayName": "ZZ Bob",
    "memberOf": [],
})
seed_conn.strategy.add_entry("CN=Inconnu Kikan,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordInc2026!",
    "objectGUID": b"\x41\x42\x43\x44\x45\x46\x47\x48\x49\x4a\x4b\x4c\x4d\x4e\x4f\x50",
    "mail": "zzg5.inconnu@exemple.test",
    "memberOf": [GRP_ALLOWED],
})
seed_conn.strategy.add_entry("CN=Local Vers LDAP,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordLocal2026!",
    "objectGUID": b"\x61\x62\x63\x64\x65\x66\x67\x68\x69\x6a\x6b\x6c\x6d\x6e\x6f\x70",
    "mail": "zzg5.autre.mail@exemple.test",
    "sAMAccountName": "ZZG5-03",
    "displayName": "ZZ Local Converti",
    "memberOf": [GRP_ALLOWED],
})
seed_conn.strategy.add_entry("CN=Doublon Mail,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordDup2026!",
    "objectGUID": b"\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f\x90",
    "mail": "zzg5.dup@exemple.test",
    "sAMAccountName": "zzg5.dup",
    "memberOf": [GRP_ALLOWED],
})
seed_conn.strategy.add_entry("CN=Local Convert,DC=exemple,DC=test", {
    "objectClass": ["user"],
    "userPassword": "AdPasswordConv2026!",
    "objectGUID": b"\x61\x62\x63\x64\x65\x66\x67\x68\x69\x6a\x6b\x6c\x6d\x6e\x6f\x70",
    "mail": "zzg5.local@exemple.test",
    "memberOf": [GRP_ALLOWED],
})

ldap_calls = {"count": 0}


def fake_factory(host, port, use_ssl, tls_obj, timeout):
    ldap_calls["count"] += 1
    return mock_server, MOCK_SYNC


os.environ["KIKAN_LDAP_HOSTS"] = "127.0.0.1"
os.environ["KIKAN_LDAP_PORT"] = "636"
os.environ["KIKAN_LDAP_TLS"] = "ldaps"
os.environ["KIKAN_LDAP_BASE_DN"] = BASE_DN
os.environ["KIKAN_LDAP_BIND_DN"] = SVC_DN
os.environ["KIKAN_LDAP_BIND_PASSWORD"] = SVC_PW
ldap_auth._TEST_CLIENT_FACTORY = fake_factory

try:
    s_it, r_it = login(ADMIN_USER, ADMIN_PASS)
    assert s_it == 200, (s_it, r_it)
    tok_it = r_it["access_token"]

    print("== 1. Administration /admin/ldap et secret jamais expose ==")
    _, ent = j("POST", "/entites", {"code": "ZZG5", "nom": "ZZ G5 Entite"}, tok_it)
    _, _ = j("POST", "/auth/accounts", {
        "username": "zzg5_rh", "password": "G5Password2026!", "role": "rh", "entites": [ent["id"]],
    }, tok_it)
    _, r_rh = login("zzg5_rh", "G5Password2026!")
    tok_rh = r_rh["access_token"]

    show("GET /admin/ldap sans auth -> 401", j("GET", "/admin/ldap")[0] == 401)
    show("GET /admin/ldap role RH -> 403", j("GET", "/admin/ldap", token=tok_rh)[0] == 403)
    s_st, st = j("GET", "/admin/ldap", token=tok_it)
    show("GET /admin/ldap IT -> 200 sans jamais exposer bind_password",
         s_st == 200 and st["config"]["configure"] is True
         and st["config"]["bind_password_present"] is True
         and SVC_PW not in json.dumps(st), st)

    s_tst, r_tst = j("POST", "/admin/ldap/test", {}, tok_it)
    show("POST /admin/ldap/test -> 200 ok", s_tst == 200 and r_tst.get("ok") is True, r_tst)

    show("attribut invalide refuse (422)",
         j("PUT", "/admin/ldap", {"actif": True, "attribut": "cn"}, tok_it)[0] == 422)
    s_act, st_act = j("PUT", "/admin/ldap", {
        "actif": True, "attribut": "mail", "groupe_dn": GRP_ALLOWED,
    }, tok_it)
    show("activation LDAP + groupe autorise", s_act == 200 and st_act["actif"] is True, st_act)

    print("== 2. Donnees salaries et tests d'authentification AD/LDAP ==")
    _, u_alice = j("POST", "/users", {
        "matricule": "ZZG5-01", "nom": "ZZG5_ALICE", "prenom": "ZZ_Alice",
        "email": "zzg5.alice@exemple.test", "entite_id": ent["id"],
    }, tok_it)
    _, u_bob = j("POST", "/users", {
        "matricule": "ZZG5-02", "nom": "ZZG5_BOB", "prenom": "ZZ_Bob",
        "email": "zzg5.bob@exemple.test", "entite_id": ent["id"],
    }, tok_it)
    _, u_local = j("POST", "/users", {
        "matricule": "ZZG5-03", "nom": "ZZG5_LOCAL", "prenom": "ZZ_Local",
        "email": "zzg5.local@exemple.test", "entite_id": ent["id"],
    }, tok_it)

    # Mot de passe vide refuse (anti-bind anonyme)
    calls_before = ldap_calls["count"]
    s_empty, _ = login("zzg5.alice@exemple.test", "")
    show("mot de passe vide refuse (401) sans aucun appel LDAP",
         s_empty == 401 and ldap_calls["count"] == calls_before, (s_empty, ldap_calls["count"] - calls_before))

    # Tentative d'injection LDAP RFC 4515 : prouver que sans echappement le filtre matche Alice,
    # alors qu'avec l'echappement de ldap_auth.authenticate() il est neutralise (401).
    inj_payload = "zzg5.alice@exemple.test)(objectClass=*"
    seed_conn.bind()
    seed_conn.search(BASE_DN, f"(&(objectClass=user)(mail={inj_payload}))", attributes=["mail"])
    raw_matched = len(list(seed_conn.entries or [])) == 1
    s_inj, _ = login(inj_payload, "AdPasswordAlice2026!")
    show("injection LDAP : filtre brut matche mais authenticate() echappe et neutralise (401)",
         raw_matched and s_inj == 401, (raw_matched, s_inj))

    # Utilisateur hors groupe AD autorise refuse
    s_grp, _ = login("zzg5.bob@exemple.test", "AdPasswordBob2026!")
    show("utilisateur hors groupe AD autorise refuse (401)", s_grp == 401, s_grp)

    # Utilisateur valide dans AD mais sans fiche salarie Kikan -> 401 uniforme (ne confirme jamais le MDP AD)
    s_inc, d_inc = login("zzg5.inconnu@exemple.test", "AdPasswordInc2026!")
    show("utilisateur AD sans fiche salarie -> 401 uniforme", s_inc == 401 and "provisionne" not in str(d_inc).lower(), (s_inc, d_inc))

    # Plusieurs fiches salarie avec le meme e-mail -> refus 401 uniforme
    j("POST", "/users", {"matricule": "ZZG5-D1", "nom": "ZZG5_D1", "prenom": "ZZ_D1", "email": "zzg5.dup@exemple.test", "entite_id": ent["id"]}, tok_it)
    j("POST", "/users", {"matricule": "ZZG5-D2", "nom": "ZZG5_D2", "prenom": "ZZ_D2", "email": "zzg5.dup@exemple.test", "entite_id": ent["id"]}, tok_it)
    s_dup, _ = login("zzg5.dup@exemple.test", "AdPasswordDup2026!")
    show("plusieurs fiches salarie meme e-mail -> refus 401 uniforme", s_dup == 401, s_dup)

    # Connexion nominale Alice (membre Domain Admins -> role demandeur UNIQUEMENT)
    s_ok, r_ok = login("zzg5.alice@exemple.test", "AdPasswordAlice2026!")
    show("connexion LDAP reussie -> role strictement demandeur (jamais IT)",
         s_ok == 200 and r_ok["role"] == "demandeur", r_ok)
    tok_alice = r_ok["access_token"]
    show("session LDAP demandeur : /mon-espace/materiel (200) et /users (403)",
         j("GET", "/mon-espace/materiel", token=tok_alice)[0] == 200
         and j("GET", "/users", token=tok_alice)[0] == 403)

    # Liaison stable par external_uid apres changement d'e-mail sur User
    j("PUT", f"/users/{u_alice['id']}", {"email": "zzg5.alice.renomme@exemple.test"}, tok_it)
    s_ok2, _ = login("zzg5.alice@exemple.test", "AdPasswordAlice2026!")
    show("liaison stable par external_uid apres changement d'e-mail", s_ok2 == 200, s_ok2)

    # Aiguillage strict : mot de passe d'un compte local JAMAIS envoye a l'annuaire AD
    calls_before_local = ldap_calls["count"]
    s_loc_ok, _ = login("zzg5_rh", "G5Password2026!")
    s_loc_bad, _ = login("zzg5_rh", "MauvaisMotDePasse!")
    show("compte local : mot de passe jamais envoye a l'annuaire AD",
         s_loc_ok == 200 and s_loc_bad == 401 and ldap_calls["count"] == calls_before_local,
         (s_loc_ok, s_loc_bad, ldap_calls["count"] - calls_before_local))

    # Conversion sans doublon d'un compte local demandeur existant -> LDAP via attribut configure (sAMAccountName -> matricule)
    s_p, acc_loc = j("POST", f"/users/{u_local['id']}/compte-demandeur", {"mode": "mot_de_passe"}, tok_it)
    assert s_p == 201, acc_loc
    calls_before_dem_loc = ldap_calls["count"]
    s_dl, _ = login(acc_loc["username"], acc_loc["mot_de_passe_provisoire"])
    show("compte demandeur local reste verifie localement (pas d'envoi AD)",
         s_dl == 200 and ldap_calls["count"] == calls_before_dem_loc, (s_dl, ldap_calls["count"] - calls_before_dem_loc))
    # Bascule attribut sur sAMAccountName : liaison par matricule (ZZG5-03) convertit le compte local sans doublon
    j("PUT", "/admin/ldap", {"actif": True, "attribut": "sAMAccountName", "groupe_dn": GRP_ALLOWED}, tok_it)
    s_conv, r_conv = login("ZZG5-03", "AdPasswordLocal2026!")
    _, accs_after = j("GET", "/auth/accounts", token=tok_it)
    loc_accs = [a for a in accs_after if a["user_id"] == u_local["id"]]
    show("premiere liaison par attribut configure (sAMAccountName -> matricule) convertit le compte local sans doublon",
         s_conv == 200 and len(loc_accs) == 1 and loc_accs[0]["source_auth"] == "ldap" and loc_accs[0]["id"] == acc_loc["account_id"],
         (s_conv, loc_accs))
    j("PUT", "/admin/ldap", {"actif": True, "attribut": "mail", "groupe_dn": GRP_ALLOWED}, tok_it)

    # AuditLog : pseudonyme dem-<id> et zero e-mail salarie LDAP
    _, accounts = j("GET", "/auth/accounts", token=tok_it)
    a_alice = next(a for a in accounts if a["user_id"] == u_alice["id"])
    # Garde-fous compte LDAP : pas de reset-password, pas de mot de passe local, pas de secours, pas de lier-sso
    show("compte LDAP : reset-password refuse (409)",
         j("POST", f"/auth/accounts/{a_alice['id']}/reset-password", {}, tok_it)[0] == 409)
    show("compte LDAP : secours=True et password local refuses (409)",
         j("PUT", f"/auth/accounts/{a_alice['id']}", {"secours": True}, tok_it)[0] == 409
         and j("PUT", f"/auth/accounts/{a_alice['id']}", {"password": "LocalPassword2026!"}, tok_it)[0] == 409)
    show("compte LDAP : lier-sso refuse (409)",
         j("POST", f"/auth/accounts/{a_alice['id']}/lier-sso", {"upn": "zzg5.alice@exemple.test"}, tok_it)[0] == 409)

    # Compte LDAP desactive -> connexion refusee (401 uniforme)
    j("PUT", f"/auth/accounts/{a_alice['id']}", {"actif": False}, tok_it)
    s_inact, _ = login("zzg5.alice@exemple.test", "AdPasswordAlice2026!")
    show("compte LDAP desactive -> connexion refusee (401)", s_inact == 401, s_inact)
    j("PUT", f"/auth/accounts/{a_alice['id']}", {"actif": True}, tok_it)

    # Hote AD refuse par netguard : login anonyme renvoie 401 sans jamais exposer le nom d'hote
    prev_hosts = os.environ.get("KIKAN_LDAP_HOSTS", "")
    os.environ["KIKAN_LDAP_HOSTS"] = "127.0.0.1"
    s_ng, d_ng = login("zzg5.inconnu2@exemple.test", "AdPasswordInc2026!")
    os.environ["KIKAN_LDAP_HOSTS"] = prev_hosts
    show("hote AD refuse par netguard : 401 anonyme sans exposer l'hote",
         s_ng == 401 and "127.0.0.1" not in str(d_ng), (s_ng, d_ng))

    # Salarie passe sorti -> connexion LDAP refusee (401 uniforme)
    from sqlmodel import Session
    from app.db import engine
    from app.models import EmployeeStatus, User
    with Session(engine) as db:
        db_u = db.get(User, u_alice["id"])
        db_u.statut = EmployeeStatus.sorti
        db.add(db_u)
        db.commit()
    s_l_sort, _ = login("zzg5.alice@exemple.test", "AdPasswordAlice2026!")
    show("salarie sorti -> connexion LDAP refusee (401)", s_l_sort == 401, s_l_sort)

    _, aud = j("GET", "/audit?limit=300", token=tok_it)
    aud_blob = json.dumps(aud)
    show("AuditLog G5 : pseudonyme dem-<id> present et zero e-mail salarie",
         f"dem-{a_alice['id']}" in aud_blob
         and "zzg5.alice@exemple.test" not in aud_blob
         and "zzg5.inconnu@exemple.test" not in aud_blob)
finally:
    ldap_auth._TEST_CLIENT_FACTORY = None
    _srv.should_exit = True

print(f"\nResultat : {ok_count} OK, {fail_count} FAIL")
sys.exit(1 if fail_count else 0)
