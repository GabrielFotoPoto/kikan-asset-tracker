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

"""Connecteur GLPI (B5) : reglages, import propose puis applique, export des utilisateurs et du materiel avec numeros de serie.

Deux modes, memes tests :
  - FAKE (par defaut) : un faux GLPI integre a ce script (127.0.0.1:2580) imite l'API REST historique ;
        docker compose -f docker-compose.yml -f tests/glpi-test.override.yml up -d api
        docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/glpi_check.py
  - LIVE : un vrai GLPI de test (tests/glpi-test.yml) ; GLPI_TEST_TOKEN = jeton utilisateur de ce GLPI (donne aussi a l'API)
        GLPI_TEST_TOKEN=... docker compose -f docker-compose.yml -f tests/glpi-test.override.yml up -d api
        docker exec -i -e GLPI_LIVE=1 -e GLPI_TEST_TOKEN=... -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/glpi_check.py

Cree des donnees ZZGL (Kikan et GLPI) ; nettoyage Kikan : tests/cleanup_test_data.sql ; le script purge ses elements ZZ dans GLPI.
Code de sortie 1 si un test echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/app")

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
LIVE = os.environ.get("GLPI_LIVE") == "1"
TOKEN = os.environ.get("GLPI_TEST_TOKEN", "ZZFAKEGLPITOKEN0000000000000000000000000")
GLPI_URL = "http://glpi" if LIVE else "http://127.0.0.1:2580"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


# ====================================================================== cote GLPI : faux serveur ou vrai serveur
class Store:
    """Etat du faux GLPI."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.tables = {"Entity": [{"id": 0, "name": "Root entity", "completename": "Root entity"}, {"id": 1, "name": "ZZ Filiale", "completename": "Root entity > ZZ Filiale"}],
                       "Profile": [{"id": 1, "name": "Self-Service"}, {"id": 4, "name": "Super-Admin"}], "Manufacturer": [], "State": [{"id": 1, "name": "En service"}],
                       "ComputerModel": [], "PhoneModel": [], "User": [], "UserEmail": [], "Computer": [], "Phone": []}
        self.profile_users = []
        self.seq = {k: 100 for k in self.tables}
        self.reject_auth = False
        self.fail_serials = set()
        self.calls = []

    def add(self, table, row):
        self.seq[table] += 1
        row = {"id": self.seq[table], **row}
        self.tables[table].append(row)
        return row


STORE = Store()


