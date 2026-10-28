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

"""Stockage SharePoint Online et DocuWare (B6) : depot des PDF scelles, relecture, integrite, pannes, jetons, copie.

Les deux moteurs se testent avec le meme script, contre de FAUX serveurs integres (Microsoft Graph, DocuWare, WebDAV) :
  docker compose -f docker-compose.yml -f tests/storage-sharepoint.override.yml up -d api
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/documents_check.py
  docker compose -f docker-compose.yml -f tests/storage-docuware.override.yml up -d api
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/documents_check.py
  docker compose up -d --force-recreate api        # retour a la normale

Le moteur teste est celui de l'API (variable KIKAN_STORAGE_BACKEND du conteneur). Cree des donnees ZZDOC (nettoyage :
tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue. Ce fichier reste en ASCII (independant du lanceur).
"""
import base64
import email.parser
import email.policy
import hashlib
import io
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
MODE = os.environ.get("KIKAN_STORAGE_BACKEND", "local")
if MODE not in ("sharepoint", "docuware"):
    sys.exit("Ce script teste le moteur sharepoint ou docuware (voir l'en-tete)")
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:170] if detail else ""))


# ====================================================================== faux serveurs
class State:
    def __init__(self):
        self.files = {}            # sharepoint : chemin -> octets ; docuware : id -> {"data", "fields", "name"} ; webdav : chemin -> octets
        self.dw_seq = 4000
        self.fail = False          # tout echoue en 500
        self.deny_auth = False     # le point d'authentification refuse
        self.token_n = 0
        self.valid_tokens = set()
        self.tokens_issued = 0
        self.once_429 = False
        self.uploads = {}          # sessions de televersement
        self.blobs = {}
        self.blob_auth_headers = []   # en-tetes Authorization recus par le serveur de fichiers (doivent rester vides)
        self.chunks = []
        self.dw_bad_multipart = []
        self.requests = []


S = State()


def issue_token():
    S.token_n += 1
    S.tokens_issued += 1
    tok = "tok-%d" % S.token_n
    S.valid_tokens.add(tok)
    return tok


class Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _send(self, status, body=b"", headers=None, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _authorized(self):
        return self.headers.get("Authorization", "")[7:] in S.valid_tokens

    def _route(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        body = self._body()
        S.requests.append((method, path))
        if path.startswith("/dav/"):
            return self._webdav(method, path[len("/dav/"):], body)
        if S.fail:
            return self._send(500, {"error": {"code": "serverError"}})
        if path.startswith("/blob/") or path.startswith("/upload/"):
            return self._files(method, path, body)
        if path.endswith("/oauth2/v2.0/token") or path.endswith("/connect/token"):
            form = urllib.parse.parse_qs(body.decode())
            ok = not S.deny_auth
            if path.endswith("/oauth2/v2.0/token"):
                ok = ok and form.get("client_secret") == ["zz-secret-test-0123456789"] and form.get("grant_type") == ["client_credentials"]
            else:
                ok = ok and form.get("password") == ["zz-password-test-0123456789"] and form.get("grant_type") == ["password"] \
                    and form.get("scope") == ["docuware.platform"]
            if not ok:
                return self._send(400, {"error": "invalid_client"})
            return self._send(200, {"access_token": issue_token(), "expires_in": 3600, "token_type": "Bearer"})
        if path == "/DocuWare/Platform/Home/IdentityServiceInfo":
            return self._send(200, {"IdentityServiceUrl": "http://127.0.0.1:2620/DocuWare/Identity"})
        if not self._authorized():
            return self._send(401, {"error": {"code": "InvalidAuthenticationToken"}})
        if S.once_429:
            S.once_429 = False
            return self._send(429, {"error": {"code": "activityLimitReached"}}, {"Retry-After": "1"})
        if path.startswith("/v1.0/"):
            return self._graph(method, path[len("/v1.0"):], body, parsed)
        if path.startswith("/DocuWare/Platform/"):
            return self._docuware(method, path[len("/DocuWare/Platform"):], body)
        return self._send(404, {"error": {"code": "notFound"}})

    # ---------------- Microsoft Graph
    def _graph(self, method, path, body, parsed):
        if method == "GET" and path.startswith("/sites/zz.sharepoint.test:/sites/Kikan"):
            return self._send(200, {"id": "zz.sharepoint.test,site-1,web-1"})
        if method == "GET" and path.startswith("/sites/zz.sharepoint.test,site-1,web-1/drives"):
            return self._send(200, {"value": [{"id": "drive-1", "name": "Documents"}, {"id": "drive-2", "name": "Autre"}]})
        if path.startswith("/drives/drive-1/root:/"):
            rest = path[len("/drives/drive-1/root:/"):]
            item, _, action = rest.rpartition(":")
            action = action.strip("/")
            if method == "PUT" and action == "content":
                S.files[item] = body
                return self._send(201, {"id": "item-1", "name": item.rsplit("/", 1)[-1]})
            if method == "POST" and action == "createUploadSession":
                sid = "u%d" % len(S.uploads)
                S.uploads[sid] = {"item": item, "data": bytearray()}
                return self._send(200, {"uploadUrl": "http://127.0.0.1:2610/upload/" + sid})
            if method == "GET" and action == "content":
                if item not in S.files:
                    return self._send(404, {"error": {"code": "itemNotFound"}})
                bid = "b%d" % len(S.blobs)
                S.blobs[bid] = S.files[item]
                return self._send(302, b"", {"Location": "http://127.0.0.1:2610/blob/" + bid + "/" + item.rsplit("/", 1)[-1]})
            if method == "DELETE" and action == "":
                if item not in S.files:
                    return self._send(404, {"error": {"code": "itemNotFound"}})
                del S.files[item]
                return self._send(204)
        return self._send(404, {"error": {"code": "notFound"}})

    def _files(self, method, path, body):
        S.blob_auth_headers.append(self.headers.get("Authorization"))
        if path.startswith("/blob/") and method == "GET":
            bid = path.split("/")[2]
            return self._send(200, S.blobs[bid], ctype="application/octet-stream")
        if path.startswith("/upload/") and method == "PUT":
            up = S.uploads[path.split("/")[2]]
            rng = self.headers.get("Content-Range", "")
            start, end_total = rng[len("bytes "):].split("-")
            end, total = end_total.split("/")
            if int(start) != len(up["data"]):
                return self._send(416, {"error": "range"})
            up["data"].extend(body)
            S.chunks.append(len(body))
            if int(end) + 1 == int(total):
                S.files[up["item"]] = bytes(up["data"])
                return self._send(201, {"id": "item-big"})
            return self._send(202, {"nextExpectedRanges": ["%d-" % (int(end) + 1)]})
        return self._send(404, {})

    # ---------------- DocuWare
    def _docuware(self, method, path, body):
        if method == "GET" and path == "/FileCabinets":
            return self._send(200, {"FileCabinet": [{"Id": "bask-1", "Name": "Kikan", "IsBasket": True}, {"Id": "cab-guid-1", "Name": "Kikan", "IsBasket": False}]})
        if path == "/FileCabinets/cab-guid-1/Documents" and method == "POST":
            msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
            parts = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
            try:
                index = json.loads(parts["document"].get_content())
                fpart = parts["file[]"]
                data = fpart.get_payload(decode=True)
                name = fpart.get_filename()
                assert data.startswith(b"%PDF") or len(data) > 0
            except Exception as exc:  # noqa: BLE001
                S.dw_bad_multipart.append(str(exc))
                return self._send(400, {"Message": "Invalid multipart"})
            S.dw_seq += 1
            S.files[S.dw_seq] = {"data": data, "fields": {f["FieldName"]: (f["Item"], f["ItemElementName"]) for f in index["Fields"]}, "name": name}
            return self._send(200, {"Id": S.dw_seq, "Title": name})
        if path.startswith("/FileCabinets/cab-guid-1/Documents/"):
            rest = path[len("/FileCabinets/cab-guid-1/Documents/"):].split("/")
            did = int(rest[0])
            if method == "GET" and len(rest) > 1 and rest[1] == "FileDownload":
                if did not in S.files:
                    return self._send(404, {"Message": "not found"})
                return self._send(200, S.files[did]["data"], ctype="application/pdf")
            if method == "DELETE":
                if did not in S.files:
                    return self._send(404, {"Message": "not found"})
                del S.files[did]
                return self._send(204)
        return self._send(404, {"Message": "not found"})

    # ---------------- WebDAV (ancien emplacement pour l'outil de copie)
    def _webdav(self, method, path, body):
        if method == "MKCOL":
            return self._send(201)
        if method == "PUT":
            S.files[("dav", path)] = body
            return self._send(201)
        if method == "GET":
            data = S.files.get(("dav", path))
            return self._send(200, data, ctype="application/octet-stream") if data is not None else self._send(404)
        if method == "DELETE":
            S.files.pop(("dav", path), None)
            return self._send(204)
        return self._send(405)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def do_MKCOL(self):
        self._route("MKCOL")


for port in (2610, 2620, 2630):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def stored_files():
    """Fichiers vus par le faux serveur du moteur teste : liste d'octets."""
    if MODE == "sharepoint":
        return {k: v for k, v in S.files.items() if isinstance(k, str)}
    return {k: v["data"] for k, v in S.files.items() if isinstance(k, int)}


# ====================================================================== client Kikan
def call(method, path, payload=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
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


img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)], fill=(17, 17, 17, 255), width=7)
_buf = io.BytesIO()
img.save(_buf, "PNG")
SIGN = {"consent": True, "signature_image": "data:image/png;base64," + base64.b64encode(_buf.getvalue()).decode(), "strokes": 4, "duration_ms": 1800}

