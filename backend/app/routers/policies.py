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

"""Chartes informatiques : depot par l'informatique (globale ou par entite), versions, apercu."""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlmodel import Session, select

from .. import charte
from ..auth import get_current_account, writer_guard
from ..db import get_session
from ..filestore import StorageError, delete_document, is_pending, read_document, sha256_hex, store_document
from ..models import Account, Entite, Policy
from ..scope import GLOBAL, Scope, scope_dep

router = APIRouter(
    prefix="/policies", tags=["policies"],
    dependencies=[Depends(writer_guard("informatique"))],
)

MEDIA = {"pdf": "application/pdf", "markdown": "text/markdown", "docx":
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
EXT = {"pdf": "pdf", "markdown": "md", "docx": "docx"}


def view(session: Session, p: Policy) -> dict:
    ent = session.get(Entite, p.entite_id) if p.entite_id else None
    return {
        "id": p.id, "titre": p.titre, "version": p.version, "statut": p.statut,
        "entite_id": p.entite_id, "portee": f"Entite : {ent.nom}" if ent else "Globale (toutes les entites)",
        "format_source": p.format_source, "source_nom": p.source_nom, "nb_pages": p.nb_pages,
        "sha256": p.sha256, "depose_par": p.depose_par, "depose_le": p.depose_le,
        "date_version": p.date_version, "en_attente_depot": is_pending(p.fichier_ref),
    }


def _get(session: Session, policy_id: int, scope: Scope = GLOBAL) -> Policy:
    p = session.get(Policy, policy_id)
    if not p or not p.fichier_ref or not scope.allows_policy(p.entite_id):
        raise HTTPException(404, "Charte introuvable")
    return p


def read_pdf(p: Policy) -> bytes:
    """PDF normalise de la charte, avec controle d'integrite (empreinte enregistree au depot)."""
    try:
        data = read_document(p.fichier_ref)
    except StorageError as exc:
        raise HTTPException(503, f"Charte inaccessible sur le stockage : {exc}") from exc
    if sha256_hex(data) != p.sha256:
        raise HTTPException(500, "Integrite de la charte compromise (empreinte differente)")
    return data


@router.get("")
def list_policies(session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    rows = [p for p in session.exec(select(Policy).where(Policy.fichier_ref.is_not(None))).all() if scope.allows_policy(p.entite_id)]
    rows.sort(key=lambda p: (p.statut != "active", p.entite_id is not None, -(p.id or 0)))
    return [view(session, p) for p in rows]


@router.get("/applicable")
def applicable(entite_id: int | None = None, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Charte qui serait jointe a une remise pour cette entite (entite, puis parents, puis globale)."""
    if entite_id is not None and not scope.allows(entite_id):
        return None  # entite hors perimetre : rien n'est revele
    p = charte.resolve_policy(session, entite_id)
    return view(session, p) if p else None


@router.post("", status_code=201)
def upload_policy(
    file: UploadFile = File(...),
    titre: str = Form("Charte informatique"),
    entite_id: int | None = Form(None),
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    titre = (titre or "").strip()[:120] or "Charte informatique"
    if entite_id is not None and not session.get(Entite, entite_id):
        raise HTTPException(404, "Entite introuvable")
    raw = file.file.read(charte.MAX_BYTES + 1)
    try:
        fmt, pdf, pages = charte.normalize(file.filename or "", raw, titre)
    except charte.CharteError as exc:
        raise HTTPException(400, str(exc)) from exc

    now = datetime.utcnow()
    # La version precedente de la meme portee est archivee dans la meme transaction.
    for old in session.exec(charte._scope(select(Policy).where(Policy.statut == "active"), entite_id)).all():
        old.statut = "archivee"
        session.add(old)
    session.flush()
    p = Policy(
        version=charte.next_version(session, entite_id), titre=titre, entite_id=entite_id,
        format_source=fmt, statut="active", sha256=sha256_hex(pdf), source_sha256=sha256_hex(raw),
        source_nom=os.path.basename(file.filename or "")[:200] or None, nb_pages=pages,
        depose_par=account.username, depose_le=now, date_version=now.date(),
    )
    session.add(p)
    session.flush()
    refs = []
    try:
        p.fichier_ref = store_document(f"chartes/{p.id}/charte.pdf", pdf)
        refs.append(p.fichier_ref)
        p.source_ref = store_document(f"chartes/{p.id}/origine.{EXT[fmt]}", raw)
        refs.append(p.source_ref)
        session.add(p)
        session.commit()
    except Exception as exc:  # noqa: BLE001  (echec de stockage : rien n'est conserve, l'ancienne charte reste active)
        session.rollback()
        for ref in refs:
            delete_document(ref)
        raise HTTPException(503, f"Depot de la charte impossible : {exc}") from exc
    session.refresh(p)
    return view(session, p)


@router.get("/{policy_id}/page/{page}")
def page_image(policy_id: int, page: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    p = _get(session, policy_id, scope)
    if page < 1 or page > (p.nb_pages or 0):
        raise HTTPException(404, "Page introuvable")
    return Response(charte.render_page_png(read_pdf(p), page - 1), media_type="image/png")


@router.get("/{policy_id}/fichier")
def download_pdf(policy_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    p = _get(session, policy_id, scope)
    return Response(read_pdf(p), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="charte_{p.id}_{p.version}.pdf"'})


@router.get("/{policy_id}/source")
def download_source(policy_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    p = _get(session, policy_id, scope)
    try:
        data = read_document(p.source_ref)
    except StorageError as exc:
        raise HTTPException(503, f"Fichier inaccessible sur le stockage : {exc}") from exc
    if sha256_hex(data) != p.source_sha256:
        raise HTTPException(500, "Integrite du fichier compromise (empreinte differente)")
    return Response(data, media_type=MEDIA.get(p.format_source, "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="charte_{p.id}_{p.version}_origine.{EXT.get(p.format_source, "bin")}"'})


@router.post("/{policy_id}/archiver")
def archive_policy(policy_id: int, session: Session = Depends(get_session)):
    """Retire la charte : la portee retombe sur la charte de l'entite parente, ou sur la charte globale."""
    p = _get(session, policy_id)
    if p.statut != "active":
        raise HTTPException(409, "Cette charte est deja archivee")
    p.statut = "archivee"
    session.add(p)
    session.commit()
    return view(session, p)