class FakeGlpi(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        if not path.startswith("/apirest.php/"):
            return self._send(404, ["ERROR_NOT_FOUND", "no"])
        path = path[len("/apirest.php/"):]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        STORE.calls.append((method, path))
        if path == "initSession":
            if STORE.reject_auth or self.headers.get("Authorization") != "user_token " + TOKEN:
                return self._send(401, ["ERROR_GLPI_LOGIN_USER_TOKEN", "parameter user_token seems invalid"])
            return self._send(200, {"session_token": "FAKESESSION"})
        if self.headers.get("Session-Token") != "FAKESESSION":
            return self._send(401, ["ERROR_SESSION_TOKEN_INVALID", "session_token seems invalid"])
        if path == "killSession":
            return self._send(200, [])
        parts = path.split("/")
        table = parts[0]
        if table not in STORE.tables:
            return self._send(400, ["ERROR_ITEMTYPE_NOT_FOUND_NOR_COMMONDBTM", "itemtype not found"])
        if method == "GET" and len(parts) == 1:
            rows = STORE.tables[table]
            q = urllib.parse.parse_qs(url.query)
            a, b = (int(x) for x in q.get("range", ["0-49"])[0].split("-"))
            if not rows:
                return self._send(200, [])
            if a >= len(rows):
                return self._send(400, ["ERROR_RANGE_EXCEED_TOTAL", "Provided range exceed total count of data: %d" % len(rows)])
            return self._send(206 if len(rows) > b + 1 else 200, rows[a:b + 1])
        if method == "POST":
            values = (body or {}).get("input", {})
            if table == "User":
                if any(u["name"] == values.get("name") for u in STORE.tables["User"]):
                    return self._send(400, ["ERROR_GLPI_ADD", "Unable to add. The user already exists."])
                row = STORE.add("User", {"name": values.get("name"), "realname": values.get("realname"), "firstname": values.get("firstname"),
                                         "registration_number": values.get("registration_number"), "is_active": values.get("is_active", 1),
                                         "is_deleted": 0, "entities_id": values.get("entities_id", 0)})
                for mail in values.get("_useremails", []):
                    STORE.add("UserEmail", {"users_id": row["id"], "is_default": 1, "email": mail})
                if values.get("_profiles_id"):
                    STORE.profile_users.append({"users_id": row["id"], "profiles_id": values["_profiles_id"], "entities_id": values.get("_entities_id")})
                return self._send(201, {"id": row["id"], "message": "ok"})
            if table in ("Computer", "Phone"):
                if values.get("serial") in STORE.fail_serials:
                    return self._send(400, ["ERROR_GLPI_ADD", "Unable to add."])
                row = STORE.add(table, {"name": values.get("name"), "serial": values.get("serial"), "otherserial": values.get("otherserial"),
                                        "users_id": values.get("users_id", 0), "entities_id": values.get("entities_id", 0),
                                        "manufacturers_id": values.get("manufacturers_id", 0), "computermodels_id": values.get("computermodels_id", 0),
                                        "phonemodels_id": values.get("phonemodels_id", 0), "states_id": 0, "is_deleted": 0, "is_template": 0,
                                        "comment": values.get("comment")})
                return self._send(201, {"id": row["id"], "message": "ok"})
            row = STORE.add(table, {"name": values.get("name")})
            return self._send(201, {"id": row["id"], "message": "ok"})
        if method == "PUT" and len(parts) == 2:
            values = (body or {}).get("input", {})
            for row in STORE.tables[table]:
                if row["id"] == int(parts[1]):
                    row.update({k: v for k, v in values.items() if k != "id"})
                    return self._send(200, [{parts[1]: True, "message": ""}])
            return self._send(404, ["ERROR_ITEM_NOT_FOUND", "not found"])
        return self._send(400, ["ERROR_METHOD_NOT_ALLOWED", "no"])

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")


class FakeSide:
    """Pilote le faux GLPI directement (donnees d'essai)."""

    def user(self, name, realname, firstname, email=None, matricule=None, active=1):
        row = STORE.add("User", {"name": name, "realname": realname, "firstname": firstname, "registration_number": matricule,
                                 "is_active": active, "is_deleted": 0, "entities_id": 0})
        if email:
            STORE.add("UserEmail", {"users_id": row["id"], "is_default": 1, "email": email})
        return row["id"]

    def item(self, itemtype, name, serial, users_id=0, manufacturer=None, model=None, **extra):
        mid = 0
        if manufacturer:
            mid = STORE.add("Manufacturer", {"name": manufacturer})["id"]
        modid = 0
        if model:
            modid = STORE.add("ComputerModel" if itemtype == "Computer" else "PhoneModel", {"name": model})["id"]
        row = {"name": name, "serial": serial, "otherserial": None, "users_id": users_id, "entities_id": 0, "manufacturers_id": mid,
               "computermodels_id": modid if itemtype == "Computer" else 0, "phonemodels_id": modid if itemtype == "Phone" else 0,
               "states_id": 0, "is_deleted": 0, "is_template": 0, **extra}
        return STORE.add(itemtype, row)["id"]

    def items(self, itemtype):
        return [r for r in STORE.tables[itemtype] if not r.get("is_deleted") and not r.get("is_template")]

    def users(self):
        return [r for r in STORE.tables["User"]]

    def email_of(self, uid):
        return next((e["email"] for e in STORE.tables["UserEmail"] if e["users_id"] == uid), None)

    def profile_of(self, uid):
        return next((p["profiles_id"] for p in STORE.profile_users if p["users_id"] == uid), None)

    def profile_id(self, name):
        return next(p["id"] for p in STORE.tables["Profile"] if p["name"] == name)

    def clean(self):
        STORE.reset()

    def fail_serial(self, serial):
        STORE.fail_serials.add(serial)

    def reject_auth(self, flag):
        STORE.reject_auth = flag


class LiveSide:
    """Pilote un vrai GLPI de test par son API REST (donnees d'essai ZZ purgees avant et apres)."""

    def __init__(self):
        self.base = GLPI_URL + "/apirest.php"
        s, b = self._call("GET", "/initSession", headers={"Authorization": "user_token " + TOKEN})
        self.session = b["session_token"]

    def _call(self, method, path, body=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if getattr(self, "session", None):
            h["Session-Token"] = self.session
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
        try:
            r = urllib.request.urlopen(req, timeout=60)
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def _all(self, itemtype):
        s, rows = self._call("GET", "/%s?range=0-999" % itemtype)
        return rows if s in (200, 206) else []

    def user(self, name, realname, firstname, email=None, matricule=None, active=1):
        values = {"name": name, "realname": realname, "firstname": firstname, "is_active": active}
        if email:
            values["_useremails"] = [email]
        if matricule:
            values["registration_number"] = matricule
        s, b = self._call("POST", "/User", {"input": values})
        return b["id"]

    def _dropdown(self, itemtype, name):
        for r in self._all(itemtype):
            if r["name"] == name:
                return r["id"]
        return self._call("POST", "/" + itemtype, {"input": {"name": name}})[1]["id"]

    def item(self, itemtype, name, serial, users_id=0, manufacturer=None, model=None, **extra):
        values = {"name": name, "users_id": users_id, **extra}
        if serial:
            values["serial"] = serial
        if manufacturer:
            values["manufacturers_id"] = self._dropdown("Manufacturer", manufacturer)
        if model:
            values["computermodels_id" if itemtype == "Computer" else "phonemodels_id"] = self._dropdown("ComputerModel" if itemtype == "Computer" else "PhoneModel", model)
        s, b = self._call("POST", "/" + itemtype, {"input": values})
        return b["id"]

    def items(self, itemtype):
        return [r for r in self._all(itemtype) if not r.get("is_deleted") and not r.get("is_template")]

    def users(self):
        return self._all("User")

    def email_of(self, uid):
        return next((e["email"] for e in self._all("UserEmail") if e["users_id"] == uid), None)

    def profile_of(self, uid):
        s, rows = self._call("GET", "/User/%d/Profile_User" % uid)
        return rows[0]["profiles_id"] if s == 200 and rows else None

    def profile_id(self, name):
        return next(p["id"] for p in self._all("Profile") if p["name"] == name)

    def clean(self):
        for itemtype in ("Computer", "Phone"):
            for r in self._all(itemtype):
                if str(r.get("name") or "").startswith("ZZ") or str(r.get("serial") or "").startswith("ZZGL"):
                    self._call("DELETE", "/%s/%d?force_purge=true" % (itemtype, r["id"]))
        for r in self._all("User"):
            if str(r.get("name") or "").startswith(("zz", "alice.zz", "bob.zz")) or str(r.get("registration_number") or "").startswith("ZZ-GL"):
                self._call("DELETE", "/User/%d?force_purge=true" % r["id"])

    def fail_serial(self, serial):
        pass

    def reject_auth(self, flag):
        pass


if not LIVE:
    srv = ThreadingHTTPServer(("127.0.0.1", 2580), FakeGlpi)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
G = LiveSide() if LIVE else FakeSide()
G.clean()


# ====================================================================== cote Kikan
def call(method, path, payload=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=180)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(user, pw):
    s, b = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


ADM = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, payload=None, token=None):
    s, b = call(method, path, payload, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


print("== Preparation (%s) ==" % ("vrai GLPI" if LIVE else "faux GLPI"))
ent = {}
for code in ("ZZGL-A", "ZZGL-B"):
    s, r = j("POST", "/entites", {"code": code, "nom": code})
    if s == 409:
        r = next(e for e in j("GET", "/entites")[1] if e["code"] == code)
    ent[code] = r["id"]
EA, EB = ent["ZZGL-A"], ent["ZZGL-B"]
for t in ("ZZGL portable", "ZZGL smartphone", "ZZGL ecran"):
    j("POST", "/parametres/types", {"nom": t})
for name, role in (("sec_gl_rh", "rh"), ("sec_gl_lec", "lecture")):
    j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True})
