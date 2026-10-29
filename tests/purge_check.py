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

"""Purge RGPD : reglages, quarantaine des PDF, suppression apres le delai de grace, liste pour la GED, rappels.

Usage (moteur de stockage local) :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/purge_check.py

Cree des donnees marquees ZZPG (nettoyage : tests/cleanup_test_data.sql). Code de sortie 1 si un test echoue.
"""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
fails = 0


def signature_b64():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1000, 400), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(100, 300), (250, 110), (380, 300), (520, 130), (700, 290), (860, 150)],
                             fill=(17, 17, 17, 255), width=7)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


SIGN = {"consent": True, "signature_image": signature_b64(), "strokes": 4, "duration_ms": 1800}


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=90)
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


from sqlmodel import Session, select  # noqa: E402
from app import filestore, mailer, reminders  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import PurgeDocument, Signature  # noqa: E402

n_user = [0]


def salarie_sorti(sortie="2019-01-01"):
    """Salarie avec remise et restitution signees (2 PDF), sorti a la date donnee. Retourne (user, [references des PDF])."""
    n_user[0] += 1
    n = n_user[0]
    s, u = j("POST", "/users", {"nom": "ZZPG", "prenom": f"Sorti{n}", "matricule": f"ZZPG{n}", "statut": "actif"})
    s, a = j("POST", "/assets", {"type": "PC", "marque": "ZZPG-HP", "numero_serie": f"ZZPG-SN{n}", "statut": "stock"})
    s, asg = j("POST", "/assignments", {"user_id": u["id"], "asset_ids": [a["id"]]})
    s, sg = j("POST", f"/assignments/{asg['id']}/sign", SIGN)
    j("POST", f"/lifecycle/depart/{u['id']}", {"date_sortie": sortie})
    s, rs = j("POST", "/lifecycle/restituer", {"user_id": u["id"], **SIGN})
    return u, [sg["ged_reference"], rs["ged_reference"]], [sg["empreinte_doc"], rs["empreinte_doc"]]


def existe(ref):
    try:
        filestore.read_document(ref)
        return True
    except filestore.StorageError:
        return False


def audit_rows():
    s, rows = j("GET", "/audit?limit=500")
    return rows if isinstance(rows, list) else rows.get("items", [])


print("== Reglages (jamais codes en dur) ==")
s, r = j("GET", "/rgpd/retention")
show("valeurs par defaut : 12 mois, 30 jours de grace", s == 200 and r == {"mois": 12, "delai_grace_jours": 30}, r)
for body, name in (({"mois": -1}, "duree negative"), ({"mois": 241}, "duree trop longue"),
                   ({"mois": 12, "delai_grace_jours": 366}, "delai de grace trop long"), ({"mois": 12, "delai_grace_jours": -1}, "delai negatif")):
    s, _ = j("PUT", "/rgpd/retention", body)
    show(f"{name} refusee (422)", s == 422, f"HTTP {s}")
s, r = j("PUT", "/rgpd/retention", {"mois": 18, "delai_grace_jours": 7})
show("duree et delai de grace modifiables", s == 200 and r == {"mois": 18, "delai_grace_jours": 7}, r)
s, r = j("PUT", "/rgpd/retention", {"mois": 36})
show("le delai de grace est conserve si on ne l'envoie pas", r == {"mois": 36, "delai_grace_jours": 7}, r)
show("les changements de reglage sont journalises", any(x.get("action") == "rgpd_retention" for x in audit_rows()))

print("== Previsualisation et purge selective ==")
user_a, refs_a, hash_a = salarie_sorti("2019-01-01")
user_b, refs_b, hash_b = salarie_sorti(date.today().isoformat())
s, pv = j("GET", "/rgpd/purge-preview")
ids = {c["id"] for c in pv["candidats"]}
show("le salarie ancien est candidat, le recent non", user_a["id"] in ids and user_b["id"] not in ids)
show("la previsualisation annonce le delai de grace", pv.get("delai_grace_jours") == 7, pv.get("delai_grace_jours"))
s, r = j("POST", "/rgpd/purge", {"ids": []})
show("ids vide : personne n'est purge", s == 200 and r["count"] == 0, r)
s, got = j("GET", f"/users/{user_a['id']}")
show("le salarie est toujours la", s == 200)