print("== Preparation (%s) ==" % MODE)
s, ent = j("POST", "/entites", {"code": "ZZDOC-A", "nom": "ZZDOC Filiale"})
if s == 409:
    ent = next(e for e in j("GET", "/entites")[1] if e["code"] == "ZZDOC-A")
for name, role in (("sec_dc_rh", "rh"), ("sec_dc_lec", "lecture")):
    j("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True})
RH, LEC = login("sec_dc_rh", PW), login("sec_dc_lec", PW)
show("comptes de test", bool(RH and LEC))
from sqlmodel import Session, select  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Signature  # noqa: E402
from app import filestore  # noqa: E402


def new_remise(key):
    s, u = j("POST", "/users", {"matricule": "ZZDOC-" + key, "nom": "Nom" + key, "prenom": "ZZDOC" + key, "entite_id": ent["id"]})
    s, a = j("POST", "/assets", {"type": "ZZDOC type", "marque": "ZZDOC", "modele": "M" + key, "numero_serie": "ZZDOC-SN-" + key,
                                  "identifiant_interne": "ZZDOC-ID-" + key, "entite_id": ent["id"]})
    s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]]})
    return u, a, asg


print("== Etat et test de depot ==")
s, st = j("GET", "/storage/status")
show("moteur actif et reglages non secrets", st["active"] == MODE and st["documents_seulement"] is True and st["description"], st)
show("aucun secret dans l'etat", "zz-secret" not in json.dumps(st) and "zz-password" not in json.dumps(st))
s, r = j("POST", "/storage/test")
show("test de depot : ecriture, relecture et suppression", s == 200 and r["ok"] is True and r["backend"] == MODE, r)
show("le fichier d'essai est supprime", not stored_files(), len(stored_files()))
for who, tok in (("RH", RH), ("lecture", LEC)):
    for method, path in (("POST", "/storage/test"), ("POST", "/storage/migrer"), ("POST", "/storage/sync"), ("GET", "/storage/status")):
        s, _ = j(method, path, {} if method == "POST" else None, token=tok)
        show("%s %s refuse a un compte %s" % (method, path, who), s == 403, s)