RH, LEC = login("sec_gl_rh", PW), login("sec_gl_lec", PW)
show("comptes de test", bool(RH and LEC))

CONF = {"actif": True, "url": GLPI_URL, "verifier_cert": True, "types_computer": ["ZZGL portable"], "types_phone": ["ZZGL smartphone"],
        "entites": {}, "entite_kikan": EA, "entite_glpi": 0, "profil": "Self-Service"}

print("== Reglages ==")
s, r = j("GET", "/glpi/config")
show("par defaut : connecteur desactive, jeton non expose", s == 200 and r["config"]["actif"] is False and "token" not in json.dumps(r).lower().replace("jeton_", ""), r)
show("l'API connait le jeton GLPI (variable d'environnement)", r["jeton_defini"] is True, r)
for name, payload, codes in [
    ("adresse sans schema", {**CONF, "url": "glpi.local"}, (400,)),
    ("schema ftp", {**CONF, "url": "ftp://glpi.local"}, (400,)),
    ("identifiants dans l'adresse", {**CONF, "url": "http://user:pass@glpi.local"}, (400,)),
    ("adresse link-local (metadonnees cloud)", {**CONF, "url": "http://169.254.169.254"}, (400,)),
    ("activation sans adresse", {**CONF, "url": ""}, (400,)),
    ("type a la fois ordinateur et telephone", {**CONF, "types_phone": ["ZZGL portable"]}, (400,)),
    ("nom de type avec separateur", {**CONF, "types_computer": ["a|b"]}, (400,)),
    ("entite Kikan inconnue", {**CONF, "entite_kikan": 999999}, (400,)),
    ("correspondance d'entite inconnue", {**CONF, "entites": {"0": 999999}}, (400,)),
]:
    s, r = j("PUT", "/glpi/config", payload)
    show("refuse : " + name, s in codes, s)
