# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

"""Suite de tests du lot G3 : pieces jointes transversales, magic bytes, re-encodage Pillow, quotas, stockage et purge RGPD."""
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

from PIL import Image
from sqlmodel import Session, select
from app import filestore
from app.db import engine
from app.models import Attachment, PurgeDocument, Ticket

B = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("TEST_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "ChangeMoi123!")

fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}  {name}" + (f" ({detail})" if detail else ""))


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "X-Kikan-Request": "1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(B + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw.decode("utf-8")) if raw else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw
        return e.code, payload, dict(e.headers)


def upload(path, filename, content, token, content_type="application/octet-stream"):
    boundary = "----KikanTestBoundary" + uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n".encode("ascii"),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
        content,
        f"\r\n--{boundary}--\r\n".encode("ascii"),
    ]
    body = b"".join(parts)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Kikan-Request": "1",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(B + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw
        return e.code, payload


def download(path, token):
    req = urllib.request.Request(B + path, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def make_jpeg_with_exif():
    img = Image.new("RGB", (32, 32), color=(29, 66, 138))
    exif = img.getexif()
    exif[0x010F] = "SecretPhoneModel"
    exif[0x0131] = "SecretSoftware"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def make_png():
    img = Image.new("RGB", (16, 16), color=(30, 120, 70))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def login(u, p):
    st, d, _ = call("POST", "/auth/login", {"username": u, "password": p})
    assert st == 200 and d and d.get("access_token"), f"Login {u} echoue: {st} {d}"
    return d["access_token"]


def main():
    tok_it = login(ADMIN_USER, ADMIN_PASS)
    call("POST", "/auth/accounts", {"username": "sec_pj_rh", "password": "TestPassword123!", "role": "rh"}, tok_it)
    tok_rh = login("sec_pj_rh", "TestPassword123!")

    # Creer un ticket de test
    st, tkt, _ = call("POST", "/tickets", {"nature_code": "panne_materiel", "titre": "ZZPJ Ticket PJ"}, tok_it)
    tid = tkt["id"]

    # 1. Rejets de formats interdits / magic bytes
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "mal.svg", b"<svg><script>alert(1)</script></svg>", tok_it, "image/svg+xml")
    show("Rejet SVG (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "page.html", b"<html><body>hi</body></html>", tok_it, "text/html")
    show("Rejet HTML (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "export.csv", b"=CMD()|1,2\n", tok_it, "text/csv")
    show("Rejet CSV (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "archive.zip", b"PK\x03\x04dummy", tok_it, "application/zip")
    show("Rejet ZIP (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "tool.exe", b"MZdummy", tok_it, "application/octet-stream")
    show("Rejet EXE (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "faux.png", b"NOT_A_PNG_AT_ALL", tok_it, "image/png")
    show("Rejet faux PNG magic bytes (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "binaire.txt", b"hello\x00world", tok_it, "text/plain")
    show("Rejet texte avec octet nul (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "bad.txt", b"\xff\xfe\xfd", tok_it, "text/plain")
    show("Rejet texte non UTF-8 (422)", st == 422, f"got {st}")
    st, _ = upload(f"/tickets/{tid}/pieces-jointes", "script.txt", b"\xef\xbb\xbf<svg onload=alert(1)>", tok_it, "text/plain")
    show("Rejet SVG avec BOM deguise en .txt (422)", st == 422, f"got {st}")

    # 2. Upload JPEG avec EXIF -> re-encodage retire EXIF + en-tetes securises au telechargement
    jpg_exif = make_jpeg_with_exif()
    show("JPEG de test contient bien EXIF avant upload", b"SecretPhoneModel" in jpg_exif)
    st, pj1 = upload(f"/tickets/{tid}/pieces-jointes", "photo_ecran.jpg", jpg_exif, tok_it, "image/jpeg")
    show("Upload JPEG reussi (201)", st == 201 and pj1["mime_type"] == "image/jpeg", str(pj1))

    st_dl, raw_dl, hdrs = download(f"/tickets/{tid}/pieces-jointes/{pj1['id']}", tok_it)
    show("Telechargement PJ : headers attachment, nosniff, no-store",
         st_dl == 200
         and "attachment;" in hdrs.get("content-disposition", "")
         and hdrs.get("x-content-type-options") == "nosniff"
         and "no-store" in hdrs.get("cache-control", ""),
         str(hdrs))
    show("Re-encodage Pillow retire EXIF et SHA-256 correspond",
         b"SecretPhoneModel" not in raw_dl and hashlib.sha256(raw_dl).hexdigest() == pj1["sha256"])

    # 3. Controle droits rh -> 403
    st_rh, _ = upload(f"/tickets/{tid}/pieces-jointes", "ok.txt", b"bonjour", tok_rh)
    st_rh_dl, _, _ = download(f"/tickets/{tid}/pieces-jointes/{pj1['id']}", tok_rh)
    show("Role rh refuse (403) sur upload et download PJ", st_rh == 403 and st_rh_dl == 403)

    # 4. Upload PDF, TXT et PNG jusqu'au quota de 5 fichiers, puis 6e refuse (409)
    st_pdf, pj_pdf = upload(f"/tickets/{tid}/pieces-jointes", "doc.pdf", b"%PDF-1.4\n%%EOF\n", tok_it, "application/pdf")
    st_txt, _ = upload(f"/tickets/{tid}/pieces-jointes", "journal.log", b"ligne 1\nligne 2\n", tok_it, "text/plain")
    st_p3, _ = upload(f"/tickets/{tid}/pieces-jointes", "img3.png", make_png(), tok_it, "image/png")
    st_p4, _ = upload(f"/tickets/{tid}/pieces-jointes", "img4.png", make_png(), tok_it, "image/png")
    st_p6, _ = upload(f"/tickets/{tid}/pieces-jointes", "img6.png", make_png(), tok_it, "image/png")
    show("Upload PDF/LOG/PNG ok et 6e fichier refuse (409)",
         st_pdf == 201 and st_txt == 201 and st_p3 == 201 and st_p4 == 201 and st_p6 == 409,
         f"st={st_pdf},{st_txt},{st_p3},{st_p4},{st_p6}")

    # 5. Suppression manuelle d'une PJ + verification stockage status/test
    st_del, _, _ = call("DELETE", f"/tickets/{tid}/pieces-jointes/{pj_pdf['id']}", token=tok_it)
    show("Suppression manuelle PJ (204)", st_del == 204)
    st_st, status_data, _ = call("GET", "/storage/status", token=tok_it)
    st_tst, test_data, _ = call("POST", "/storage/pieces-jointes/test", {}, tok_it)
    show("Endpoint /storage/status expose pieces_jointes et test PJ OK",
         st_st == 200 and "pieces_jointes" in status_data and st_tst == 200 and test_data.get("ok") is True)

    # 6. Purge RGPD : anonymisation ticket -> PJ en quarantaine A_PURGER/, restauration REFUSEE (409), suppression definitive
    call("POST", f"/tickets/{tid}/statut", {"statut": "en_cours"}, tok_it)
    call("POST", f"/tickets/{tid}/statut", {"statut": "resolu"}, tok_it)
    call("POST", f"/tickets/{tid}/statut", {"statut": "ferme"}, tok_it)
    with Session(engine) as s:
        tk = s.get(Ticket, tid)
        tk.ferme_le = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=800)
        s.add(tk)
        s.commit()

    st_p, res_p, _ = call("POST", "/rgpd/purge-tickets", {"ids": [tid]}, tok_it)
    show("Purge ticket clos avec PJ reussie", st_p == 200 and res_p.get("anonymises") == 1)

    with Session(engine) as s:
        restantes = s.exec(select(Attachment).where(Attachment.entity_type == "ticket", Attachment.entity_id == tid)).all()
        docs_pj = s.exec(select(PurgeDocument).where(PurgeDocument.type_doc == "piece_jointe")).all()
    show("Lignes Attachment supprimees et PJ deplacees en quarantaine A_PURGER/",
         len(restantes) == 0 and len(docs_pj) == 4 and all(d.statut == "quarantaine" and (d.reference_quarantaine or "").startswith("local:A_PURGER/") for d in docs_pj),
         f"rest={len(restantes)} docs={len(docs_pj)}")

    # Restauration depuis la quarantaine REFUSEE (409) pour les pieces jointes
    st_rest, _, _ = call("POST", "/rgpd/quarantaine/restaurer", {"ids": [docs_pj[0].id]}, tok_it)
    show("Restauration de quarantaine refusee pour une piece jointe (409)", st_rest == 409, f"got {st_rest}")

    # Suppression definitive apres echeance
    with Session(engine) as s:
        for d in s.exec(select(PurgeDocument).where(PurgeDocument.type_doc == "piece_jointe")).all():
            d.echeance = datetime.now(timezone.utc).date() - timedelta(days=1)
            s.add(d)
        s.commit()
    st_sup, sup_res, _ = call("POST", "/rgpd/quarantaine/supprimer", {}, tok_it)
    show("Suppression definitive des PJ echues en quarantaine", st_sup == 200 and sup_res.get("supprimes") == 4, str(sup_res))

    # 7. Plafond taille max depasse (413)
    call("PUT", "/parametres/tickets", {"cloture_auto_jours": 7, "delais_cibles_heures": {"faible": 120}, "pj_taille_max_mio": 1}, tok_it)
    _, t_big, _ = call("POST", "/tickets", {"nature_code": "autre", "titre": "ZZPJ Big"}, tok_it)
    # 1.1 Mio de texte
    st_413, _ = upload(f"/tickets/{t_big['id']}/pieces-jointes", "gros.txt", b"a" * (1024 * 1024 + 100), tok_it, "text/plain")
    show("Fichier depassant pj_taille_max_mio refuse (413)", st_413 == 413, f"got {st_413}")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
