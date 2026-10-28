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

"""Tests des chartes informatiques deposees (instance de DEVELOPPEMENT).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/policy_check.py

Cree des donnees ZZPOL et des comptes sec_pol* : lancer tests/cleanup_test_data.sql entre deux executions
(les codes d'entite de test doivent etre uniques).
Code de sortie 1 si un test echoue.
"""
import base64
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.generic import DictionaryObject, NameObject, TextStringObject, ArrayObject, NumberObject  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
PW = "Sec-Test-Passw0rd-2026"
fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:140] if detail else ""))


def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def login(user, pw):
    s, b, _ = call("POST", "/auth/login", {"username": user, "password": pw})
    return json.loads(b)["access_token"] if s == 200 else None


ADM = login(ADMIN, ADMIN_PW)
if not ADM:
    sys.exit("Connexion admin impossible")


def j(method, path, body=None, token=None):
    s, b, _ = call(method, path, body, token or ADM)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def upload(filename, content, titre="ZZPOL Charte", entite_id=None, token=None):
    bd = "----kikanPOL"
    parts = []
    def field(n, v):
        parts.append(f'--{bd}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}\r\n'.encode())
    field("titre", titre)
    if entite_id is not None:
        field("entite_id", entite_id)
    parts.append((f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                  "Content-Type: application/octet-stream\r\n\r\n").encode() + content + b"\r\n")
    parts.append(f"--{bd}--\r\n".encode())
    s, b, _ = call("POST", "/policies", token=token or ADM, raw=b"".join(parts),
                   ctype="multipart/form-data; boundary=" + bd)
    try:
        return s, json.loads(b)
    except ValueError:
        return s, b


def make_pdf(pages=2, text="Charte ZZPOL"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(100, 750, f"{text} - page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def hostile_pdf():
    """PDF avec JavaScript a l'ouverture, action sur la page et lien externe (annotation)."""
    base = PdfReader(io.BytesIO(make_pdf(1)))
    w = PdfWriter()
    w.add_page(base.pages[0])
    js = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('x')")})
    w._root_object[NameObject("/OpenAction")] = w._add_object(js)
    link = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(200), NumberObject(200)]),
        NameObject("/A"): w._add_object(DictionaryObject({NameObject("/S"): NameObject("/URI"),
                                                         NameObject("/URI"): TextStringObject("http://evil.example/")}))})
    w.pages[0][NameObject("/Annots")] = ArrayObject([w._add_object(link)])
    w.pages[0][NameObject("/AA")] = DictionaryObject({NameObject("/O"): w._add_object(js)})
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def signature_b64():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIGN = {"consent": True, "signature_image": signature_b64(), "strokes": 4, "duration_ms": 1800}


