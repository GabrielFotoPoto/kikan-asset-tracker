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

"""Jeu de donnees de DEMONSTRATION : un groupe fictif et ses filiales, des salaries, du materiel, des remises signees (vrais PDF scelles),
des restitutions, des departs, des besoins, des acces applicatifs et un import annulable.

Ne se lance pas directement : utiliser scripts/demo.sh (charger, effacer, etat). Le script tourne dans le conteneur de l'API.

Securite :
- il REFUSE de charger quoi que ce soit si la base contient deja des donnees qui ne sont pas de demonstration ;
- tout ce qu'il cree est marque (entites DEMO-..., matricules DEMO-..., materiel DEMO-...) : "effacer" ne retire que cela, PDF scelles compris ;
- personnes, adresses et numeros sont fictifs (adresses en @exemple.test).
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

B = os.environ.get("DEMO_BASE_URL", "http://localhost:8000")
ACTION = os.environ.get("DEMO_ACTION", "charger")
TODAY = date.today()

ENTITES = [  # code, nom, parent
    ("DEMO-GRP", "Groupe SICA Atlantique", ""),
    ("DEMO-SICA", "SICA Atlantique", "DEMO-GRP"),
    ("DEMO-AMT", "AMT", "DEMO-GRP"),
    ("DEMO-SISP", "SISP", "DEMO-GRP"),
    ("DEMO-ALLFAST", "ALLFAST", "DEMO-GRP"),
    ("DEMO-ATENA", "ATENA", "DEMO-GRP"),
]
FILIALES = ["DEMO-SICA", "DEMO-AMT", "DEMO-SISP", "DEMO-ALLFAST", "DEMO-ATENA"]
POIDS = [14, 10, 8, 9, 7]  # repartition des salaries entre les filiales
SERVICES = ["Comptabilite", "Ressources humaines", "Informatique", "Logistique", "Commercial", "Production", "Direction", "Qualite"]
APPLICATIONS = [  # nom, description, entites concernees (None = tout le groupe)
    ("ERP Cereo", "ERP de gestion", None), ("Messagerie Microsoft 365", "Messagerie et agenda", None),
    ("VPN", "Acces distant", None), ("CRM Commercial", "Suivi des clients", ["DEMO-SICA", "DEMO-AMT"]),
    ("Paie", "Gestion de la paie", ["DEMO-SICA"]), ("Outil qualite", "Non-conformites et audits", ["DEMO-ALLFAST", "DEMO-ATENA"]),
]
PRENOMS = ["Camille", "Julien", "Sophie", "Nicolas", "Laura", "Thomas", "Emilie", "Antoine", "Claire", "Mathieu", "Marion", "Pierre", "Sarah",
           "Alexandre", "Lucie", "Maxime", "Julie", "Romain", "Anais", "Vincent", "Helene", "Benoit", "Charlotte", "Damien", "Elodie", "Fabien"]
NOMS = ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre",
        "Michel", "Garcia", "David", "Bertrand", "Roux", "Vincent", "Fournier", "Morel", "Girard", "Andre", "Mercier", "Dupont", "Lambert"]
PC = [("Dell", "Latitude 5550"), ("Lenovo", "ThinkPad T14"), ("HP", "EliteBook 840 G10")]
PHONES = [("Apple", "iPhone 15"), ("Samsung", "Galaxy S24"), ("Samsung", "Galaxy A55")]
fails = 0


def log(msg):
    print(msg, flush=True)


def call(method, path, body=None, token=None, raw=None, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    if token:
        h["Authorization"] = "Bearer " + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(B + path, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=120)  # nosec B310 (adresse de l'API locale, fixee par l'operateur du script)
        out = r.read()
        return r.status, (json.loads(out) if out else None)
    except urllib.error.HTTPError as e:
        raw_err = e.read()
        try:
            return e.code, json.loads(raw_err)
        except ValueError:
            return e.code, raw_err


def signature_b64(k=0):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    j = (k * 37) % 90
    ImageDraw.Draw(img).line([(100, 300 - j // 3), (250 + j, 110), (380, 300), (520 - j, 130 + j // 2), (700, 290 - j // 3), (860 + j // 2, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def sign_body(k):
    return {"consent": True, "signature_image": signature_b64(k), "strokes": 5, "duration_ms": 2100}


def login():
    s, r = call("POST", "/auth/login", {"username": os.environ.get("TEST_ADMIN_USER", "admin"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")})
    if s != 200:
        sys.exit("Connexion impossible : verifiez l'identifiant et le mot de passe de l'administrateur.")
    return r["access_token"]


def need(label, res, ok=(200, 201)):
    s, r = res
    if s not in ok:
        sys.exit(f"ECHEC ({label}) : HTTP {s} {str(r)[:300]}")
    return r


# --------------------------------------------------------------------------------------------------------------------------------------------
def effacer():
    """Retire tout ce que le jeu de demonstration a cree (et seulement cela), PDF scelles compris."""
    from sqlalchemy import text
    from sqlmodel import Session
    from app import filestore
    from app.db import engine
    with Session(engine) as s:
        q = lambda sql: s.execute(text(sql))
        # Requetes ecrites en entier (pas d'assemblage) : seuls les elements marques DEMO- sont concernes.
        refs = [r[0] for r in q("SELECT ged_reference FROM signatures WHERE ged_reference IS NOT NULL AND assignment_id IN "
                                "(SELECT id FROM assignments WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%'))")]
        q("DELETE FROM import_lots WHERE kind = 'entites' AND (elements::jsonb -> 'ids' -> 'entite') @> to_jsonb((SELECT id FROM entite WHERE code = 'DEMO-GRP'))")
        q("DELETE FROM besoins WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%') OR assignment_id IN "
          "(SELECT id FROM assignments WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%'))")
        q("DELETE FROM signatures WHERE assignment_id IN "
          "(SELECT id FROM assignments WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%'))")
        q("DELETE FROM assignment_assets WHERE assignment_id IN "
          "(SELECT id FROM assignments WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%'))")
        q("DELETE FROM assignments WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%')")
        q("DELETE FROM user_applications WHERE user_id IN (SELECT id FROM users WHERE matricule LIKE 'DEMO-%')")
        q("DELETE FROM users WHERE matricule LIKE 'DEMO-%'")
        q("DELETE FROM assignment_assets WHERE asset_id IN (SELECT id FROM assets WHERE identifiant_interne LIKE 'DEMO-%')")
        q("DELETE FROM assets WHERE identifiant_interne LIKE 'DEMO-%'")
        q("DELETE FROM user_applications WHERE application_id IN "
          "(SELECT id FROM applications WHERE entite_id IN (SELECT id FROM entite WHERE code LIKE 'DEMO-%'))")
        q("DELETE FROM applications WHERE entite_id IN (SELECT id FROM entite WHERE code LIKE 'DEMO-%')")
        q("DELETE FROM entite WHERE code LIKE 'DEMO-%'")
        s.commit()
    gone = sum(1 for ref in refs if filestore.delete_document(ref))
    log(f"Jeu de demonstration efface ({gone} PDF scelle(s) supprime(s) sur {len(refs)}).")


def etat():
    token = login()
    users = need("salaries", call("GET", "/users", token=token))
    assets = need("materiel", call("GET", "/assets", token=token))
    ents = need("entites", call("GET", "/entites", token=token))
    demo_u = [u for u in users if str(u.get("matricule") or "").startswith("DEMO-")]
    demo_a = [a for a in assets if str(a.get("identifiant_interne") or "").startswith("DEMO-")]
    log(f"Salaries : {len(demo_u)} de demonstration sur {len(users)} ; materiel : {len(demo_a)} sur {len(assets)} ; "
        f"entites : {len([e for e in ents if e['code'].startswith('DEMO-')])} sur {len(ents)}.")


def charger():
    token = login()
    users = need("salaries", call("GET", "/users", token=token))
    assets = need("materiel", call("GET", "/assets", token=token))
    ents = need("entites", call("GET", "/entites", token=token))
    reels = ([u for u in users if not str(u.get("matricule") or "").startswith("DEMO-")]
             + [a for a in assets if not str(a.get("identifiant_interne") or "").startswith("DEMO-")]
             + [e for e in ents if not e["code"].startswith("DEMO-")])
    if reels:
        sys.exit(f"REFUSE : la base contient deja {len(reels)} element(s) qui ne sont pas de demonstration (salaries, materiel ou entites). "
                 "Le jeu de demonstration se charge sur une instance vide ou de test, jamais sur des donnees reelles.")
    if any(str(u.get("matricule") or "").startswith("DEMO-") for u in users) or any(e["code"].startswith("DEMO-") for e in ents):
        sys.exit("Le jeu de demonstration est deja charge. Lancez d'abord : scripts/demo.sh effacer")

    # 1. Entites, par la page d'import (un lot d'import que l'on peut ouvrir sur la page Import)
    csv = "code;nom;code_parent;actif\n" + "".join(f"{c};{n};{p};oui\n" for c, n, p in ENTITES)
    boundary = "----kikanDemo"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"entites.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() \
        + csv.encode() + f"\r\n--{boundary}--\r\n".encode()
    r = need("import des entites", call("POST", "/import/entites?strict=true", token=token, raw=body,
                                        headers={"Content-Type": "multipart/form-data; boundary=" + boundary}))
    log(f"Entites importees : {r['imported']} (lot d'import n{r.get('lot_id')})")
    eid = {e["code"]: e["id"] for e in need("entites", call("GET", "/entites", token=token))}

    # 2. Applications et acces
    apps = {}
    for nom, desc, scope in APPLICATIONS:
        for code in (scope or ["DEMO-GRP"]):
            a = need(f"application {nom}", call("POST", "/applications", {"nom": nom, "description": desc, "entite_id": eid[code], "actif": True}, token))
            apps.setdefault(nom, []).append((a["id"], code))
    log(f"Applications : {sum(len(v) for v in apps.values())} entrees (6 applications, certaines par filiale)")

    # 3. Materiel : 52 salaries, 1 PC chacun (sauf sortis anciens), des telephones, des machines en stock
    def asset(i, kind, stock=False):
        marque, modele = (PC if kind == "PC portable" else PHONES)[i % 3]
        achat = TODAY - timedelta(days=60 + (i * 41) % 1300)
        if kind == "PC portable" and i % 9 == 4:
            achat = TODAY - timedelta(days=1440)   # renouvellement dans une vingtaine de jours
        elif kind == "PC portable" and i % 13 == 6:
            achat = TODAY - timedelta(days=1490)   # echeance de renouvellement depassee
        pref = "PC" if kind == "PC portable" else "TEL"
        return need(f"materiel {pref}{i}", call("POST", "/assets", {
            "type": kind, "marque": marque, "modele": modele, "numero_serie": f"DEMO-SN-{pref}-{i:04d}", "identifiant_interne": f"DEMO-{pref}-{i:04d}",
            "date_achat": str(achat), "fin_garantie": str(achat + timedelta(days=1095)), "echeance_renouvellement": str(achat + timedelta(days=1460)),
            "statut": "stock", "entite_id": None}, token))

    # 4. Salaries (52) : repartis entre les filiales
    total = 52
    person = []
    for i in range(total):
        fil = FILIALES[[k for k, c in enumerate(__import__("itertools").accumulate(POIDS)) if i % sum(POIDS) < c][0]]
        person.append({"i": i, "prenom": PRENOMS[i % len(PRENOMS)], "nom": NOMS[(i * 7 + i // len(PRENOMS)) % len(NOMS)], "ent": fil,
                       "service": SERVICES[i % len(SERVICES)]})
    # roles dans le scenario
    PREVUS = range(40, 43)       # arrivees a venir : besoins ouverts
    DEPART_FUTUR = range(43, 45)  # depart dans quelques jours, materiel encore detenu
    NON_RESTITUES = range(45, 47)  # date de sortie depassee, materiel non restitue
    SORTIS_ANCIENS = range(47, 50)  # sortis depuis plus d'un an : a purger
    SORTIS_RECENTS = range(50, 52)  # sortis recemment
    sortie_ancien = {47: 560, 48: 480, 49: 410}
    sortie_recent = {50: 70, 51: 160}

    made = {}
    for p in person:
        i = p["i"]
        statut = "prevu" if i in PREVUS else "actif"
        arrivee = TODAY + timedelta(days=(5, 12, 25)[i - 40]) if i in PREVUS else TODAY - timedelta(days=200 + (i * 53) % 1100)
        u = need(f"salarie {i}", call("POST", "/users", {
            "matricule": f"DEMO-{i + 1:04d}", "nom": p["nom"], "prenom": p["prenom"], "email": f"{p['prenom'].lower()}.{p['nom'].lower()}{i}@exemple.test",
            "entite_id": eid[p["ent"]], "service": p["service"], "statut": statut, "date_arrivee": str(arrivee)}, token))
        made[i] = u
    log(f"Salaries : {len(made)}")

    # 5. Remises signees (vrais PDF scelles)
    pcs = {}
    n_sign = 0
    for p in person:
        i = p["i"]
        if i in PREVUS:
            continue
        pc = asset(i, "PC portable")
        pcs[i] = pc
        ids = [pc["id"]]
        phone = None
        if i % 3 == 0 and i not in SORTIS_ANCIENS:
            phone = asset(i, "Smartphone")
            ids.append(phone["id"])
        a = need(f"remise {i}", call("POST", "/assignments", {"user_id": made[i]["id"], "asset_ids": ids}, token))
        need(f"signature {i}", call("POST", f"/assignments/{a['id']}/sign", sign_body(i), token))
        n_sign += 1
    log(f"Remises signees : {n_sign}")

    # 6. Stock disponible (a remettre)
    for k in range(100, 106):
        asset(k, "PC portable")
    for k in range(100, 104):
        asset(k, "Smartphone")

    # 7. Departs et restitutions
    for i in DEPART_FUTUR:
        need(f"depart {i}", call("POST", f"/lifecycle/depart/{made[i]['id']}", {"date_sortie": str(TODAY + timedelta(days=(9, 21)[i - 43]))}, token), (200, 201))
    for i in NON_RESTITUES:
        need(f"depart {i}", call("POST", f"/lifecycle/depart/{made[i]['id']}", {"date_sortie": str(TODAY - timedelta(days=(18, 33)[i - 45]))}, token), (200, 201))
    for jours in (sortie_ancien, sortie_recent):
        for i, d in jours.items():
            need(f"depart {i}", call("POST", f"/lifecycle/depart/{made[i]['id']}", {"date_sortie": str(TODAY - timedelta(days=d))}, token), (200, 201))
            need(f"restitution {i}", call("POST", "/lifecycle/restituer", {"user_id": made[i]["id"], **sign_body(i + 100)}, token))
    log("Departs et restitutions : 9 salaries concernes (2 departs a venir, 2 materiels non restitues, 5 sortis dont 3 a purger)")

    # 8. Acces applicatifs
    nb = 0
    for p in person:
        i = p["i"]
        if i in SORTIS_ANCIENS or i in SORTIS_RECENTS:
            continue
        for nom, lst in apps.items():
            for app_id, code in lst:
                if code == "DEMO-GRP" or code == p["ent"]:
                    if nom in ("Paie", "CRM Commercial", "Outil qualite") and i % 2:
                        continue
                    need(f"acces {nom}", call("POST", f"/users/{made[i]['id']}/applications", {"application_id": app_id, "acces": True,
                         "note": "Profil standard" if i % 5 else "Administrateur metier"}, token))
                    nb += 1
    log(f"Acces applicatifs : {nb}")

    # 9. Besoins de materiel (arrivees a venir + un besoin solde par une remise)
    cats = need("categories", call("GET", "/besoins/categories", token=token))
    pc_cat = next((c for c in cats if c.startswith("PC portable")), cats[0])
    phone_cat = next((c for c in cats if c.startswith("Smartphone")), cats[-1])
    b1 = need("besoin", call("POST", "/besoins", {"user_id": made[40]["id"], "type": pc_cat, "quantite": 1, "commentaire": "Poste comptabilite"}, token))
    need("besoin", call("POST", "/besoins", {"user_id": made[40]["id"], "type": phone_cat, "quantite": 1}, token))
    b3 = need("besoin", call("POST", "/besoins", {"user_id": made[41]["id"], "type": pc_cat, "quantite": 1, "commentaire": "Avec double ecran"}, token))
    need("besoin", call("POST", "/besoins", {"user_id": made[42]["id"], "type": pc_cat, "quantite": 1}, token))
    need("statut besoin", call("POST", f"/besoins/{b3['id']}/statut", {"statut": "en_preparation"}, token))
    solde = need("besoin a solder", call("POST", "/besoins", {"user_id": made[7]["id"], "type": phone_cat, "quantite": 1, "commentaire": "Telephone de service"}, token))
    tel = asset(300, "Smartphone")
    a2 = need("remise du telephone", call("POST", "/assignments", {"user_id": made[7]["id"], "asset_ids": [tel["id"]], "besoin_ids": [solde["id"]]}, token))
    need("signature du telephone", call("POST", f"/assignments/{a2['id']}/sign", sign_body(7), token))
    log("Besoins : 4 ouverts (dont 1 en preparation) et 1 solde par une remise")
    del b1

    log("")
    log("Jeu de demonstration charge : 52 salaries, 6 entites, 6 applications, 76 materiels, des remises et restitutions signees (PDF scelles).")
    log("Rappel : les salaries en depart et non restitues alimentent les rappels e-mail ; 3 sortis depuis plus d'un an apparaissent dans la page RGPD.")


if ACTION == "charger":
    charger()
elif ACTION == "effacer":
    effacer()
elif ACTION == "etat":
    etat()
else:
    sys.exit("Action inconnue : charger, effacer ou etat")
