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

"""Tests du parametrage : types, services, fusion marques/modeles, modele de PDF, etat du scellement.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/parametres_check.py

Cree des donnees ZZPA et des comptes sec_pa* ; remet le modele de PDF a zero a la fin
(nettoyage : tests/cleanup_test_data.sql). Ce fichier reste en ASCII (independant du lanceur).
Code de sortie 1 si un test echoue.
"""
import base64
import hashlib
import io
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

sys.path.insert(0, "/app")
from PIL import Image, ImageDraw  # noqa: E402
from PIL.PngImagePlugin import PngInfo  # noqa: E402
from pypdf import PdfReader  # noqa: E402

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
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=h)
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


def msg(r):
    return r.get("detail", "") if isinstance(r, dict) else str(r)


def ensure_account(name, role):
    s, b, _ = call("POST", "/auth/accounts", {"username": name, "password": PW, "role": role, "portee_globale": True}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": PW, "portee_globale": True}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


def png(w, h, color=(30, 90, 160, 255), meta=None, fmt="PNG"):
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    ImageDraw.Draw(img).rectangle([0, 0, w - 1, h - 1], fill=color)
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG")
    elif meta:
        info = PngInfo()
        for k, v in meta.items():
            info.add_text(k, v)
        img.save(buf, "PNG", pnginfo=info)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def data_url(raw, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def bomb_png(width, height):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


def sign_payload():
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"consent": True, "signature_image": data_url(buf.getvalue()), "strokes": 4, "duration_ms": 1800}


def pdf_text(pdf_bytes):
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


ids = [ensure_account("sec_parh", "rh"), ensure_account("sec_palect", "lecture")]
RH, LECT = login("sec_parh", PW), login("sec_palect", PW)

print("== Roles ==")
for name, tok in (("RH", RH), ("lecture", LECT)):
    for path in ("/parametres/types", "/parametres/services", "/parametres/marques", "/parametres/pdf", "/parametres/etat"):
        show(f"{name} : GET {path} refuse (403)", call("GET", path, token=tok)[0] == 403)
    show(f"{name} : creation de type refusee (403)", call("POST", "/parametres/types", {"nom": "ZZPA-x"}, tok)[0] == 403)
    show(f"{name} : fusion refusee (403)", call("POST", "/parametres/marques/fusion", {"sources": ["a"], "cible": "b"}, tok)[0] == 403)
show("sans jeton : refuse (401)", call("GET", "/parametres/types")[0] == 401)
show("menus : types lisibles par tous les roles", call("GET", "/assets/catalogue/types", token=LECT)[0] == 200)
show("menus : services lisibles par tous les roles", call("GET", "/users/catalogue/services", token=RH)[0] == 200)

print("== Types d'actifs ==")
s, t1 = j("POST", "/parametres/types", {"nom": "ZZPA-Laptop"})
show("creation", s == 201 and t1["nom"] == "ZZPA-Laptop" and t1["utilise"] == 0, msg(t1))
s, r = j("POST", "/parametres/types", {"nom": "zzpa-laptop"})
show("doublon (casse differente) -> 409", s == 409, msg(r))
s, r = j("POST", "/parametres/types", {"nom": "   "})
show("nom vide -> 400", s == 400)
s, r = j("POST", "/parametres/types", {"nom": "x" * 101})
show("nom trop long -> 422", s == 422)
s, r = j("POST", "/parametres/types", {"nom": "  ZZPA   Ecran   large "})
show("espaces normalises", s == 201 and r["nom"] == "ZZPA Ecran large", msg(r))
s, t2 = j("GET", "/parametres/types")
show("liste avec compteur d'usage", s == 200 and any(x["nom"] == "ZZPA-Laptop" and x["utilise"] == 0 for x in t2))
a = {"marque": "ZZPA-Dell", "modele": "L1", "numero_serie": "ZZPA-SN1", "statut": "stock", "type": "zzpa-laptop"}
s, a1 = j("POST", "/assets", a)
show("un type saisi a la casse pres reprend la graphie de la liste", s == 201 and a1["type"] == "ZZPA-Laptop", a1.get("type"))
s, a2 = j("POST", "/assets", {**a, "numero_serie": "ZZPA-SN2", "type": "ZZPA-Nouveau"})
s, lst = j("GET", "/parametres/types")
show("liste souple : un type nouveau est ajoute a la liste (rien n'est refuse)", s == 201 or a2.get("type") == "ZZPA-Nouveau"
     and any(x["nom"] == "ZZPA-Nouveau" for x in lst))
s, r = j("DELETE", f"/parametres/types/{t1['id']}")
show("suppression d'un type utilise -> 409", s == 409 and "actif(s)" in msg(r) and "Desactivez" in msg(r), msg(r))
s, r = j("PUT", f"/parametres/types/{t1['id']}", {"nom": "ZZPA-Portable", "actif": True})
s, chk = j("GET", f"/assets/{a1['id']}")
show("renommage propage aux actifs", s == 200 and r.get("mis_a_jour") == 1 and chk["type"] == "ZZPA-Portable", msg(r))
s, r = j("PUT", f"/parametres/types/{t1['id']}", {"nom": "zzpa-nouveau", "actif": True})
show("renommer vers un nom deja pris -> 409", s == 409)
s, r = j("PUT", f"/parametres/types/{t1['id']}", {"nom": "ZZPA-Portable", "actif": False})
s, cat = j("GET", "/assets/catalogue/types")
show("type desactive : absent des menus, toujours en liste", r.get("actif") is False and "ZZPA-Portable" not in cat)
s, r = j("PUT", f"/assets/{a1['id']}", {**{k: chk[k] for k in ("identifiant_interne", "marque", "modele", "numero_serie", "statut",
     "entite_id", "notes", "date_achat", "fin_garantie", "echeance_renouvellement", "source", "id_externe")}, "type": "ZZPA-Portable", "marque": "ZZPA-Dell2"})
show("un actif garde son type desactive (modification possible)", s == 200 and r["type"] == "ZZPA-Portable", msg(r))
s, free = j("POST", "/parametres/types", {"nom": "ZZPA-Libre"})
s, r = j("DELETE", f"/parametres/types/{free['id']}")
show("suppression d'un type inutilise (204)", s == 204)
show("type inconnu -> 404", j("DELETE", "/parametres/types/999999")[0] == 404 and j("PUT", "/parametres/types/999999", {"nom": "x"})[0] == 404)

print("== Services ==")
s, sv = j("POST", "/parametres/services", {"nom": "ZZPA-Compta"})
show("creation", s == 201 and sv["utilise"] == 0)
s, r = j("POST", "/parametres/services", {"nom": "ZZPA-COMPTA"})
show("doublon -> 409", s == 409)
s, u = j("POST", "/users", {"prenom": "Pa", "nom": "Test", "matricule": "ZZPA-U1", "statut": "actif", "service": "zzpa-compta"}, RH)
show("RH : un service saisi a la casse pres reprend la graphie de la liste", s == 201 and u["service"] == "ZZPA-Compta", u.get("service"))
s, u2 = j("POST", "/users", {"prenom": "Pb", "nom": "Test", "matricule": "ZZPA-U2", "statut": "actif", "service": "ZZPA-Neuf"}, RH)
s, lst = j("GET", "/parametres/services")
show("liste souple : un service nouveau est ajoute", any(x["nom"] == "ZZPA-Neuf" for x in lst))
s, r = j("DELETE", f"/parametres/services/{sv['id']}")
show("suppression d'un service utilise -> 409", s == 409 and "salarie(s)" in msg(r), msg(r))
s, r = j("PUT", f"/parametres/services/{sv['id']}", {"nom": "ZZPA-Comptabilite", "actif": True})
s, chk = j("GET", f"/users/{u['id']}")
show("renommage propage aux salaries", r.get("mis_a_jour") == 1 and chk["service"] == "ZZPA-Comptabilite", msg(r))
s, cat = j("GET", "/users/catalogue/services", token=LECT)
show("menu des services", "ZZPA-Comptabilite" in cat)

print("== Import : listes souples, simulation sans effet ==")
def post_import(kind, content, query=""):
    bd = "----kikanPA"
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\nContent-Type: text/csv\r\n\r\n').encode() + content + f"\r\n--{bd}--\r\n".encode()
    req = urllib.request.Request(B + f"/import/{kind}{query}", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + ADM, "Content-Type": "multipart/form-data; boundary=" + bd})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

