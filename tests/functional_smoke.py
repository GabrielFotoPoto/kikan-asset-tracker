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

"""Test fonctionnel de non-regression des flux metier (instance de DEVELOPPEMENT).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/functional_smoke.py

Cree des donnees marquees ZZFN (a nettoyer ensuite). Code de sortie 1 si un test echoue.
"""
import glob
import json
import os
import sys
import urllib.error
import urllib.request

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
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


def call(method, path, body=None, token=None, raw=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""))


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


print("== Donnees de base ==")
s, ent = j("POST", "/entites", {"code": "ZZFN-E", "nom": "ZZFN Entite"})
show("creation entite", s == 201)
s, u = j("POST", "/users", {"nom": "Fonctionnel", "prenom": "Test", "matricule": "ZZFN1", "service": "Compta",
                             "entite_id": ent.get("id"), "statut": "actif", "date_arrivee": "2026-01-05"})
show("creation salarie (dates, cree_le/maj_le)", s == 201 and u.get("cree_le"), f"HTTP {s}")
s, a1 = j("POST", "/assets", {"type": "PC portable", "marque": "ZZFN-Dell", "modele": "Latitude",
                               "numero_serie": "ZZFN-SN1", "identifiant_interne": "ZZFN-PC1",
                               "date_achat": "2025-03-01", "echeance_renouvellement": "2027-03-01", "statut": "stock"})
show("creation actif", s == 201)
s, a2 = j("POST", "/assets", {"type": "Smartphone", "marque": "ZZFN-Samsung", "modele": "S24",
                               "numero_serie": "ZZFN-SN2", "statut": "stock"})
s, mq = j("GET", "/assets/catalogue/marques?q=zzfn-d")
show("autocompletion des marques", s == 200 and "ZZFN-Dell" in mq, str(mq))
s, md = j("GET", "/assets/catalogue/modeles?marque=ZZFN-Dell")
show("autocompletion des modeles", s == 200 and "Latitude" in md, str(md))

print("== Remise signee (PAdES) ==")
s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a1["id"], a2["id"]], "cree_par": "test"})
show("creation de l'affectation (2 actifs)", s == 201 and asg.get("statut") == "en_cours", f"HTTP {s}")
s, sig = j("POST", f"/assignments/{asg['id']}/sign", SIGN)
show("signature et scellement", s == 201 and sig.get("empreinte_doc"), f"HTTP {s}")
show("signataire deduit de la fiche du salarie", sig.get("signataire") == "Test Fonctionnel", sig.get("signataire"))
s, pdf = call("GET", f"/assignments/{asg['id']}/document", token=T)
show("telechargement du PDF scelle", s == 200 and pdf[:4] == b"%PDF", f"{len(pdf)} octets")
try:
    import io

    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    # Le PDF est lu tel que l'API le sert (volume local, partage SMB ou WebDAV).
    show("reference de stockage au format backend:cle", sig["ged_reference"].partition(":")[0] in ("local", "smb", "webdav"),
         sig["ged_reference"])
    sg = PdfFileReader(io.BytesIO(pdf)).embedded_signatures[0]
    try:
        st = validate_pdf_signature(sg)
        show("signature PAdES intacte et valide", st.intact and st.valid)
    except Exception as exc:  # noqa: BLE001  (certificat auto-signe : chemin de confiance absent)
        show("signature PAdES validable", False, str(exc)[:80])
except Exception as exc:  # noqa: BLE001
    show("lecture de la signature PAdES", False, str(exc)[:80])
s, a1b = j("GET", f"/assets/{a1['id']}")
show("l'actif est passe en 'affecte'", a1b.get("statut") == "affecte")

print("== Acces applicatifs ==")
s, app_ = j("POST", "/applications", {"nom": "ZZFN-ERP"})
s, ua = j("POST", f"/users/{u['id']}/applications", {"application_id": app_["id"], "acces": True, "note": "admin"})
show("attribution d'un acces", s == 201, f"HTTP {s}")
s, ua2 = j("POST", f"/users/{u['id']}/applications", {"application_id": app_["id"], "acces": False, "note": "retire"})
show("upsert du meme acces", s == 201 and ua2["id"] == ua["id"])
s, lst = j("GET", f"/users/{u['id']}/applications")
show("liste des acces", s == 200 and len(lst) == 1 and lst[0]["note"] == "retire")