print("== Purge : base supprimee, PDF en quarantaine ==")
show("avant la purge, les PDF sont a leur place", all(existe(x) for x in refs_a))
s, r = j("POST", "/rgpd/purge", {"ids": [user_a["id"]]})
show("purge du salarie ancien", s == 200 and r["count"] == 1 and r["documents"] == 2 and r["deplaces"] == 2, r)
s, got = j("GET", f"/users/{user_a['id']}")
show("salarie supprime de la base", s == 404)
show("les PDF ne sont plus a l'emplacement d'origine", not any(existe(x) for x in refs_a))
quar = ["local:" + filestore.QUARANTAINE + "/" + x.partition(":")[2] for x in refs_a]
show("les PDF sont dans le dossier A_PURGER, intacts", all(existe(x) for x in quar)
     and [filestore.sha256_hex(filestore.read_document(x)) for x in quar] == hash_a)
s, d = j("GET", "/rgpd/documents")
mine = [x for x in d["documents"] if x["statut"] == "quarantaine"]
show("deux documents suivis en quarantaine", len(mine) == 2, len(mine))
show("echeance = aujourd'hui + delai de grace", all(x["echeance"] == str(date.today() + timedelta(days=7)) and not x["echu"] for x in mine))
show("l'empreinte du PDF est conservee", sorted(x["empreinte"] for x in mine) == sorted(hash_a))
with Session(engine) as ss:
    show("plus aucune signature du salarie en base", not ss.exec(select(Signature).where(Signature.ged_reference.in_(refs_a))).all())
rows = audit_rows()
blob = json.dumps([x for x in rows if str(x.get("action", "")).startswith("rgpd")])
show("le journal de purge ne contient ni nom ni matricule", "ZZPG" not in blob and "Sorti" not in blob)
show("la purge est journalisee", any(x.get("action") == "rgpd_purge" for x in rows))
s, st = j("GET", "/rgpd/etat")
show("l'etat compte 2 documents en quarantaine, aucun echu", st["quarantaine"] == 2 and st["quarantaine_echus"] == 0, st)

print("== Suppression definitive apres le delai de grace ==")
s, r = j("POST", "/rgpd/quarantaine/supprimer", {})
show("avant l'echeance rien n'est supprime", s == 200 and r["supprimes"] == 0 and r["non_echus"] == 2, r)
show("les PDF sont toujours en quarantaine", all(existe(x) for x in quar))
with Session(engine) as ss:
    for dd in ss.exec(select(PurgeDocument)).all():
        dd.echeance = date.today() - timedelta(days=1)
        ss.add(dd)
    ss.commit()
s, st = j("GET", "/rgpd/etat")
show("les documents sont maintenant echus", st["quarantaine_echus"] == 2, st)
s, r = j("POST", "/rgpd/quarantaine/supprimer", {})
show("suppression definitive des 2 PDF", s == 200 and r["supprimes"] == 2 and r["echecs"] == 0, r)
show("les PDF ont disparu du partage", not any(existe(x) for x in quar))
s, d = j("GET", "/rgpd/documents")
show("plus aucun document suivi", d["documents"] == [])
rows = audit_rows()
proofs = {x.get("target") for x in rows if x.get("action") == "rgpd_document_supprime"}
show("le journal garde l'empreinte SHA-256 des PDF supprimes", set(hash_a) <= proofs)

print("== Restauration pendant le delai de grace ==")
user_c, refs_c, hash_c = salarie_sorti("2019-01-01")
j("POST", "/rgpd/purge", {"ids": [user_c["id"]]})
s, d = j("GET", "/rgpd/documents")
ids_c = [x["id"] for x in d["documents"] if x["statut"] == "quarantaine"]
s, r = j("POST", "/rgpd/quarantaine/restaurer", {"ids": ids_c})
show("restauration des PDF", s == 200 and r["restaures"] == 2 and r["echecs"] == 0, r)
show("les PDF sont revenus a leur emplacement d'origine", all(existe(x) for x in refs_c))
s, d = j("GET", "/rgpd/documents")
show("plus de suivi apres restauration", d["documents"] == [])