print("== Remise signee ==")
u1, a1, asg1 = new_remise("1")
s, sg = j("POST", "/assignments/%d/sign" % asg1["id"], SIGN)
show("remise signee", s == 201, sg)
ref = sg.get("ged_reference", "") if isinstance(sg, dict) else ""
show("reference sur le moteur actif", ref.startswith(MODE + ":") and ref.endswith(".pdf"), ref)
files = stored_files()
show("le PDF est dans le service", len(files) == 1 and next(iter(files.values())).startswith(b"%PDF"), list(files)[:2])
data = next(iter(files.values())) if files else b""
show("empreinte enregistree = empreinte du fichier depose", sg["empreinte_doc"] == hashlib.sha256(data).hexdigest())
if MODE == "sharepoint":
    path = next(iter(files))
    show("rangement <dossier>/<annee>/<fichier>", path.startswith("Kikan/20") and "/remise_%d_" % asg1["id"] in path, path)
else:
    did = next(iter(S.files))
    show("reference DocuWare : identifiant du document en tete de cle", ref.startswith("docuware:%d/" % did), ref)
    fields = S.files[did]["fields"]
    show("champs d'index associes envoyes (type, annee, numero, entite, cle)",
         fields.get("TYPE_DOC") == ("Remise", "String") and fields.get("ANNEE", (0, ""))[1] == "Int" and fields.get("NUMERO") == (asg1["id"], "Int")
         and fields.get("ENTITE") == ("ZZDOC Filiale", "String") and fields.get("CLE_KIKAN", ("",))[0].endswith(".pdf"), fields)
    show("aucune donnee nominative envoyee (champs non associes)", set(fields) == {"TYPE_DOC", "ANNEE", "NUMERO", "ENTITE", "CLE_KIKAN"}
         and "NomZZ" not in json.dumps(fields, default=str) and "ZZDOC-1" not in json.dumps(fields, default=str), sorted(fields))
    show("le fichier porte un nom de fichier propre", S.files[did]["name"].startswith("remise_") and S.files[did]["name"].endswith(".pdf"), S.files[did]["name"])
s, pdf = call("GET", "/assignments/%d/document" % asg1["id"], token=ADM)
show("relecture du document par l'API", s == 200 and pdf == data, s)
s, pdf = call("GET", "/assignments/%d/document" % asg1["id"], token=ADM)
show("deuxieme lecture identique (jeton reutilise)", s == 200 and pdf == data)

print("== Restitution signee ==")
j("POST", "/lifecycle/depart/%d" % u1["id"], {"date_sortie": "2026-12-31"})
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u1["id"], **SIGN})
show("restitution signee et deposee", s == 201 and rs["ged_reference"].startswith(MODE + ":") and "restitution_" in rs["ged_reference"], rs)
if MODE == "docuware":
    last = max(k for k in S.files if isinstance(k, int))
    show("type d'index : Restitution", S.files[last]["fields"].get("TYPE_DOC") == ("Restitution", "String"), S.files[last]["fields"])

print("== Les chartes restent en local (uniquement les PDF scelles) ==")
before = dict(stored_files())
bd = "zzdocbd"
raw = ('--%s\r\nContent-Disposition: form-data; name="titre"\r\n\r\nZZDOC charte\r\n--%s\r\nContent-Disposition: form-data; name="file"; filename="c.md"\r\n'
       'Content-Type: text/markdown\r\n\r\n# Charte\n\nTexte de test.\r\n--%s--\r\n' % (bd, bd, bd)).encode()