print("== Reporting et statistiques ==")
s, rep = j("GET", "/reports/holdings?format=json")
show("rapport JSON contient l'affectation", s == 200 and any(r["matricule"] == "ZZFN1" for r in rep["rows"]))
s, c = call("GET", "/reports/holdings?format=csv", token=T)
show("export CSV", s == 200 and b"ZZFN1" in c)
s, p = call("GET", "/reports/holdings?format=pdf", token=T)
show("export PDF", s == 200 and p[:4] == b"%PDF")
s, st = j("GET", "/stats")
show("statistiques", s == 200 and st["actifs_total"] >= 2 and st["renouvellements_12m"]["count"] >= 0)

print("== Depart et restitution ==")
s, dep = j("POST", f"/lifecycle/depart/{u['id']}", {"date_sortie": "2026-12-31"})
show("declaration du depart", s == 200 and len(dep["materiel_a_recuperer"]) == 2, f"HTTP {s}")
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u["id"], **SIGN})
show("restitution signee", s == 201 and rs["audit_json"]["type"] == "restitution", f"HTTP {s}")
s, u2 = j("GET", f"/users/{u['id']}")
show("le salarie passe en 'sorti'", u2.get("statut") == "sorti")
s, a1c = j("GET", f"/assets/{a1['id']}")
show("les actifs passent en 'rendu'", a1c.get("statut") == "rendu")

print("== Retention RGPD ==")
j("PUT", "/rgpd/retention", {"mois": 36})
s, old = j("POST", "/users", {"nom": "Ancien", "prenom": "ZZFN", "matricule": "ZZFN2", "statut": "sorti",
                               "date_sortie": "2019-01-01"})
s, pv = j("GET", "/rgpd/purge-preview")
show("previsualisation liste l'ancien salarie", s == 200 and any(c["matricule"] == "ZZFN2" for c in pv["candidats"]))
show("le salarie recent n'est pas candidat", not any(c["matricule"] == "ZZFN1" for c in pv["candidats"]))
s, pg = j("POST", "/rgpd/purge", {})
show("purge", s == 200 and pg["count"] >= 1)
s, _ = j("GET", f"/users/{old['id']}")
show("salarie purge introuvable", s == 404)

# Salarie purge AVEC affectation, signature et document (ordre de suppression des tables liees).
s, o3 = j("POST", "/users", {"nom": "Ancien", "prenom": "Affecte", "matricule": "ZZFN3", "statut": "actif"})
s, a3 = j("POST", "/assets", {"type": "PC", "marque": "ZZFN-HP", "numero_serie": "ZZFN-SN3", "statut": "stock"})
s, asg3 = j("POST", "/assignments", {"user_id": o3["id"], "asset_ids": [a3["id"]]})
s, sg3 = j("POST", f"/assignments/{asg3['id']}/sign", SIGN)
j("PUT", f"/users/{o3['id']}", {"nom": "Ancien", "prenom": "Affecte", "matricule": "ZZFN3",
                                 "statut": "sorti", "date_sortie": "2019-01-01"})
s, pg3 = j("POST", "/rgpd/purge", {})
show("purge d'un salarie avec affectation et document", s == 200 and pg3.get("documents_supprimes", 0) >= 1, f"HTTP {s} {pg3}")
s, _ = j("GET", f"/users/{o3['id']}")
show("salarie avec affectation purge introuvable", s == 404)

print("== Import (ecriture reelle) ==")
def upload(kind, content):
    boundary = "----kikanFN"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.csv\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    s, b = call("POST", f"/import/{kind}", token=T, raw=body,
                headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    return s, json.loads(b)
s, r = upload("entites", b"code;nom;code_parent;actif\nZZFN-I1;Import 1;;oui\nZZFN-I2;Import 2;ZZFN-I1;oui\n")
show("import entites", s == 200 and r["imported"] == 2 and not r["errors"], str(r.get("errors")))
s, r = upload("materiel", b"identifiant_interne;type;marque;modele;numero_serie;statut\nZZFN-I-PC;PC;HP;Elite;ZZFN-SN-I;stock\n")
show("import materiel", s == 200 and r["imported"] == 1, str(r.get("errors")))
s, r = upload("materiel", b"identifiant_interne;type;marque;modele;numero_serie;statut\nZZFN-I-PC2;PC;HP;Elite;ZZFN-SN-I;stock\n")
show("doublon de numero de serie rejete", s == 200 and r["imported"] == 0 and len(r["errors"]) == 1)

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