print("== PDF absent ou partage indisponible ==")
with Session(engine) as ss:
    ss.add(PurgeDocument(reference="local:ZZPG/absent.pdf", moteur="local", statut="a_deplacer", empreinte="e" * 64, echeance=date.today()))
    ss.add(PurgeDocument(reference="smb:ZZPG/indisponible.pdf", moteur="smb", statut="a_deplacer", empreinte="f" * 64, echeance=date.today()))
    ss.commit()
s, r = j("POST", "/rgpd/purge", {"ids": []})
s, d = j("GET", "/rgpd/documents")
left = [x for x in d["documents"] if x["statut"] == "a_deplacer"]
show("un PDF deja absent n'est plus suivi", not any("absent.pdf" in x["reference"] for x in d["documents"]))
show("un PDF dont le partage est indisponible reste a reessayer", len(left) == 1 and "indisponible" in left[0]["reference"] and r["en_attente"] == 1, r)

print("== Documents de la GED (SharePoint, DocuWare) ==")
user_e, refs_e, hash_e = salarie_sorti("2019-01-01")
with Session(engine) as ss:
    for k, ref in enumerate(refs_e):
        sig = ss.exec(select(Signature).where(Signature.ged_reference == ref)).first()
        sig.ged_reference = f"docuware:ZZPG{k}/2019/ZZPG_{k}.pdf"
        ss.add(sig)
    ss.commit()
s, r = j("POST", "/rgpd/purge", {"ids": [user_e["id"]]})
show("la purge ne deplace pas les documents de la GED", s == 200 and r["documents"] == 2 and r["deplaces"] == 0, r)
s, d = j("GET", "/rgpd/documents")
ged = [x for x in d["documents"] if x["statut"] == "ged_a_supprimer"]
show("deux documents listes pour l'equipe de la GED", len(ged) == 2 and all(x["moteur"] == "docuware" for x in ged), len(ged))
s, st = j("GET", "/rgpd/etat")
show("l'etat compte les documents de la GED", st["ged"] == 2, st)
s, r = j("POST", "/rgpd/quarantaine/supprimer", {})
show("la suppression de la quarantaine ne touche pas la GED", r["supprimes"] == 0 and len([x for x in j("GET", "/rgpd/documents")[1]["documents"] if x["statut"] == "ged_a_supprimer"]) == 2, r)

print("== Rappels par e-mail ==")
user_f, refs_f, hash_f = salarie_sorti("2019-01-01")
with Session(engine) as ss:
    cfg = mailer.load_config(ss)
    show("le rappel de purge est actif par defaut, relance chaque semaine", cfg.purge is True and cfg.purge_sem == 1, (cfg.purge, cfg.purge_sem))
    with Session(engine) as s2:
        for dd in s2.exec(select(PurgeDocument).where(PurgeDocument.statut == "ged_a_supprimer")).all():
            dd.echeance = date.today() - timedelta(days=1)
            s2.add(dd)
        s2.commit()
    items = reminders.collect(ss, cfg, date.today())["purge"]
    texte = " | ".join(x["ligne"] for x in items)
    show("rappel : salarie a purger", any(x["cle"] == "purge:candidats" for x in items), texte)
    show("rappel : documents de la GED echus", any(x["cle"] == "purge:ged" for x in items), texte)
    show("rappel : partage indisponible", any(x["cle"] == "purge:deplacement" for x in items), texte)
    show("le rappel ne contient ni nom ni matricule", "ZZPG" not in texte and "Sorti" not in texte)
    cfg.purge = False
    show("rappel desactivable", reminders.collect(ss, cfg, date.today())["purge"] == [])
s, mc = j("GET", "/mail/config")
show("reglage du rappel visible dans la configuration des e-mails", mc["config"].get("purge") is True and mc["config"].get("purge_sem") == 1, mc.get("config", {}).get("purge"))

print(f"\n{'ECHEC' if fails else 'OK'} : {fails} test(s) en echec")
sys.exit(1 if fails else 0)