s, b = call("POST", "/policies", token=ADM, raw=raw, ctype="multipart/form-data; boundary=" + bd)
pol = json.loads(b)
show("depot de charte", s == 201, pol)
with Session(engine) as s_:
    from app.models import Policy
    p = s_.get(Policy, pol["id"])
    show("la charte et son original sont dans le volume local, pas dans le service", p.fichier_ref.startswith("local:") and p.source_ref.startswith("local:"), (p.fichier_ref, p.source_ref))
show("aucun fichier de charte envoye au service", stored_files() == before)
show("une charte locale n'est pas 'en attente de depot'", pol["en_attente_depot"] is False, pol)
s, r = call("GET", "/policies/%d/fichier" % pol["id"], token=ADM)
show("la charte se relit normalement", s == 200 and r.startswith(b"%PDF"))

print("== Integrite ==")
u2, a2, asg2 = new_remise("2")
s, sg2 = j("POST", "/assignments/%d/sign" % asg2["id"], SIGN)
if MODE == "sharepoint":
    key = next(k for k in S.files if isinstance(k, str) and "/remise_%d_" % asg2["id"] in k)
    S.files[key] = S.files[key] + b"x"
else:
    did2 = int(sg2["ged_reference"].split(":")[1].split("/")[0])
    S.files[did2]["data"] += b"x"
s, r = call("GET", "/assignments/%d/document" % asg2["id"], token=ADM)
show("document altere dans le service : refuse (integrite)", s == 500 and b"Integrite" in r, (s, r[:80]))

print("== Jeton expire ou revoque ==")
tokens_before = S.tokens_issued
S.valid_tokens.clear()      # le service rejette le jeton en cours
s, pdf = call("GET", "/assignments/%d/document" % asg1["id"], token=ADM)
show("jeton rejete : renouvele une fois, la lecture reussit", s == 200 and pdf == data and S.tokens_issued == tokens_before + 1, (s, S.tokens_issued - tokens_before))
S.once_429 = True
s, pdf = call("GET", "/assignments/%d/document" % asg1["id"], token=ADM)
show("limitation de debit (429 + Retry-After) : nouvelle tentative", s == 200 and pdf == data, s)

print("== Authentification refusee ==")
S.valid_tokens.clear()
S.deny_auth = True
s, r = j("POST", "/storage/test")
show("authentification refusee : message clair, sans secret", r["ok"] is False and "authentification" in r["detail"].lower()
     and "zz-secret" not in json.dumps(r) and "zz-password" not in json.dumps(r), r)
S.deny_auth = False

print("== Panne du service : tampon local puis reprise ==")
u3, a3, asg3 = new_remise("3")
S.fail = True
s, sg3 = j("POST", "/assignments/%d/sign" % asg3["id"], SIGN)
show("service en panne : la signature n'echoue pas, le document reste en local", s == 201 and sg3["ged_reference"].startswith("local:"), sg3)
s, st = j("GET", "/storage/status")
show("document signale en attente de depot", st["documents"]["en_attente_de_depot"] >= 1, st["documents"])
s, r = j("POST", "/storage/test")
show("test de depot pendant la panne : echec lisible", r["ok"] is False and r["detail"], r)
S.fail = False
s, r = j("POST", "/storage/sync")
show("reprise : le document en attente est depose", s == 200 and r["synced"] >= 1 and r["failed"] == 0, r)
with Session(engine) as s_:
    sig3 = s_.exec(select(Signature).where(Signature.assignment_id == asg3["id"])).one()
    show("la reference pointe maintenant sur le service", sig3.ged_reference.startswith(MODE + ":"), sig3.ged_reference)
    show("le contenu depose correspond a l'empreinte", hashlib.sha256(filestore.read_document(sig3.ged_reference)).hexdigest() == sig3.empreinte_doc)

