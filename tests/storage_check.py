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

"""Tests du stockage des PDF scelles (local, SMB, WebDAV) sur une instance de DEVELOPPEMENT.

Usage (le backend teste est celui configure dans l'API ; voir SECURITY.md) :
  docker exec -i -e TEST_EXPECT_BACKEND=smb -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... \
    kikan-api python - < tests/storage_check.py

Affiche KEY_MAIN=... et KEY_PURGED=... : cles de stockage a verifier cote serveur de fichiers.
Code de sortie 1 si un test echoue. Cree des donnees ZZST (nettoyage : tests/cleanup_test_data.sql).
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
EXPECT = os.environ.get("TEST_EXPECT_BACKEND", "local")
fails = 0


def signature_b64():
    """Signature manuscrite de test (PNG 1000x400, trace fonce sur fond transparent)."""
    import base64
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIG = signature_b64()
SIGN = {"consent": True, "signature_image": SIG, "strokes": 4, "duration_ms": 1800}


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


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


s, b = call("POST", "/auth/login", {"username": os.environ.get("TEST_ADMIN_USER", "admin"),
                                     "password": os.environ.get("TEST_ADMIN_PASSWORD", "")})
if s != 200:
    sys.exit("Connexion admin impossible")
T = json.loads(b)["access_token"]


def j(method, path, body=None):
    s, b = call(method, path, body, T)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


print(f"== Stockage attendu : {EXPECT} ==")
s, st = j("GET", "/storage/status")
show("le backend actif est celui attendu", s == 200 and st["active"] == EXPECT, st.get("active") if s == 200 else s)
s, tc = j("POST", "/storage/test", {})
show("test de connexion (ecriture, lecture, suppression)", s == 200 and tc.get("ok") is True, tc)

print("== Remise signee deposee sur le stockage ==")
s, u = j("POST", "/users", {"nom": "Stockage", "prenom": "Test", "matricule": "ZZST1", "statut": "actif"})
s, a = j("POST", "/assets", {"type": "PC", "marque": "ZZST", "modele": "M1", "numero_serie": "ZZST-SN1", "statut": "stock"})
s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]]})
s, sig = j("POST", f"/assignments/{asg['id']}/sign", SIGN)
ref = sig.get("ged_reference", "") if s == 201 else ""
show("signature creee", s == 201, s)
show(f"reference au format {EXPECT}:AAAA/...", ref.startswith(f"{EXPECT}:") and "/" in ref, ref)
print("KEY_MAIN=" + ref.partition(":")[2])
s, pdf = call("GET", f"/assignments/{asg['id']}/document", token=T)
show("document relu depuis le stockage (PDF)", s == 200 and pdf[:4] == b"%PDF", f"HTTP {s}, {len(pdf)} octets")
show("empreinte SHA-256 identique a celle enregistree", hashlib.sha256(pdf).hexdigest() == sig.get("empreinte_doc"))
s, st = j("GET", "/storage/status")
show("aucun document en attente de depot", st["documents"]["en_attente_de_depot"] == 0, st["documents"])
show(f"le document est compte sous '{EXPECT}'", st["documents"]["par_backend"].get(EXPECT, 0) >= 1)

print("== Restitution deposee sur le stockage ==")
s, _ = j("POST", f"/lifecycle/depart/{u['id']}", {"date_sortie": "2026-12-31"})
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u["id"], **SIGN})
rref = rs.get("ged_reference", "") if s == 201 else ""
show("restitution signee et deposee", s == 201 and rref.startswith(f"{EXPECT}:"), rref)
print("KEY_RESTIT=" + rref.partition(":")[2])

print("== Cles de stockage dangereuses ==")
try:
    sys.path.insert(0, "/app")
    from app import filestore
    for bad in ("../x.pdf", "/etc/passwd", "2026/../../x", "a b.pdf", "", "2026//x.pdf", "..", "x/./y"):
        try:
            filestore.safe_key(bad)
            show(f"cle refusee : {bad!r}", False)
        except filestore.StorageError:
            show(f"cle refusee : {bad!r}", True)
    for bad_ref in ("smb:../x", "webdav:/abs", "ftp:2026/x.pdf", "/etc/passwd", "local:../../etc/passwd"):
        try:
            filestore.parse_reference(bad_ref)
            show(f"reference refusee : {bad_ref!r}", False)
        except filestore.StorageError:
            show(f"reference refusee : {bad_ref!r}", True)
except Exception as exc:  # noqa: BLE001
    show("import du module de stockage", False, exc)

print("== Purge RGPD : le document disparait aussi du stockage ==")
s, u2 = j("POST", "/users", {"nom": "Ancien", "prenom": "Stockage", "matricule": "ZZST2", "statut": "actif"})
s, a2 = j("POST", "/assets", {"type": "PC", "marque": "ZZST", "modele": "M2", "numero_serie": "ZZST-SN2", "statut": "stock"})
s, asg2 = j("POST", "/assignments", {"user_id": u2["id"], "asset_ids": [a2["id"]]})
s, sig2 = j("POST", f"/assignments/{asg2['id']}/sign", SIGN)
print("KEY_PURGED=" + sig2.get("ged_reference", "").partition(":")[2])
j("POST", f"/lifecycle/depart/{u2['id']}", {"date_sortie": "2019-01-01"})
s, _ = j("POST", "/lifecycle/restituer", {"user_id": u2["id"], **SIGN})
j("PUT", "/rgpd/retention", {"mois": 36})
s, pg = j("POST", "/rgpd/purge", {})
show("purge effectuee avec suppression du document", s == 200 and pg.get("documents", 0) >= 1, pg)

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