def ensure_account(name, role):
    s, b, _ = call("POST", "/auth/accounts", {"username": name, "password": PW, "role": role}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": PW}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


print("== Preparation ==")
ids = [ensure_account("sec_polrh", "rh"), ensure_account("sec_pollect", "lecture")]
RH, LECT = login("sec_polrh", PW), login("sec_pollect", PW)
s, grp = j("POST", "/entites", {"code": "ZZPOL-G", "nom": "ZZPOL Groupe"})
s, fil = j("POST", "/entites", {"code": "ZZPOL-F", "nom": "ZZPOL Filiale", "code_parent": "ZZPOL-G"})
s, aut = j("POST", "/entites", {"code": "ZZPOL-A", "nom": "ZZPOL Autre"})
show("entites de test creees", bool(RH and LECT and grp.get("id") and fil.get("id") and aut.get("id")))

print("== Roles ==")
s, _ = upload("c.pdf", make_pdf(), token=RH)
show("RH : depot de charte refuse (403)", s == 403, f"HTTP {s}")
s, _ = upload("c.pdf", make_pdf(), token=LECT)
show("lecture : depot de charte refuse (403)", s == 403, f"HTTP {s}")
s, _ = call("GET", "/policies", token=LECT)[:2]
show("lecture : consultation autorisee", s == 200, f"HTTP {s}")
show("sans jeton : refuse (401)", call("GET", "/policies")[0] == 401)

print("== Fichiers refuses ==")
def refused(name, filename, content, codes=(400,), **kw):
    s, r = upload(filename, content, **kw)
    show(name, s in codes, f"HTTP {s} {r.get('detail') if isinstance(r, dict) else ''}")

refused("fichier vide", "v.pdf", b"")
refused("executable Windows", "c.pdf", b"MZ\x90\x00" + b"\x00" * 100)
refused("fichier binaire sans extension connue", "c.bin", os.urandom(300))
refused("texte sans extension .md", "c.dat", b"# Titre\ntexte")
refused("PDF corrompu (tronque)", "c.pdf", make_pdf()[:200])
refused("faux PDF (en-tete seul)", "c.pdf", b"%PDF-1.7\n" + b"garbage" * 50)
refused("Markdown non UTF-8", "c.md", "caf\xe9 \xe9t\xe9".encode("latin-1"))
refused("Markdown vide", "c.md", b"   \n  ")
refused("fichier trop volumineux (11 Mo)", "c.md", b"a" * (11 * 1024 * 1024), codes=(400, 413))
w = PdfWriter(); w.add_blank_page(200, 200); w.encrypt("secret"); b = io.BytesIO(); w.write(b)
refused("PDF chiffre (mot de passe)", "c.pdf", b.getvalue())
big = PdfWriter()
for _ in range(61):
    big.add_blank_page(200, 200)
bb = io.BytesIO(); big.write(bb)
refused("PDF de 61 pages (plafond 60)", "c.pdf", bb.getvalue())
refused("Word (.docx) : pas encore pris en charge", "c.docx", b"PK\x03\x04" + b"\x00" * 50)
s, _ = upload("c.pdf", make_pdf(), entite_id=999999)
show("entite inconnue -> 404", s == 404, f"HTTP {s}")
s, lst = j("GET", "/policies")
show("aucun fichier refuse n'a cree de charte", not any(p["titre"] == "ZZPOL Charte" for p in lst) if s == 200 else False)

print("== PDF hostile assaini ==")
s, p_h = upload("hostile.pdf", hostile_pdf(), titre="ZZPOL Hostile", entite_id=aut["id"])
show("PDF avec JavaScript, action et lien : accepte apres nettoyage", s == 201, f"HTTP {s} {p_h if s != 201 else ''}")
s, clean, _ = call("GET", f"/policies/{p_h['id']}/fichier", token=ADM)
show("PDF normalise : plus de JavaScript, d'action ni de lien",
     s == 200 and all(m not in clean for m in (b"JavaScript", b"/OpenAction", b"/AA", b"evil.example", b"/Annots")),
     f"{len(clean)} octets")
s, src, _ = call("GET", f"/policies/{p_h['id']}/source", token=ADM)
show("fichier d'origine conserve tel quel (telechargeable)", s == 200 and b"JavaScript" in src)

print("== Markdown ==")
md = ("# Charte informatique ZZPOL\n\n## 1. Principes\n\nTexte avec **gras** et *italique* et <script>alert(1)</script> "
      "et <b>balise</b>.\n\n- poste de travail\n- messagerie\n\n1. Premier\n2. Second\n").encode()
s, p_md = upload("charte.md", md, titre="ZZPOL Markdown", entite_id=aut["id"])
show("Markdown accepte", s == 201 and p_md.get("format_source") == "markdown" and p_md["nb_pages"] == 1, f"HTTP {s} {p_md if s != 201 else ''}")
s, mdpdf, _ = call("GET", f"/policies/{p_md['id']}/fichier", token=ADM)
text = PdfReader(io.BytesIO(mdpdf)).pages[0].extract_text()
show("rendu Markdown : titres, listes et gras, balises HTML rendues en texte inerte",
     "Principes" in text and "poste de travail" in text and "<script>" in text and "gras" in text, text[:90].replace("\n", " / "))
show("rendu Markdown : aucun script actif dans le PDF", b"JavaScript" not in mdpdf and b"/JS" not in mdpdf)

print("== Portees, versions et archivage ==")
s, g1 = upload("g.pdf", make_pdf(2, "Charte globale v1"), titre="ZZPOL Globale")
show("depot d'une charte globale", s == 201 and g1["entite_id"] is None and g1["version"].startswith("v") and g1["nb_pages"] == 2
     and g1["statut"] == "active" and g1["portee"].startswith("Globale"), g1 if s != 201 else "")
s, g2 = upload("g2.pdf", make_pdf(3, "Charte globale v2"), titre="ZZPOL Globale")
s, lst = j("GET", "/policies")
old = next(p for p in lst if p["id"] == g1["id"])
show("nouvelle version : numero suivant active, precedente archivee automatiquement",
     int(g2["version"][1:]) == int(g1["version"][1:]) + 1 and old["statut"] == "archivee"
     and sum(1 for p in lst if p["entite_id"] is None and p["statut"] == "active") == 1)
s, f1 = upload("f.pdf", make_pdf(1, "Charte filiale"), titre="ZZPOL Filiale", entite_id=fil["id"])
show("depot d'une charte propre a une entite", s == 201 and f1["entite_id"] == fil["id"] and f1["version"].startswith("v") and "ZZPOL Filiale" in f1["portee"])
s, lst = j("GET", "/policies")
show("la charte globale reste active (portees independantes)", next(p for p in lst if p["id"] == g2["id"])["statut"] == "active")

def applicable(eid):
    s, r = j("GET", "/policies/applicable" + (f"?entite_id={eid}" if eid is not None else ""))
    return r["id"] if s == 200 and r else None

show("entite avec sa propre charte -> la sienne", applicable(fil["id"]) == f1["id"])
show("charte Markdown deposee apres le PDF : seule la derniere est active", applicable(aut["id"]) == p_md["id"]
     and next(p for p in j("GET", "/policies")[1] if p["id"] == p_h["id"])["statut"] == "archivee")
s, p_md2 = j("POST", f"/policies/{p_md['id']}/archiver")
show("archivage manuel", s == 200 and p_md2["statut"] == "archivee", f"HTTP {s}")
show("charte archivee : l'entite retombe sur la charte globale", applicable(aut["id"]) == g2["id"])
s, r = j("POST", f"/policies/{p_md['id']}/archiver")
show("double archivage -> 409", s == 409, f"HTTP {s}")
show("sans entite -> charte globale", applicable(None) == g2["id"])
# heritage : sous-entite sans charte propre -> parent, sinon globale
s, sub = j("POST", "/entites", {"code": "ZZPOL-S", "nom": "ZZPOL Sous-filiale", "code_parent": "ZZPOL-F"})
show("sous-entite sans charte propre -> charte de l'entite parente", applicable(sub["id"]) == f1["id"])

print("== Apercu et telechargement ==")
s, png, h = call("GET", f"/policies/{g2['id']}/page/1", token=ADM)
show("apercu de la page 1 (PNG)", s == 200 and png[:8] == b"\x89PNG\r\n\x1a\n" and h.get("Content-Type") == "image/png", f"{len(png)} octets")
show("apercu page 3 sur 3", call("GET", f"/policies/{g2['id']}/page/3", token=ADM)[0] == 200)
show("page 4 inexistante -> 404", call("GET", f"/policies/{g2['id']}/page/4", token=ADM)[0] == 404)
show("page 0 -> 404", call("GET", f"/policies/{g2['id']}/page/0", token=ADM)[0] == 404)
show("charte inconnue -> 404", call("GET", "/policies/999999/fichier", token=ADM)[0] == 404)
show("lecture : apercu autorise", call("GET", f"/policies/{g2['id']}/page/1", token=LECT)[0] == 200)
s, pdf2, _ = call("GET", f"/policies/{g2['id']}/fichier", token=ADM)
show("PDF normalise : empreinte enregistree correcte", hashlib.sha256(pdf2).hexdigest() == g2["sha256"] and len(PdfReader(io.BytesIO(pdf2)).pages) == 3)

print("== Rattachement automatique a la remise ==")
def new_user_asset(entite_id, tag):
    s, u = j("POST", "/users", {"prenom": "Pol", "nom": tag, "matricule": "ZZPOL-" + tag, "statut": "actif", "entite_id": entite_id})
    s, a = j("POST", "/assets", {"type": "PC", "marque": "ZZPOL", "modele": "M", "numero_serie": "ZZPOL-" + tag, "statut": "stock"})
    return u, a

u1, a1 = new_user_asset(fil["id"], "F1")
s, asg1 = j("POST", "/assignments", {"user_id": u1["id"], "asset_ids": [a1["id"]]})
show("remise : la charte de l'entite est jointe d'office", s == 201 and asg1["policy_id"] == f1["id"], asg1.get("policy_id"))
u2, a2 = new_user_asset(None, "G1")
s, asg2 = j("POST", "/assignments", {"user_id": u2["id"], "asset_ids": [a2["id"]]})
show("remise sans entite : charte globale jointe d'office", asg2["policy_id"] == g2["id"])
u3, a3 = new_user_asset(fil["id"], "N1")
s, asg3 = j("POST", "/assignments", {"user_id": u3["id"], "asset_ids": [a3["id"]], "sans_charte": True})
show("option 'aucune charte' respectee", s == 201 and asg3["policy_id"] is None)
u4, a4 = new_user_asset(fil["id"], "C1")
s, asg4 = j("POST", "/assignments", {"user_id": u4["id"], "asset_ids": [a4["id"]], "policy_id": g2["id"]})
show("choix explicite d'une autre charte active", s == 201 and asg4["policy_id"] == g2["id"])
u5, a5 = new_user_asset(fil["id"], "A1")
s, r = j("POST", "/assignments", {"user_id": u5["id"], "asset_ids": [a5["id"]], "policy_id": g1["id"]})
show("charte archivee refusee", s == 400, f"HTTP {s}")
s, r = j("POST", "/assignments", {"user_id": u5["id"], "asset_ids": [a5["id"]], "policy_id": 999999})
show("charte inconnue refusee", s == 400, f"HTTP {s}")
s, rc = j("GET", f"/assignments/{asg1['id']}/recap")
show("recap : charte (titre, version, pages, empreinte)", s == 200 and rc["charte"]["id"] == f1["id"] and rc["charte"]["nb_pages"] == 1
     and rc["charte"]["sha256"] == f1["sha256"])

print("== Signature avec charte en annexe ==")
s, sig = j("POST", f"/assignments/{asg1['id']}/sign", SIGN)
show("signature acceptee", s == 201, f"HTTP {s} {sig if s != 201 else ''}")
s, pdf, _ = call("GET", f"/assignments/{asg1['id']}/document", token=ADM)
rd = PdfReader(io.BytesIO(pdf))
show("PDF signe = accuse (1 page) + charte annexee (1 page)", len(rd.pages) == 2, len(rd.pages))
show("le texte de la charte figure dans le document signe", "Charte filiale" in rd.pages[1].extract_text())
show("l'accuse cite la version et l'empreinte de la charte", f1["sha256"][:8] in rd.pages[0].extract_text().replace("\n", " ").replace(" ", ""))
aj = sig["audit_json"]["charte"]
show("preuve en base : charte (id, version, empreinte, entite)", aj["id"] == f1["id"] and aj["version"] == f1["version"]
     and aj["sha256"] == f1["sha256"] and aj["entite_id"] == fil["id"], aj)
try:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    st = validate_pdf_signature(PdfFileReader(io.BytesIO(pdf)).embedded_signatures[0])
    show("scellement PAdES intact sur le document complet", st.intact and st.valid)
except Exception as exc:  # noqa: BLE001
    show("scellement PAdES", False, str(exc)[:90])
s, rc = j("GET", f"/assignments/{asg3['id']}/recap")
show("recap sans charte : aucune charte", rc["charte"] is None)
s, sig3 = j("POST", f"/assignments/{asg3['id']}/sign", SIGN)
s, pdf3, _ = call("GET", f"/assignments/{asg3['id']}/document", token=ADM)
show("remise sans charte : 1 seule page, pas d'annexe", len(PdfReader(io.BytesIO(pdf3)).pages) == 1 and sig3["audit_json"]["charte"] is None)

print("== Nouvelle version : les documents deja signes ne changent pas ==")
s, f2 = upload("f2.pdf", make_pdf(1, "Charte filiale NOUVELLE"), titre="ZZPOL Filiale", entite_id=fil["id"])
s, pdf_again, _ = call("GET", f"/assignments/{asg1['id']}/document", token=ADM)
show("document signe avec v1 inchange apres le depot de v2", hashlib.sha256(pdf_again).hexdigest() == sig["empreinte_doc"])
show("nouvelle version de la filiale : active, la precedente archivee", int(f2["version"][1:]) == int(f1["version"][1:]) + 1
     and applicable(fil["id"]) == f2["id"])
u6, a6 = new_user_asset(fil["id"], "F2")
s, asg6 = j("POST", "/assignments", {"user_id": u6["id"], "asset_ids": [a6["id"]]})
show("nouvelles remises : joignent la v2", asg6["policy_id"] == f2["id"])

print("== Alteration du stockage ==")
path = f"/archive/chartes/{f2['id']}/charte.pdf"
orig = open(path, "rb").read()
open(path, "wb").write(orig + b"\n%altere")
s, _, _ = call("GET", f"/policies/{f2['id']}/page/1", token=ADM)
show("apercu d'une charte alteree -> refuse (500)", s == 500, f"HTTP {s}")
s, r = j("POST", f"/assignments/{asg6['id']}/sign", SIGN)
show("signature avec une charte alteree -> refusee", s == 500 and "Integrite" in str(r), f"HTTP {s}")
open(path, "wb").write(orig)
s, r = j("POST", f"/assignments/{asg6['id']}/sign", SIGN)
show("charte restauree : signature possible", s == 201, f"HTTP {s}")

for aid in ids:
    call("PUT", f"/auth/accounts/{aid}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