for who, tok in (("RH", RH), ("lecture", LEC), ("sans jeton", None)):
    for method, path in (("GET", "/glpi/config"), ("PUT", "/glpi/config"), ("POST", "/glpi/tester"), ("POST", "/glpi/import/apercu"),
                         ("POST", "/glpi/import/appliquer"), ("POST", "/glpi/export/apercu"), ("POST", "/glpi/export/appliquer"), ("GET", "/glpi/historique")):
        if tok is None:
            s, _ = call(method, path, {} if method in ("POST", "PUT") else None)
        else:
            s, _ = j(method, path, {} if method in ("POST", "PUT") else None, token=tok)
        show("%s %s refuse (%s)" % (method, path, who), s in ((401, 403) if tok is None else (403,)), s)
s, r = j("POST", "/glpi/import/apercu")
show("connecteur desactive : import refuse", s == 409, r)
s, r = j("PUT", "/glpi/config", CONF)
show("configuration enregistree", s == 200 and r["config"]["actif"] and r["config"]["types_computer"] == ["ZZGL portable"], r)

print("== Test de connexion ==")
s, r = j("POST", "/glpi/tester")
show("connexion et lecture reussies", s == 200 and r["ok"] and "entites" in r and r["profil_trouve"] is True, r)
s, r2 = j("PUT", "/glpi/config", {**CONF, "url": GLPI_URL.replace("2580", "2599").replace("http://glpi", "http://glpi-inexistant")})
s, r = j("POST", "/glpi/tester")
show("serveur injoignable : 502 lisible, sans jeton", s == 502 and "injoignable" in json.dumps(r).lower() and TOKEN not in json.dumps(r), r)
j("PUT", "/glpi/config", CONF)
if not LIVE:
    G.reject_auth(True)
    s, r = j("POST", "/glpi/tester")
    show("jeton refuse par GLPI : message clair, sans jeton", s == 502 and "invalide" in json.dumps(r).lower() and "KIKAN_GLPI_USER_TOKEN" in json.dumps(r) and TOKEN not in json.dumps(r), r)
    G.reject_auth(False)

print("== Import depuis GLPI ==")
alice = G.user("alice.zz", "MartinZZ", "ZZAlice", "alice.zz@exemple.test", "ZZ-GL-1")
bob = G.user("bob.zz", "DurandZZ", "ZZBob", "bob.zz@exemple.test")
chloe = G.user("zz.chloe", "PetitZZ", "ZZChloe", "chloe.zz@exemple.test")
G.user("zz.inactif", "InactifZZ", "ZZIna", "ina.zz@exemple.test", active=0)
G.user("zz.sam", "SamGLZZ", "ZZSam", "sam.zz@exemple.test")
pc1 = G.item("Computer", "ZZ-PC-1", "ZZGLSN1", alice, "ZZDell", "ZZLatitude 5540")
pc2 = G.item("Computer", "ZZ-PC-2", "ZZGLSN2", 0, "ZZLenovo", "ZZThinkPad T14")
pc3 = G.item("Computer", "ZZ-PC-SANS-SERIE", None, 0)
ph1 = G.item("Phone", "ZZ-TEL-1", "ZZGLSNP1", bob, "ZZSamsung", "ZZGalaxy A55")
if not LIVE:
    G.item("Computer", "ZZ-PC-SUPPRIME", "ZZGLSNDEL", 0, is_deleted=1)
    G.item("Computer", "ZZ-GABARIT", "ZZGLSNTPL", 0, is_template=1)
s, existing = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZManuel", "modele": "M1", "numero_serie": "zzglsn2", "identifiant_interne": "ZZGL-ID-2", "entite_id": EB})
s, kuser = j("POST", "/users", {"matricule": "ZZ-GL-1", "nom": "Martin", "prenom": "ZZGLalice", "entite_id": EB})
s, homonyme = j("POST", "/users", {"matricule": "ZZ-GL-H", "nom": "PetitZZ", "prenom": "ZZChloe", "entite_id": EB})

s, prop = j("POST", "/glpi/import/apercu")
show("apercu de l'import", s == 200 and "actifs" in prop and "salaries" in prop, prop if s != 200 else "")
by = {a["externe_id"]: a for a in prop["actifs"]}
show("les ordinateurs et telephones sont proposes (les supprimes et gabarits non)", {"Computer:%d" % pc1, "Computer:%d" % pc2, "Phone:%d" % ph1} <= set(by)
     and not any(a["nom"] in ("ZZ-PC-SUPPRIME", "ZZ-GABARIT") for a in prop["actifs"]), sorted(by))
