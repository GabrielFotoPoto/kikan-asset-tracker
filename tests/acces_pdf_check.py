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

"""Tests des acces applicatifs dans l'accuse de remise (instantane fige, empreinte, preuve).

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/acces_pdf_check.py

Cree des donnees ZZAC et un compte sec_ac2* ; remet le reglage a "desactive" a la fin.
Fichier ASCII uniquement. Code de sortie 1 si un test echoue.
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


def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
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


def msg(r):
    return r.get("detail", "") if isinstance(r, dict) else str(r)


def sign_payload(**extra):
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"consent": True, "signature_image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
            "strokes": 4, "duration_ms": 1800, **extra}


def pdf_text(raw):
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)


def set_option(value):
    s, t = j("GET", "/parametres/pdf")
    return j("PUT", "/parametres/pdf", {"organisation": t["organisation"], "mentions": t["mentions"], "pied": t["pied"],
                                        "inclure_acces": value})


counter = [0]


def new_assignment(entite_id=None):
    counter[0] += 1
    n = counter[0]
    s, u = j("POST", "/users", {"prenom": "Ac", "nom": f"Remise{n}", "matricule": f"ZZAC-U{n}", "statut": "actif", "entite_id": entite_id})
    s, a = j("POST", "/assets", {"type": "PC", "marque": "ZZAC", "modele": "M", "numero_serie": f"ZZAC-SN{n}", "statut": "stock"})
    s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]], "sans_charte": entite_id is None})
    return u, asg


def grant(user, app, acces=True, note=None):
    return j("POST", f"/users/{user['id']}/applications", {"application_id": app["id"], "acces": acces, "note": note})


def document(asg_id):
    s, raw = call("GET", f"/assignments/{asg_id}/document", token=ADM)
    return raw


print("== Reglage ==")
s, t0 = j("GET", "/parametres/pdf")
show("reglage desactive par defaut", s == 200 and t0.get("inclure_acces") is False, t0)
s, r = call("POST", "/auth/accounts", {"username": "sec_ac2rh", "password": PW, "role": "rh"}, ADM)
if s == 409:
    accs = json.loads(call("GET", "/auth/accounts", token=ADM)[1])
    acc = next(a for a in accs if a["username"] == "sec_ac2rh")
    call("PUT", f"/auth/accounts/{acc['id']}", {"actif": True, "role": "rh", "password": PW}, ADM)
    rh_id = acc["id"]
else:
    rh_id = json.loads(r)["id"]
RH = login("sec_ac2rh", PW)
show("RH : modification du reglage refusee (403)", j("PUT", "/parametres/pdf", {"inclure_acces": True}, RH)[0] == 403)
s, r = j("PUT", "/parametres/pdf", {"organisation": "", "mentions": "", "pied": ""})
show("un PUT sans le champ laisse le reglage inchange", s == 200 and r["inclure_acces"] is False)

print("== Reglage desactive : accuse inchange ==")
u1, a1 = new_assignment()
s, rc = j("GET", f"/assignments/{a1['id']}/recap")
show("recap : pas de section d'acces", s == 200 and rc["acces_remise"] is None)
s, sg = j("POST", f"/assignments/{a1['id']}/sign", sign_payload())
t1 = pdf_text(document(a1["id"]))
show("accuse sans section ni mention", s == 201 and "Acces applicatifs" not in t1 and "pris connaissance" not in t1)
show("preuve : aucun instantane enregistre", sg["audit_json"]["acces"] is None)

print("== Reglage active ==")
s, r = set_option(True)
show("activation par l'informatique", s == 200 and r["inclure_acces"] is True and j("GET", "/parametres/pdf")[1]["inclure_acces"] is True)
mk = lambda nom, **kw: j("POST", "/applications", {"nom": nom, **kw})[1]
zeta, alpha, off, old, html = mk("ZZAC-Zeta"), mk("ZZAC-Alpha"), mk("ZZAC-Off"), mk("ZZAC-Old", actif=False), mk("ZZAC-Html")
u2, a2 = new_assignment()
grant(u2, zeta, True, "admin")
grant(u2, alpha, True, None)
grant(u2, off, False, "retire")
grant(u2, old, True, "ancienne")
grant(u2, html, True, "<b>x</b> & <i>y</i>")
s, rc = j("GET", f"/assignments/{a2['id']}/recap")
liste = rc["acces_remise"]["liste"]
fp = rc["acces_remise"]["empreinte"]
show("recap : acces accordes sur applications actives, tries", [x["application"] for x in liste] == ["ZZAC-Alpha", "ZZAC-Html", "ZZAC-Zeta"], liste)
show("recap : niveau repris de la note", {x["application"]: x["niveau"] for x in liste}["ZZAC-Zeta"] == "admin" and len(fp) == 64)
s, sg2 = j("POST", f"/assignments/{a2['id']}/sign", sign_payload(acces_empreinte=fp))
show("signature avec l'empreinte affichee", s == 201, msg(sg2))
raw2 = document(a2["id"])
t2 = pdf_text(raw2)
show("accuse : section et acces accordes", "Acces applicatifs accordes" in t2 and "ZZAC-Alpha" in t2 and "ZZAC-Zeta" in t2 and "admin" in t2)
show("accuse : acces refuse et application desactivee absents", "ZZAC-Off" not in t2 and "ZZAC-Old" not in t2)
show("accuse : texte HTML rendu tel quel (inerte)", "<b>x</b>" in t2 and "<i>y</i>" in t2)
show("accuse : ordre alphabetique", t2.index("ZZAC-Alpha") < t2.index("ZZAC-Html") < t2.index("ZZAC-Zeta"))
show("declaration : prise de connaissance des acces", "avoir pris connaissance des acces applicatifs" in t2.replace("\n", " "))
show("preuve : nombre et empreinte enregistres", sg2["audit_json"]["acces"] == {"nb": 3, "sha256": fp}, sg2["audit_json"]["acces"])
try:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    st = validate_pdf_signature(PdfFileReader(io.BytesIO(raw2)).embedded_signatures[0])
    show("scellement PAdES intact", st.intact and st.valid)
except Exception as exc:  # noqa: BLE001
    show("scellement PAdES", False, str(exc)[:80])

print("== Instantane fige ==")
grant(u2, zeta, True, "MODIFIE-APRES")
grant(u2, off, True, "AJOUTE-APRES")
raw2b = document(a2["id"])
show("changer les acces apres coup ne modifie pas le document signe",
     hashlib.sha256(raw2b).hexdigest() == sg2["empreinte_doc"] and "MODIFIE-APRES" not in pdf_text(raw2b))
s, rc2 = j("GET", f"/assignments/{a2['id']}/recap")
show("l'empreinte de la liste change avec les acces", rc2["acces_remise"]["empreinte"] != fp)

print("== Aucun acces ==")
u3, a3 = new_assignment()
s, sg3 = j("POST", f"/assignments/{a3['id']}/sign", sign_payload())
t3 = pdf_text(document(a3["id"]))
show("mention explicite quand aucun acces", s == 201 and "Aucun acces applicatif enregistre a ce jour" in t3 and "Acces applicatifs accordes" in t3)
show("preuve : zero acces enregistre", sg3["audit_json"]["acces"]["nb"] == 0)

print("== Coherence ecran / signature ==")
u4, a4 = new_assignment()
grant(u4, alpha, True, "niveau 1")
s, rc4 = j("GET", f"/assignments/{a4['id']}/recap")
fp4 = rc4["acces_remise"]["empreinte"]
grant(u4, alpha, True, "niveau 2")
s, r = j("POST", f"/assignments/{a4['id']}/sign", sign_payload(acces_empreinte=fp4))
show("acces modifies entre l'affichage et la signature : refus (409)", s == 409 and "ont change" in msg(r), msg(r))
s, ds = j("GET", f"/assignments/{a4['id']}")
show("rien n'a ete signe", not any(x for x in [call("GET", f"/assignments/{a4['id']}/document", token=ADM)[0] == 200]))
s, rc4b = j("GET", f"/assignments/{a4['id']}/recap")
s, r = j("POST", f"/assignments/{a4['id']}/sign", sign_payload(acces_empreinte=rc4b["acces_remise"]["empreinte"]))
show("apres rechargement : signature acceptee", s == 201 and "niveau 2" in pdf_text(document(a4["id"])), msg(r))
u5, a5 = new_assignment()
grant(u5, zeta, True, "x")
s, r = j("POST", f"/assignments/{a5['id']}/sign", sign_payload())
show("sans empreinte (scripts) : signature acceptee, instantane pris a la signature", s == 201 and r["audit_json"]["acces"]["nb"] == 1)
u6, a6 = new_assignment()
s, r = j("POST", f"/assignments/{a6['id']}/sign", sign_payload(acces_empreinte="0" * 64))
show("empreinte erronee : refus (409)", s == 409)

print("== Avec une charte ==")
s, ent = j("POST", "/entites", {"code": "ZZAC-E", "nom": "ZZAC Entite"})
bd = "----kikanAC"
raw = (f'--{bd}\r\nContent-Disposition: form-data; name="titre"\r\n\r\nZZAC Charte\r\n--{bd}\r\nContent-Disposition: form-data; name="entite_id"\r\n\r\n{ent["id"]}\r\n'
       f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="c.md"\r\nContent-Type: text/markdown\r\n\r\n').encode() + b"# Charte\n\nTexte.\n" + f"\r\n--{bd}--\r\n".encode()
call("POST", "/policies", token=ADM, raw=raw, ctype="multipart/form-data; boundary=" + bd)
u7, a7 = new_assignment(ent["id"])
grant(u7, alpha, True, "n")
s, rc7 = j("GET", f"/assignments/{a7['id']}/recap")
s, r = j("POST", f"/assignments/{a7['id']}/sign", sign_payload(acces_empreinte=rc7["acces_remise"]["empreinte"]))
t7 = pdf_text(document(a7["id"])).replace("\n", " ")
show("declaration combinee : acces et charte", s == 201 and "pris connaissance des acces applicatifs" in t7 and "accepte la charte informatique" in t7, msg(r))

print("== Restitution inchangee ==")
j("POST", f"/lifecycle/depart/{u2['id']}", {"date_sortie": "2026-12-31"})
s, rs = j("POST", "/lifecycle/restituer", {"user_id": u2["id"], **sign_payload()})
show("restitution signee", s == 201, msg(rs))
s, docs = j("GET", f"/lifecycle/recap/{u2['id']}")
show("recap de restitution : aucune section d'acces", "acces_remise" not in docs)

print("== Reglage desactive de nouveau ==")
set_option(False)
u8, a8 = new_assignment()
grant(u8, zeta, True, "x")
s, rc8 = j("GET", f"/assignments/{a8['id']}/recap")
s, r = j("POST", f"/assignments/{a8['id']}/sign", sign_payload())
show("reglage retire : recap et accuse sans acces", rc8["acces_remise"] is None and s == 201 and "Acces applicatifs" not in pdf_text(document(a8["id"])))

print("== Journal d'audit ==")
s, log = j("GET", "/audit?limit=500")
mods = [x for x in log if x["action"] == "modification" and x["target"] == "parametres/pdf/0"]
show("changements du reglage journalises", any("inclure_acces" in (x.get("detail") or "") for x in mods), [x["detail"] for x in mods][:3])

call("PUT", f"/auth/accounts/{rh_id}", {"actif": False}, ADM)
print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