csv_mat = b"identifiant_interne;type;marque;modele;numero_serie;statut\nZZPA-I1;zzpa-importe;ZZPA-HP;E;ZZPA-SN9;stock\n"
post_import("materiel", csv_mat, "?dry_run=true")
show("simulation : aucun type ajoute", not any(x["nom"].lower() == "zzpa-importe" for x in j("GET", "/parametres/types")[1]))
post_import("materiel", csv_mat)
show("import reel : type ajoute a la liste", any(x["nom"].lower() == "zzpa-importe" for x in j("GET", "/parametres/types")[1]))
csv_usr = b"matricule;nom;prenom;service\nZZPA-U3;Imp;Orte;zzpa-comptabilite\n"
post_import("utilisateurs", csv_usr)
s, lu = j("GET", "/users?q=ZZPA-U3")
show("import : service rattache a la graphie de la liste", s == 200 and lu and lu[0]["service"] == "ZZPA-Comptabilite", lu[0]["service"] if lu else None)

print("== Fusion des marques et modeles ==")
# Variantes "historiques" inserees directement en base : depuis A8 le formulaire et l'API les normalisent.
from sqlmodel import Session as _Session  # noqa: E402
from app.db import engine as _engine  # noqa: E402
from app.models import Asset as _Asset  # noqa: E402
with _Session(_engine) as _ses:
    for i, m in enumerate(("ZZPA-dell", "ZZPA-DELL", "ZZPA-DELL", "ZZPA Dell Technologies")):
        _ses.add(_Asset(marque=m, modele="Latitude" if i < 2 else "LATITUDE", numero_serie=f"ZZPA-M{i}", statut="stock"))
    _ses.commit()