a1 = by["Computer:%d" % pc1]
show("numero de serie, fabricant, modele et utilisateur lus", a1["serial"] == "ZZGLSN1" and a1["fabricant"] == "ZZDell" and a1["modele"] == "ZZLatitude 5540" and a1["utilisateur"] == "alice.zz", a1)
show("etat : nouveau", a1["etat_import"] == "nouveau" and a1["type_kikan"] == "ZZGL portable" and a1["importable"], a1)
show("meme numero de serie qu'un materiel Kikan (casse differente) : correspondance", by["Computer:%d" % pc2]["etat_import"] == "correspondance"
     and by["Computer:%d" % pc2]["kikan_id"] == existing["id"], by["Computer:%d" % pc2])
show("sans numero de serie : signale", by["Computer:%d" % pc3]["etat_import"] == "sans_serie", by["Computer:%d" % pc3])
show("le telephone prend le type telephone", by["Phone:%d" % ph1]["type_kikan"] == "ZZGL smartphone")
us = {u["externe_id"]: u for u in prop["salaries"]}
show("les utilisateurs inactifs ne sont pas proposes", not any(u["login"] == "zz.inactif" for u in prop["salaries"]))
show("meme matricule : correspondance avec la fiche Kikan", us["User:%d" % alice]["etat_import"] == "correspondance" and us["User:%d" % alice]["kikan_id"] == kuser["id"], us["User:%d" % alice])
show("meme nom et prenom : homonyme", us["User:%d" % chloe]["etat_import"] == "homonyme", us["User:%d" % chloe])
show("nouvel utilisateur", us["User:%d" % bob]["etat_import"] == "nouveau", us["User:%d" % bob])
n_assets = len(j("GET", "/assets")[1])

s, r = j("POST", "/glpi/import/appliquer", {"actifs": [], "salaries": []})
show("rien de selectionne -> 400", s == 400)
s, r = j("POST", "/glpi/import/appliquer", {"actifs": [{"externe_id": "Computer:999999"}], "salaries": [{"externe_id": "User:999999"}]})
res = r["resultats"]
show("element absent de GLPI : refuse", all(x["resultat"] == "refuse" for x in res), res)
s, r = j("POST", "/glpi/import/appliquer", {
    "actifs": [{"externe_id": "Computer:%d" % pc1}, {"externe_id": "Computer:%d" % pc2}, {"externe_id": "Phone:%d" % ph1}],
    "salaries": [{"externe_id": "User:%d" % alice}, {"externe_id": "User:%d" % bob}, {"externe_id": "User:%d" % chloe}]})
res = {x["id_externe"]: x for x in r["resultats"]}
show("import applique", s == 200, r if s != 200 else r["resume"])
show("materiel nouveau : cree en stock", res["Computer:%d" % pc1]["resultat"] == "cree" and res["Phone:%d" % ph1]["resultat"] == "cree", res["Computer:%d" % pc1])
na = j("GET", "/assets/%d" % res["Computer:%d" % pc1]["id"])[1]
show("le materiel importe garde son numero de serie, son type et sa marque", na["statut"] == "stock" and na["numero_serie"] == "ZZGLSN1" and na["type"] == "ZZGL portable"
     and na["marque"] == "ZZDell" and na["modele"] == "ZZLatitude 5540" and na["source"] == "glpi" and na["id_externe"] == "Computer:%d" % pc1, na)
show("l'entite par defaut est appliquee", na["entite_id"] == EA, na["entite_id"])
show("la note rappelle l'utilisateur GLPI", "alice.zz" in (na["notes"] or ""), na["notes"])
show("materiel existant (meme numero de serie) : lie, jamais modifie", res["Computer:%d" % pc2]["resultat"] == "lie" and res["Computer:%d" % pc2]["id"] == existing["id"], res["Computer:%d" % pc2])
ex = j("GET", "/assets/%d" % existing["id"])[1]
show("le materiel existant est intact", ex["marque"] == "ZZManuel" and ex["modele"] == "M1" and ex["source"] == "manuel", ex)
show("salarie existant (meme matricule) : lie, pas duplique", res["User:%d" % alice]["resultat"] == "lie" and res["User:%d" % alice]["id"] == kuser["id"], res["User:%d" % alice])
ku = j("GET", "/users/%d" % kuser["id"])[1]
show("la fiche existante n'est pas ecrasee (nom conserve) mais son e-mail vide est complete", ku["nom"] == "Martin" and ku["prenom"] == "ZZGLalice" and ku["email"] == "alice.zz@exemple.test", ku)
show("nouvel utilisateur : cree", res["User:%d" % bob]["resultat"] == "cree", res["User:%d" % bob])
show("homonyme sans decision : conflit, rien cree", res["User:%d" % chloe]["resultat"] == "conflit" and res["User:%d" % chloe]["id"] == homonyme["id"], res["User:%d" % chloe])
s, r = j("POST", "/glpi/import/appliquer", {"actifs": [], "salaries": [{"externe_id": "User:%d" % chloe, "homonyme": "creer"}]})
show("homonyme = creer : nouvelle fiche", r["resultats"][0]["resultat"] == "cree" and r["resultats"][0]["id"] != homonyme["id"], r["resultats"])
s, r = j("POST", "/glpi/import/appliquer", {"actifs": [{"externe_id": "Computer:%d" % pc1}, {"externe_id": "Computer:%d" % pc2}],
                                            "salaries": [{"externe_id": "User:%d" % alice}, {"externe_id": "User:%d" % bob}]})
