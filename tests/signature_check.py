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

"""Tests de la signature manuscrite a l'ecran (remise et restitution), instance de DEVELOPPEMENT.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/signature_check.py

Cree des donnees ZZSG et un compte sec_sigrh (nettoyage : tests/cleanup_test_data.sql).
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

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "")
RH_PW = "Sec-Test-Passw0rd-2026"
fails = 0


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


# --- Fabrication d'images de test ---

def png_bytes(img, **save):
    buf = io.BytesIO()
    img.save(buf, "PNG", **save)
    return buf.getvalue()


def data_url(raw, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def good_image(w=1000, h=400, meta=None):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    if meta:
        info = PngInfo()
        for k, v in meta.items():
            info.add_text(k, v)
        return png_bytes(img, pnginfo=info)
    return png_bytes(img)


def bomb_png(width, height):
    """PNG dont l'en-tete annonce de tres grandes dimensions (pixels jamais fournis)."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


GOOD = good_image()
SIGN_OK = {"consent": True, "signature_image": data_url(GOOD), "strokes": 4, "duration_ms": 1800}


def ensure_account(name, role):
    s, b = call("POST", "/auth/accounts", {"username": name, "password": RH_PW, "role": role}, ADM)
    if s == 409:
        accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
        acc = next(a for a in accs if a["username"] == name)
        call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": role, "password": RH_PW}, ADM)
        return acc["id"]
    return json.loads(b)["id"]


def new_assignment(prenom, nom, matricule, serial, **user_extra):
    s, u = j("POST", "/users", {"prenom": prenom, "nom": nom, "matricule": matricule, "statut": "actif", **user_extra})
    s, a = j("POST", "/assets", {"type": "PC", "marque": "ZZSG", "modele": "M1", "numero_serie": serial, "statut": "stock"})
    s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]]})
    return u, a, asg


print("== Preparation ==")
rh_id = ensure_account("sec_sigrh", "rh")
RH = login("sec_sigrh", RH_PW)
u, asset, asg = new_assignment("Marie", "Signature", "ZZSG1", "ZZSG-SN1", service="Compta")
show("donnees de test creees", bool(u and asset and asg and RH), f"affectation={asg.get('id')}")
SIGN_URL = f"/assignments/{asg['id']}/sign"

print("== Recapitulatif affiche sur la tablette ==")
s, rc = j("GET", f"/assignments/{asg['id']}/recap")
show("recap de la remise", s == 200 and rc["salarie"]["nom"] == "Signature" and len(rc["materiel"]) == 1
     and rc["signature_obligatoire"] is True and rc["deja_signe"] is False, rc if s != 200 else "")
s, _ = j("GET", "/assignments/999999/recap")
show("recap d'une affectation inconnue -> 404", s == 404, f"HTTP {s}")

print("== Refus : acceptation, image absente ou invalide ==")
def refused(name, body, expected=(400,), token=None, url=SIGN_URL):
    s, r = j("POST", url, body, token)
    show(name, s in expected, f"HTTP {s} {r.get('detail') if isinstance(r, dict) else ''}")

refused("sans acceptation (consent=false)", {**SIGN_OK, "consent": False})
refused("sans image alors que la signature manuscrite est obligatoire", {"consent": True})
refused("base64 invalide", {"consent": True, "signature_image": "ceci n'est pas du base64 !!"})
jpeg = io.BytesIO(); Image.new("RGB", (1000, 400), "white").save(jpeg, "JPEG")
refused("JPEG deguise en PNG (signature de fichier incorrecte)", {"consent": True, "signature_image": data_url(jpeg.getvalue())})
refused("type MIME image/jpeg refuse", {"consent": True, "signature_image": data_url(GOOD, "image/jpeg")})
refused("PNG corrompu (tronque)", {"consent": True, "signature_image": data_url(GOOD[:300])})
refused("dimensions trop grandes (3000 x 1200)", {"consent": True, "signature_image": data_url(good_image(3000, 1200))})
refused("dimensions trop petites (50 x 20)", {"consent": True, "signature_image": data_url(good_image(50, 20))})
refused("image totalement transparente (vide)", {"consent": True, "signature_image": data_url(png_bytes(Image.new("RGBA", (1000, 400), (0, 0, 0, 0))))})
refused("image blanche opaque (vide)", {"consent": True, "signature_image": data_url(png_bytes(Image.new("RGBA", (1000, 400), (255, 255, 255, 255))))})
dot = Image.new("RGBA", (1000, 400), (0, 0, 0, 0)); ImageDraw.Draw(dot).rectangle([500, 200, 520, 220], fill=(0, 0, 0, 255))
refused("simple point (trace trop court)", {"consent": True, "signature_image": data_url(png_bytes(dot))})
refused("chaine geante (700 000 caracteres)", {"consent": True, "signature_image": "A" * 700_000}, expected=(400, 413, 422))
t0 = time.time()
refused("bombe de decompression (en-tete 40000 x 40000)", {"consent": True, "signature_image": data_url(bomb_png(40000, 40000))})
show("   ... refusee rapidement (sans decoder les pixels)", time.time() - t0 < 5, f"{time.time() - t0:.2f} s")
refused("champ signataire fourni seul, sans image -> refuse quand meme", {"consent": True, "signataire": "Pirate"})