s, mq = j("GET", "/parametres/marques")
counts = {x["nom"]: x["count"] for x in mq}
show("liste des marques avec effectifs", counts.get("ZZPA-dell") == 1 and counts.get("ZZPA-DELL") == 2 and counts.get("ZZPA Dell Technologies") == 1, counts)
src = ["ZZPA-dell", "ZZPA-DELL", "ZZPA Dell Technologies"]
s, ap = j("POST", "/parametres/marques/fusion", {"sources": src, "cible": "ZZPA-Dell", "apercu": True})
show("apercu : nombre de materiels touches, sans ecrire", s == 200 and ap["apercu"] and ap["materiels"] == 4, ap)
show("apercu : rien n'a change", {x["nom"]: x["count"] for x in j("GET", "/parametres/marques")[1]}.get("ZZPA-DELL") == 2)
s, r = j("POST", "/parametres/marques/fusion", {"sources": src, "cible": "ZZPA-Dell"})
mq2 = {x["nom"]: x["count"] for x in j("GET", "/parametres/marques")[1]}
show("fusion : toutes les variantes vers le nom retenu", s == 200 and r["materiels"] == 4 and mq2.get("ZZPA-Dell") == 5
     and "ZZPA-dell" not in mq2 and "ZZPA-DELL" not in mq2, mq2)