show("rejouer l'import : aucun doublon", all(x["resultat"] in ("inchange",) for x in r["resultats"]) and len(j("GET", "/assets")[1]) == n_assets + 2, [x["resultat"] for x in r["resultats"]])
s, prop2 = j("POST", "/glpi/import/apercu")
st = {a["externe_id"]: a["etat_import"] for a in prop2["actifs"]}
show("apres import : deja lies", st["Computer:%d" % pc1] == "deja_lie" and st["Computer:%d" % pc2] == "deja_lie" and st["Phone:%d" % ph1] == "deja_lie", st)
s, r = j("POST", "/glpi/import/appliquer", {"actifs": [{"externe_id": "Computer:%d" % pc3, "entite_id": EB}], "salaries": []})
nb = j("GET", "/assets/%d" % r["resultats"][0]["id"])[1] if r["resultats"][0].get("id") else {}
show("l'entite choisie a l'import l'emporte sur l'entite par defaut", nb.get("entite_id") == EB, r["resultats"])

print("== Export vers GLPI ==")
j("PUT", "/glpi/config", {**CONF, "entites": {"0": EA}})
s, du = j("POST", "/users", {"matricule": "ZZ-GL-9", "nom": "ExportZZ", "prenom": "ZZZoe", "email": "zoe.export@exemple.test", "entite_id": EA})
s, eu = j("POST", "/users", {"matricule": "ZZ-GL-8", "nom": "ExistantZZ", "prenom": "ZZEli", "email": "eli.existant@exemple.test", "entite_id": EA})
s, su = j("POST", "/users", {"matricule": "ZZ-GL-7", "nom": "SansMatZZ", "prenom": "ZZSam", "email": "sam.zz@exemple.test", "entite_id": EA})
s, a_pc = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZHP", "modele": "ZZEliteBook", "numero_serie": "ZZGLSN9", "identifiant_interne": "ZZGL-ID-9", "entite_id": EA})
s, a_ph = j("POST", "/assets", {"type": "ZZGL smartphone", "marque": "ZZApple", "modele": "ZZiPhone", "numero_serie": "ZZGLSNP9", "entite_id": EA})
s, a_ec = j("POST", "/assets", {"type": "ZZGL ecran", "marque": "ZZLG", "modele": "ZZ27", "numero_serie": "ZZGLSNE9", "entite_id": EA})
s, a_ns = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZHP", "modele": "ZZSans", "identifiant_interne": "ZZGL-ID-NS", "entite_id": EA})
s, asg = j("POST", "/assignments", {"user_id": du["id"], "asset_ids": [a_pc["id"], a_ph["id"], a_ec["id"], a_ns["id"]]})
glpi_exist = G.item("Computer", "ZZ-PC-EXISTANT", "ZZGLSN5", 0, "ZZAsus", "ZZVivo")
glpi_other = G.item("Computer", "ZZ-PC-AUTRE", "ZZGLSN6", alice, "ZZAsus", "ZZVivo")
s, a_e1 = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZAsus", "modele": "ZZVivo", "numero_serie": "ZZGLSN5", "entite_id": EA})
s, a_e2 = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZAsus", "modele": "ZZVivo", "numero_serie": "ZZGLSN6", "entite_id": EA})
j("POST", "/assignments", {"user_id": eu["id"], "asset_ids": [a_e1["id"], a_e2["id"]]})
s, a_stock = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZHP", "modele": "ZZStock", "numero_serie": "ZZGLSNST", "entite_id": EA})
n_users_glpi, n_pc_glpi = len(G.users()), len(G.items("Computer"))