print("== Gros fichiers, redirection, chemins ==")
backend = filestore.get_backend(MODE)
big = os.urandom(9 * 1024 * 1024 + 123)
stored = backend.write("2026/zzdoc_gros.pdf", big, {"type": "Remise", "annee": "2026"}) or "2026/zzdoc_gros.pdf"
if MODE == "sharepoint":
    show("fichier de plus de 4 Mio : session de televersement par blocs", len(S.chunks) >= 1 and sum(S.chunks) == len(big), S.chunks)
    S.blob_auth_headers.clear()
    got = backend.read(stored)
    show("relecture d'un gros fichier", got == big)
    show("l'adresse de telechargement est appelee SANS en-tete Authorization", S.blob_auth_headers and all(h is None for h in S.blob_auth_headers), S.blob_auth_headers)
else:
    got = backend.read(stored)
    show("gros fichier : depot et relecture", got == big)
backend.delete(stored)
show("suppression", len(stored_files()) <= 4)
for bad in ("../evil.pdf", "/abs.pdf", "a/../../b.pdf", "a b.pdf", "a\\b.pdf"):
    try:
        backend.write(bad, b"x")
        show("cle refusee : %s" % bad, False)
    except filestore.StorageError:
        show("cle refusee : %s" % bad, True)

print("== Copie vers le moteur actif (depuis WebDAV) ==")
old_pdf = b"%PDF-1.4 ancien document zzdoc " + os.urandom(16)
S.files[("dav", "2026/zzdoc_ancien.pdf")] = old_pdf
u4, a4, asg4 = new_remise("4")
with Session(engine) as s_:
    s_.add(Signature(assignment_id=asg4["id"], signataire="ZZ", methode="manuscrite", empreinte_doc=hashlib.sha256(old_pdf).hexdigest(), ged_reference="webdav:2026/zzdoc_ancien.pdf"))
    s_.commit()
u5, a5, asg5 = new_remise("5")
S.files[("dav", "2026/zzdoc_corrompu.pdf")] = b"%PDF contenu different de l'empreinte"
with Session(engine) as s_:
    s_.add(Signature(assignment_id=asg5["id"], signataire="ZZ", methode="manuscrite", empreinte_doc=hashlib.sha256(b"autre chose").hexdigest(), ged_reference="webdav:2026/zzdoc_corrompu.pdf"))
    s_.commit()
n_files = len(stored_files())
s, r = j("POST", "/storage/migrer")
show("simulation par defaut : 2 documents a copier, rien n'est fait", s == 200 and r["simulation"] is True and r["a_copier"] == 2 and r["copies"] == 0 and len(stored_files()) == n_files, r)
s, r = j("POST", "/storage/migrer?dry_run=false")
show("copie reelle : un document copie, un refuse (empreinte differente)", s == 200 and r["copies"] == 1 and r["echecs"] == 1 and "Empreinte" in json.dumps(r["erreurs"]), r)
with Session(engine) as s_:
    a = s_.exec(select(Signature).where(Signature.assignment_id == asg4["id"])).one()
    b = s_.exec(select(Signature).where(Signature.assignment_id == asg5["id"])).one()
    show("la reference du document copie pointe sur le service, contenu identique", a.ged_reference.startswith(MODE + ":") and filestore.read_document(a.ged_reference) == old_pdf, a.ged_reference)
    show("le document refuse garde son ancienne reference", b.ged_reference == "webdav:2026/zzdoc_corrompu.pdf", b.ged_reference)
show("rien n'est supprime de l'ancien emplacement", ("dav", "2026/zzdoc_ancien.pdf") in S.files and ("dav", "2026/zzdoc_corrompu.pdf") in S.files)
s, r = j("POST", "/storage/migrer?dry_run=false")
show("rejouer la copie : plus rien a copier pour le document deja traite", r["copies"] == 0 and r["a_copier"] == 1, r)
s, rows = j("GET", "/audit?limit=300")
rows = rows if isinstance(rows, list) else rows.get("items", [])
show("la copie est journalisee, sans secret", any(x.get("action") == "stockage_copie" for x in rows) and all("zz-secret" not in json.dumps(x) and "zz-password" not in json.dumps(x) for x in rows))

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