s, r = j("POST", "/parametres/marques/fusion", {"sources": [], "cible": "x"})
show("sources vides -> 422", s == 422)
s, r = j("POST", "/parametres/marques/fusion", {"sources": ["ZZPA-Dell"], "cible": "  "})
show("cible vide -> 400", s == 400)
s, md = j("GET", "/parametres/modeles?marque=ZZPA-Dell")
mc = {x["nom"]: x["count"] for x in md}
show("modeles d'une marque avec effectifs", mc.get("Latitude") == 2 and mc.get("LATITUDE") == 2, mc)
s, r = j("POST", "/parametres/modeles/fusion", {"sources": ["LATITUDE"], "cible": "Latitude"})
show("fusion de modeles sans marque -> 400", s == 400)
s, r = j("POST", "/parametres/modeles/fusion", {"sources": ["LATITUDE"], "cible": "Latitude", "marque": "ZZPA-Dell"})
mc2 = {x["nom"]: x["count"] for x in j("GET", "/parametres/modeles?marque=ZZPA-Dell")[1]}
show("fusion de modeles", s == 200 and mc2 == {"L1": 1, "Latitude": 4}, mc2)
s, other = j("GET", "/parametres/modeles?marque=ZZPA-Dell2")
show("la fusion ne touche que la marque indiquee", [x["nom"] for x in other] == ["L1"], other)
show("modeles sans parametre marque -> 422", j("GET", "/parametres/modeles")[0] == 422)

print("== Modele de PDF : textes ==")
s, d0 = j("GET", "/parametres/pdf")
show("modele initial vide", s == 200 and d0["logo"] is False and d0["organisation"] == "" and len(d0["sha256"]) == 64, d0)
org = "ZZPA Organisation <b>SA</b>"
mentions = "Document etabli par ZZPA.\nMention <i>legale</i> ligne 2."
pied = "ZZPA - 1 rue de l'Exemple - 44000 Nantes"
s, d1 = j("PUT", "/parametres/pdf", {"organisation": org, "mentions": mentions, "pied": pied})
show("enregistrement des textes", s == 200 and d1["organisation"] == org and d1["sha256"] != d0["sha256"], msg(d1))
s, r = j("PUT", "/parametres/pdf", {"organisation": "x", "mentions": "m" * 1501, "pied": ""})
show("mentions trop longues -> 422", s == 422)
s, r = j("PUT", "/parametres/pdf", {"organisation": "o" * 121})
show("organisation trop longue -> 422", s == 422)
s, r = j("PUT", "/parametres/pdf", {"organisation": org + "\x00\x07", "mentions": mentions, "pied": pied})
show("caracteres de controle retires", s == 200 and r["organisation"] == org and r["sha256"] == d1["sha256"], msg(r))

print("== Modele de PDF : logo (image non fiable) ==")
def logo(raw, mime="image/png"):
    return j("POST", "/parametres/pdf/logo", {"image": data_url(raw, mime)})

def refused(name, raw, mime="image/png", codes=(400, 422)):
    s, r = logo(raw, mime)
    show(name, s in codes, f"HTTP {s} {msg(r)}")