s, ex = j("POST", "/glpi/export/apercu")
show("apercu de l'export", s == 200 and ex["profil_trouve"] is True, ex if s != 200 else "")
byu = {u["id"]: u for u in ex["salaries"]}
zu = byu[du["id"]]
show("salarie a creer dans GLPI, avec son materiel", zu["etat_export"] == "a_creer" and len(zu["actifs"]) == 4, zu)
states = {a["numero_serie"] or "(sans)": a["etat_export"] for a in zu["actifs"]}
show("etats du materiel : a creer, type non suivi, sans numero de serie", states == {"ZZGLSN9": "a_creer", "ZZGLSNP9": "a_creer", "ZZGLSNE9": "type_non_suivi", "(sans)": "sans_serie"}, states)
show("un salarie sans materiel est aussi propose", any(u["id"] == kuser["id"] for u in ex["salaries"]))
show("le materiel en stock n'est pas propose", not any(a["numero_serie"] == "ZZGLSNST" for u in ex["salaries"] for a in u["actifs"]))
show("utilisateur deja present dans GLPI (matricule ou e-mail) : propose en liaison", byu[su["id"]]["etat_export"] == "existe_dans_glpi" and byu[su["id"]]["critere"] == "email", byu[su["id"]])
show("materiel deja dans GLPI (meme numero de serie) : existe", {a["numero_serie"]: a["etat_export"] for a in byu[eu["id"]]["actifs"]} == {"ZZGLSN5": "existe_dans_glpi", "ZZGLSN6": "existe_dans_glpi"})

s, r = j("POST", "/glpi/export/appliquer", {"user_ids": []})
show("rien de selectionne -> 422", s == 422)
s, r = j("POST", "/glpi/export/appliquer", {"user_ids": [du["id"], eu["id"], su["id"], 999999]})
res = r["resultats"]
show("export applique", s == 200, r if s != 200 else r["resume"])
show("utilisateur cree dans GLPI", any(x["objet"] == "salarie" and x["id"] == du["id"] and x["resultat"] == "cree" for x in res), [x for x in res if x["id"] == du["id"]][:2])
gu = next((u for u in G.users() if (u.get("registration_number") == "ZZ-GL-9")), None)
show("l'utilisateur GLPI a le nom, le prenom, le matricule et l'e-mail", gu and gu["realname"] == "ExportZZ" and gu["firstname"] == "ZZZoe" and G.email_of(gu["id"]) == "zoe.export@exemple.test", gu)
show("le login vient de l'e-mail", gu and gu["name"] == "zoe.export", gu and gu["name"])
show("profil Self-Service attribue (pour de futurs tickets)", gu and G.profile_of(gu["id"]) == G.profile_id("Self-Service"), gu and G.profile_of(gu["id"]))
pcs = {c["serial"]: c for c in G.items("Computer")}
phs = {c["serial"]: c for c in G.items("Phone")}
show("ordinateur cree dans GLPI avec son numero de serie, son utilisateur et son numero d'inventaire", "ZZGLSN9" in pcs and pcs["ZZGLSN9"]["users_id"] == gu["id"] and pcs["ZZGLSN9"]["otherserial"] == "ZZGL-ID-9", pcs.get("ZZGLSN9"))
show("telephone cree dans GLPI avec son numero de serie et son utilisateur", "ZZGLSNP9" in phs and phs["ZZGLSNP9"]["users_id"] == gu["id"], phs.get("ZZGLSNP9"))
show("ecran (type non suivi) et materiel sans numero de serie : non exportes",
     not any(c["serial"] == "ZZGLSNE9" for c in G.items("Computer") + G.items("Phone")) and not any(c["name"] == "ZZGL-ID-NS" for c in G.items("Computer")))
show("les statuts du materiel exporte", {x["id"]: x["resultat"] for x in res if x["objet"] == "actif"}.get(a_ec["id"]) == "ignore"
     and {x["id"]: x["resultat"] for x in res if x["objet"] == "actif"}.get(a_ns["id"]) == "ignore")
show("materiel deja dans GLPI sans utilisateur : lie et utilisateur renseigne", G.items("Computer") and next(c for c in G.items("Computer") if c["serial"] == "ZZGLSN5")["users_id"] != 0
     and len([c for c in G.items("Computer") if c["serial"] == "ZZGLSN5"]) == 1, [x for x in res if x.get("id") == a_e1["id"]])
other = next(c for c in G.items("Computer") if c["serial"] == "ZZGLSN6")
show("materiel affecte a quelqu'un d'autre dans GLPI : lie, jamais modifie", other["users_id"] == alice and any(x.get("id") == a_e2["id"] and x["resultat"] == "lie" and "autre utilisateur" in x.get("message", "") for x in res),
     [x for x in res if x.get("id") == a_e2["id"]])