print("== Nettoyage de l'image (donnee non fiable) ==")
from app import signature_image as si  # noqa: E402
raw_meta = good_image(meta={"cle": "SECRET-META-MARKER"})
png, meta = si.sanitize_signature_png(data_url(raw_meta))
clean = Image.open(io.BytesIO(png))
show("metadonnees PNG supprimees apres re-encodage", "cle" not in clean.info and b"SECRET-META-MARKER" not in png)
show("image recadree sur le trace (plus petite que le canevas)", clean.size[0] < 1000 and clean.size[1] < 400, clean.size)
show("meta : empreintes et dimensions", meta["sha256_source"] == hashlib.sha256(raw_meta).hexdigest()
     and meta["pixels_encre"] > 500 and meta["octets"] == len(png), meta)

print("== Roles ==")
refused("RH : la signature d'une remise est reservee a l'informatique", SIGN_OK, expected=(403,), token=RH)

print("== Signature valide de la remise ==")
body = {**SIGN_OK, "signataire": "Pirate", "methode": "confirmation"}  # champs ignores
s, sig = j("POST", SIGN_URL, body)
show("signature acceptee (201)", s == 201, f"HTTP {s} {sig if s != 201 else ''}")
show("methode = manuscrite_ecran (non falsifiable par le client)", sig.get("methode") == "manuscrite_ecran", sig.get("methode"))
show("signataire deduit de la fiche (pas du client)", sig.get("signataire") == "Marie Signature", sig.get("signataire"))
aj = sig.get("audit_json") or {}
show("preuves : temoin, IP, navigateur, empreintes, traits, duree",
     aj.get("temoin") == ADMIN and aj.get("ip") and aj.get("image", {}).get("sha256_source")
     and aj.get("traits") == 4 and aj.get("duree_ms") == 1800 and aj.get("type") == "remise", aj)
show("l'image n'est pas stockee en base (seulement ses empreintes)", len(json.dumps(aj)) < 1500 and "base64" not in json.dumps(aj),
     f"{len(json.dumps(aj))} octets")
s, pdf = call("GET", f"/assignments/{asg['id']}/document", token=ADM)
show("PDF scelle telecharge", s == 200 and pdf[:4] == b"%PDF", f"{len(pdf)} octets")
show("la signature manuscrite est dans le PDF (objet image)", pdf.count(b"/Subtype /Image") >= 1, pdf.count(b"/Subtype /Image"))
show("empreinte du PDF identique a celle enregistree", hashlib.sha256(pdf).hexdigest() == sig.get("empreinte_doc"))
try:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    sg = PdfFileReader(io.BytesIO(pdf)).embedded_signatures[0]
    try:
        st = validate_pdf_signature(sg)
        show("scellement PAdES intact et valide apres ajout de l'image", st.intact and st.valid)
    except Exception as exc:  # noqa: BLE001  (certificat auto-signe : chemin de confiance absent)
        show("scellement PAdES validable", False, str(exc)[:80])
except Exception as exc:  # noqa: BLE001
    show("lecture du scellement PAdES", False, str(exc)[:80])
s, rc = j("GET", f"/assignments/{asg['id']}/recap")
show("recap : remise marquee comme deja signee", rc.get("deja_signe") is True)
refused("seconde signature de la meme remise -> 409", SIGN_OK, expected=(409,))

print("== Restitution signee ==")
u2, asset2, asg2 = new_assignment("Paul", "Restitue", "ZZSG2", "ZZSG-SN2")
s, sig_r = j("POST", f"/assignments/{asg2['id']}/sign", SIGN_OK)
s, _ = j("POST", f"/lifecycle/depart/{u2['id']}", {"date_sortie": "2026-12-31"})
s, rr = j("GET", f"/lifecycle/recap/{u2['id']}")
show("recap de la restitution (materiel detenu)", s == 200 and len(rr["materiel"]) == 1 and rr["signature_obligatoire"] is True)
refused("restitution sans image -> refusee", {"user_id": u2["id"], "consent": True}, url="/lifecycle/restituer")
refused("restitution sans acceptation -> refusee", {"user_id": u2["id"], "signature_image": SIGN_OK["signature_image"]}, url="/lifecycle/restituer")
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u2["id"], "signataire": "Pirate", **SIGN_OK}, RH)
show("restitution signee par un compte RH (201)", s == 201, f"HTTP {s} {rs if s != 201 else ''}")
show("restitution : signataire deduit de la fiche, temoin = compte RH",
     rs.get("signataire") == "Paul Restitue" and (rs.get("audit_json") or {}).get("temoin") == "sec_sigrh"
     and rs.get("methode") == "manuscrite_ecran", rs.get("signataire"))
s, u2b = j("GET", f"/users/{u2['id']}")
show("le salarie passe en 'sorti' apres la restitution signee", u2b.get("statut") == "sorti", u2b.get("statut"))
s, pdf2 = call("GET", rs["ged_reference"] and f"/assignments/{asg2['id']}/document", token=ADM)
show("la remise signee de ce salarie reste consultable", s == 200 and pdf2[:4] == b"%PDF")

call("PUT", f"/auth/accounts/{rh_id}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