refused("GIF refuse", b"GIF89a" + b"\x00" * 50, "image/gif")
refused("SVG refuse", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml")
refused("PNG corrompu", png(300, 100)[:120])
refused("faux PNG (octets quelconques)", b"\x89PNG\r\n\x1a\n" + os.urandom(200))
refused("PNG deguise en JPEG (type MIME incoherent)", png(300, 100), "image/gif")
refused("dimensions trop grandes (1200 x 500)", png(1200, 500))
refused("dimensions trop petites (8 x 8)", png(8, 8))
noise = Image.frombytes("RGB", (600, 300), os.urandom(600 * 300 * 3))
nb = io.BytesIO(); noise.save(nb, "PNG")
refused("fichier de plus de 300 Ko", nb.getvalue())
refused("chaine geante (500 000 caracteres)", b"A" * 400_000)
t0 = time.time()
refused("bombe de decompression (en-tete 40000 x 40000)", bomb_png(40000, 40000))
show("   ... refusee rapidement", time.time() - t0 < 5, f"{time.time() - t0:.2f} s")
s, r = j("POST", "/parametres/pdf/logo", {"image": "pas du base64 !!"})
show("base64 invalide", s == 400, msg(r))
s, ok = logo(png(400, 120, meta={"Auteur": "SECRET-META-ZZPA"}))
show("PNG valide accepte", s == 200 and ok["largeur"] == 400 and ok["hauteur"] == 120, msg(ok))
s, got, h = call("GET", "/parametres/pdf/logo", token=ADM)
im = Image.open(io.BytesIO(got))
show("logo servi : PNG propre, metadonnees supprimees", s == 200 and h.get("Content-Type") == "image/png" and b"SECRET-META-ZZPA" not in got
     and "Auteur" not in im.info, f"{len(got)} octets")
s, ok2 = logo(png(300, 90, fmt="JPEG"), "image/jpeg")
show("JPEG valide accepte (converti en PNG)", s == 200, msg(ok2))
s, got2, _ = call("GET", "/parametres/pdf/logo", token=ADM)
show("logo JPEG re-encode en PNG", got2[:8] == b"\x89PNG\r\n\x1a\n")
s, d2 = j("GET", "/parametres/pdf")
show("modele : logo present, empreinte changee", d2["logo"] is True and d2["sha256"] != d1["sha256"])

print("== Modele de PDF : apercu et documents ==")
s, pv, h = call("GET", "/parametres/pdf/apercu?format=png", token=ADM)
show("apercu PNG", s == 200 and pv[:8] == b"\x89PNG\r\n\x1a\n" and h.get("Content-Type") == "image/png", f"{len(pv)} octets")
s, pdf, _ = call("GET", "/parametres/pdf/apercu?format=pdf", token=ADM)
txt = pdf_text(pdf)
show("apercu PDF : organisation, mentions et pied de page", "ZZPA Organisation" in txt and "Mention" in txt and "1 rue de l" in txt, txt[:80].replace("\n", " / "))
show("apercu PDF : texte HTML rendu tel quel (inerte)", "<b>SA</b>" in txt and "<i>legale</i>" in txt)
show("apercu PDF : logo present (image)", pdf.count(b"/Subtype /Image") >= 1)
show("apercu : marque factice, non signe", "Apercu" in txt and b"/ByteRange" not in pdf)
j("PUT", "/parametres/pdf", {"organisation": "ZZPA " + chr(0x2605) + " " + chr(0x1F600) + " emoji", "mentions": "", "pied": "pied " + chr(0x4E2D) + chr(0x6587)})
s, pdf3, _ = call("GET", "/parametres/pdf/apercu?format=pdf", token=ADM)
show("caracteres hors alphabet latin : pas d'erreur 500", s == 200 and pdf3[:4] == b"%PDF", f"HTTP {s}")
j("PUT", "/parametres/pdf", {"organisation": org, "mentions": mentions, "pied": pied})

s, ent = j("POST", "/entites", {"code": "ZZPA-E", "nom": "ZZPA Entite"})
s, usr = j("POST", "/users", {"prenom": "Sig", "nom": "Nataire", "matricule": "ZZPA-U9", "statut": "actif", "entite_id": ent["id"]})
s, ass = j("POST", "/assets", {"type": "PC", "marque": "ZZPA-HP", "modele": "E", "numero_serie": "ZZPA-SN7", "statut": "stock"})
s, asg = j("POST", "/assignments", {"user_id": usr["id"], "asset_ids": [ass["id"]], "sans_charte": True})
s, tpl = j("GET", "/parametres/pdf")
s, sig = j("POST", f"/assignments/{asg['id']}/sign", sign_payload())
show("signature avec le modele", s == 201, msg(sig))
s, sealed, _ = call("GET", f"/assignments/{asg['id']}/document", token=ADM)
st = pdf_text(sealed)
show("accuse signe : organisation, mentions, pied de page", "ZZPA Organisation" in st and "Mention" in st and "1 rue de l" in st)
show("accuse signe : logo present", sealed.count(b"/Subtype /Image") >= 2)  # logo + signature manuscrite
mp = (sig["audit_json"] or {}).get("modele_pdf") or {}
show("preuve : empreinte du modele enregistree avec la signature", mp.get("sha256") == tpl["sha256"] and mp.get("logo") is True, mp)
h_before = hashlib.sha256(sealed).hexdigest()
j("PUT", "/parametres/pdf", {"organisation": "ZZPA Nouvelle Marque", "mentions": "", "pied": ""})
s, sealed2, _ = call("GET", f"/assignments/{asg['id']}/document", token=ADM)
show("changer le modele ne modifie pas un document deja signe", hashlib.sha256(sealed2).hexdigest() == h_before == sig["empreinte_doc"])
s, ass2 = j("POST", "/assets", {"type": "PC", "marque": "ZZPA-HP", "modele": "E", "numero_serie": "ZZPA-SN8", "statut": "stock"})
s, usr2 = j("POST", "/users", {"prenom": "Sig", "nom": "Deux", "matricule": "ZZPA-U8", "statut": "actif"})
s, asg2 = j("POST", "/assignments", {"user_id": usr2["id"], "asset_ids": [ass2["id"]], "sans_charte": True})
s, sig2 = j("POST", f"/assignments/{asg2['id']}/sign", sign_payload())
s, pd2, _ = call("GET", f"/assignments/{asg2['id']}/document", token=ADM)
show("remise suivante : nouveau modele et nouvelle empreinte", "ZZPA Nouvelle Marque" in pdf_text(pd2) and (sig2["audit_json"]["modele_pdf"] or {}).get("sha256") != mp.get("sha256"))
s, rep, _ = call("GET", "/reports/holdings?format=pdf", token=ADM)
show("rapport PDF : organisation en en-tete", s == 200 and "ZZPA Nouvelle Marque" in pdf_text(rep))
call("DELETE", "/parametres/pdf/logo", token=ADM)
j("PUT", "/parametres/pdf", {"organisation": "", "mentions": "", "pied": ""})
s, tpl0 = j("GET", "/parametres/pdf")
show("modele remis a zero : vide", tpl0["logo"] is False and tpl0["organisation"] == "" and tpl0["sha256"] == d0["sha256"])
s, ass3 = j("POST", "/assets", {"type": "PC", "marque": "ZZPA-HP", "modele": "E", "numero_serie": "ZZPA-SN6", "statut": "stock"})
s, usr3 = j("POST", "/users", {"prenom": "Sig", "nom": "Trois", "matricule": "ZZPA-U7", "statut": "actif"})
s, asg3 = j("POST", "/assignments", {"user_id": usr3["id"], "asset_ids": [ass3["id"]], "sans_charte": True})
s, sig3 = j("POST", f"/assignments/{asg3['id']}/sign", sign_payload())
show("modele vide : signature normale, aucune empreinte de modele", s == 201 and sig3["audit_json"]["modele_pdf"] is None)

print("== Etat du scellement ==")
s, et = j("GET", "/parametres/etat")
c = et.get("certificat", {})
show("certificat : sujet, validite, empreinte", s == 200 and c.get("sujet") and c.get("valide_au") and len(c.get("empreinte_sha256", "")) == 64
     and c.get("jours_restants", 0) > 0, c)
show("etat : signature manuscrite, stockage, limites", et["signature_manuscrite_obligatoire"] is True and et["stockage"] in ("local", "smb", "webdav")
     and et["limites"]["import_mo"] >= 1 and et["limites"]["charte_pages"] == 60, et)
show("la cle privee n'est jamais exposee", "PRIVATE" not in json.dumps(et) and "key" not in json.dumps(et).lower())

print("== Journal d'audit ==")
s, log = j("GET", "/audit?limit=500")
acts = [x for x in log if x["action"] in ("parametrage", "fusion_marques", "fusion_modeles", "modification")]
show("parametrage et fusions journalises", {"parametrage", "fusion_marques", "fusion_modeles"} <= {x["action"] for x in acts}, sorted({x["action"] for x in acts}))
alltext = " ".join((x.get("detail") or "") for x in log)
show("journal : jamais le contenu du logo ni les metadonnees", "SECRET-META-ZZPA" not in alltext and "iVBOR" not in alltext)
show("journal : empreinte du logo (tronquee) seulement", any("logo :" in (x.get("detail") or "") and "sha256=" in (x.get("detail") or "") for x in log))

for aid in ids:
    call("PUT", f"/auth/accounts/{aid}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