show("utilisateur GLPI existant (meme e-mail) : lie sans creation ni modification", any(x["id"] == su["id"] and x["resultat"] == "lie" for x in res if x["objet"] == "salarie"))
show("un salarie inconnu est refuse", any(x["id"] == 999999 and x["resultat"] == "refuse" for x in res))
show("pas d'utilisateur en double dans GLPI", len(G.users()) == n_users_glpi + 2, (len(G.users()), n_users_glpi))
s, r = j("POST", "/glpi/export/appliquer", {"user_ids": [du["id"], eu["id"], su["id"]]})
show("rejouer l'export : rien n'est recree", len(G.users()) == n_users_glpi + 2 and len(G.items("Computer")) == n_pc_glpi + 1
     and all(x["resultat"] in ("inchange", "ignore") for x in r["resultats"]), (r["resume"], len(G.items("Computer")), n_pc_glpi))
s, ex2 = j("POST", "/glpi/export/apercu")
byu2 = {u["id"]: u for u in ex2["salaries"]}
show("apres l'export : deja lie", byu2[du["id"]]["etat_export"] == "deja_lie" and not byu2[du["id"]]["a_traiter"], byu2[du["id"]])

print("== Conflits de liaison ==")
s, dup = j("POST", "/users", {"matricule": "ZZ-GL-4", "nom": "DoublonZZ", "prenom": "ZZDup", "email": "chloe.zz@exemple.test", "entite_id": EA})
s, ex3 = j("POST", "/glpi/export/apercu")
show("utilisateur GLPI deja lie a une autre fiche Kikan : conflit propose", {u["id"]: u for u in ex3["salaries"]}[dup["id"]]["etat_export"] == "conflit")
s, r = j("POST", "/glpi/export/appliquer", {"user_ids": [dup["id"]]})
show("export : conflit signale, aucune erreur serveur, rien cree", s == 200 and r["resultats"][0]["resultat"] == "conflit", r)
j("DELETE", "/users/%d" % dup["id"])

print("== Login deja pris et panne ==")
s, cu = j("POST", "/users", {"matricule": "ZZ-GL-6", "nom": "CollisionZZ", "prenom": "ZZZoe", "email": "zoe.export@autre-domaine.test", "entite_id": EA})
s, r = j("POST", "/glpi/export/appliquer", {"user_ids": [cu["id"]]})
new = next((u for u in G.users() if u.get("registration_number") == "ZZ-GL-6"), None)
show("login deja pris par une autre personne : suffixe, pas de fusion", new and new["name"] == "zoe.export2" and new["id"] != gu["id"], new and new["name"])
if not LIVE:
    s, fu = j("POST", "/users", {"matricule": "ZZ-GL-5", "nom": "PanneZZ", "prenom": "ZZPia", "email": "pia.panne@exemple.test", "entite_id": EA})
    s, f1 = j("POST", "/assets", {"type": "ZZGL portable", "marque": "ZZHP", "modele": "ZZP", "numero_serie": "ZZGLFAIL", "entite_id": EA})
    s, f2 = j("POST", "/assets", {"type": "ZZGL smartphone", "marque": "ZZHP", "modele": "ZZQ", "numero_serie": "ZZGLSNOK", "entite_id": EA})
    j("POST", "/assignments", {"user_id": fu["id"], "asset_ids": [f1["id"], f2["id"]]})
    G.fail_serial("ZZGLFAIL")
    s, r = j("POST", "/glpi/export/appliquer", {"user_ids": [fu["id"]]})
    rr = {x["id"]: x["resultat"] for x in r["resultats"] if x["objet"] == "actif"}
    show("une erreur GLPI sur un materiel n'arrete pas les autres", rr.get(f1["id"]) == "erreur" and rr.get(f2["id"]) == "cree", rr)
    show("l'erreur est expliquee sans exposer le jeton", all(TOKEN not in json.dumps(x) for x in r["resultats"]))

print("== Historique et journal ==")
s, h = j("GET", "/glpi/historique")
show("historique des synchronisations", s == 200 and {x["sens"] for x in h} == {"import", "export"} and all(isinstance(x["resume"], dict) for x in h), h[:1])
show("l'historique ne contient ni nom ni jeton", TOKEN not in json.dumps(h) and "ZZ" not in json.dumps(h).replace("ZZGL", ""))
s, rows = j("GET", "/audit?limit=400")
rows = rows if isinstance(rows, list) else rows.get("items", [])
actions = {r.get("action") for r in rows}
show("reglages, test, apercus, imports et exports journalises", {"glpi_reglages", "glpi_test", "glpi_import_apercu", "glpi_import", "glpi_export_apercu", "glpi_export"} <= actions,
     sorted(a for a in actions if a and a.startswith("glpi")))
show("aucun jeton ni nom de salarie dans le journal", all(TOKEN not in json.dumps(r) and "ExportZZ" not in json.dumps(r) for r in rows))

print("== Arret ==")
j("PUT", "/glpi/config", {**CONF, "actif": False})
s, r = j("POST", "/glpi/export/apercu")
show("connecteur desactive : export refuse", s == 409)
G.clean()
print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
