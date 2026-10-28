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

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..audit import audit
from ..auth import client_ip, get_current_account, writer_guard
from ..db import get_session
from ..models import (
    Account,
    Asset,
    AssetStatus,
    Assignment,
    AssignmentAsset,
    Entite,
    Policy,
    Signature,
    User,
)
from ..pdfgen import build_receipt
from ..signature_image import (
    HANDWRITTEN_REQUIRED,
    MAX_B64_CHARS,
    SignatureImageError,
    prepare_signature,
)
from ..signing import seal_pdf
from ..filestore import read_document, sha256_hex, store_document

router = APIRouter(
    prefix="/assignments", tags=["assignments"],
    dependencies=[Depends(writer_guard("informatique"))],
)


class AssignmentCreate(BaseModel):
    user_id: int
    asset_ids: list[int]
    policy_id: int | None = None
    cree_par: str | None = None


class SignRequest(BaseModel):
    """Signature de la remise. Le signataire n'est PAS fourni par le client : il est deduit de la
    fiche du salarie (un eventuel champ 'signataire' envoye est ignore)."""
    consent: bool = False
    signature_image: str | None = Field(default=None, max_length=MAX_B64_CHARS)
    note: str | None = Field(default=None, max_length=500)
    strokes: int | None = Field(default=None, ge=0, le=1000)      # nombre de traits (preuve)
    duration_ms: int | None = Field(default=None, ge=0, le=600000)  # duree du trace (preuve)


def _assets_of(session: Session, assignment_id: int) -> list[Asset]:
    links = session.exec(
        select(AssignmentAsset).where(AssignmentAsset.assignment_id == assignment_id)
    ).all()
    return [session.get(Asset, link.asset_id) for link in links]


@router.post("", response_model=Assignment, status_code=201)
def create_assignment(data: AssignmentCreate, session: Session = Depends(get_session)):
    user = session.get(User, data.user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    if not data.asset_ids:
        raise HTTPException(400, "Au moins un actif est requis")

    assets = []
    for aid in data.asset_ids:
        asset = session.get(Asset, aid)
        if not asset:
            raise HTTPException(404, f"Actif {aid} introuvable")
        if asset.statut == AssetStatus.affecte:
            raise HTTPException(409, f"Actif {aid} deja affecte")
        assets.append(asset)

    assignment = Assignment(
        user_id=data.user_id,
        policy_id=data.policy_id,
        cree_par=data.cree_par,
        statut="en_cours",
    )
    session.add(assignment)
    session.commit()
    session.refresh(assignment)

    for asset in assets:
        asset.statut = AssetStatus.affecte
        asset.maj_le = datetime.utcnow()
        session.add(asset)
        session.add(AssignmentAsset(assignment_id=assignment.id, asset_id=asset.id))
    session.commit()
    session.refresh(assignment)
    return assignment


@router.get("", response_model=list[Assignment])
def list_assignments(session: Session = Depends(get_session), user_id: int | None = None):
    stmt = select(Assignment)
    if user_id is not None:
        stmt = stmt.where(Assignment.user_id == user_id)
    return session.exec(stmt).all()


@router.get("/{assignment_id}", response_model=Assignment)
def get_assignment(assignment_id: int, session: Session = Depends(get_session)):
    obj = session.get(Assignment, assignment_id)
    if not obj:
        raise HTTPException(404, "Affectation introuvable")
    return obj


def _already_signed(session: Session, assignment_id: int) -> bool:
    """Une remise ne se signe qu'une fois (les restitutions partagent l'identifiant d'affectation)."""
    sigs = session.exec(select(Signature).where(Signature.assignment_id == assignment_id)).all()
    return any((s.audit_json or {}).get("type") != "restitution" for s in sigs)


@router.get("/{assignment_id}/recap")
def recap(assignment_id: int, session: Session = Depends(get_session)):
    """Recapitulatif affiche sur la tablette avant signature."""
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Affectation introuvable")
    user = session.get(User, assignment.user_id)
    entite = session.get(Entite, user.entite_id) if user and user.entite_id else None
    policy = session.get(Policy, assignment.policy_id) if assignment.policy_id else None
    return {
        "affectation_id": assignment.id,
        "deja_signe": _already_signed(session, assignment_id),
        "signature_obligatoire": HANDWRITTEN_REQUIRED,
        "salarie": {"prenom": user.prenom, "nom": user.nom, "matricule": user.matricule,
                    "service": user.service, "entite": entite.nom if entite else None},
        "materiel": [
            {"type": a.type, "marque": a.marque, "modele": a.modele,
             "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne}
            for a in _assets_of(session, assignment_id)
        ],
        "charte": {"version": policy.version, "texte": policy.texte} if policy else None,
    }


@router.post("/{assignment_id}/sign", response_model=Signature, status_code=201)
def sign_assignment(
    assignment_id: int,
    data: SignRequest,
    request: Request,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Affectation introuvable")
    if _already_signed(session, assignment_id):
        raise HTTPException(409, "Cette remise est deja signee")
    try:
        signature_png, image_meta, methode = prepare_signature(data.consent, data.signature_image)
    except SignatureImageError as exc:
        raise HTTPException(400, str(exc)) from exc

    user = session.get(User, assignment.user_id)
    signataire = f"{user.prenom} {user.nom}".strip()  # deduit de la fiche, jamais saisi librement
    entite = session.get(Entite, user.entite_id) if user and user.entite_id else None
    assets = _assets_of(session, assignment_id)
    policy = session.get(Policy, assignment.policy_id) if assignment.policy_id else None

    user_d = {
        "nom": user.nom, "prenom": user.prenom, "matricule": user.matricule,
    }
    assets_d = [
        {
            "type": a.type, "marque": a.marque, "modele": a.modele,
            "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne,
        }
        for a in assets
    ]

    now = datetime.utcnow()
    pdf = build_receipt(
        user=user_d,
        entite_nom=entite.nom if entite else None,
        assets=assets_d,
        policy_text=policy.texte if policy else None,
        kind="remise",
        signature_png=signature_png,
        signataire=signataire,
        temoin=account.username,
        signed_at=now,
    )
    sealed = seal_pdf(pdf, reason="Remise de materiel", name=signataire)
    empreinte = hashlib.sha256(sealed).hexdigest()

    # Rangement par annee (AAAA/...) sur le stockage actif (volume, partage SMB ou WebDAV).
    reference = store_document(f"{now.year}/remise_{assignment_id}_{now:%Y%m%d%H%M%S}.pdf", sealed)

    signature = Signature(
        assignment_id=assignment_id,
        signataire=signataire,
        methode=methode,
        horodatage=now,
        empreinte_doc=empreinte,
        # Faisceau de preuves : l'image elle-meme n'est PAS stockee en base (elle reste dans le PDF scelle).
        audit_json={
            "type": "remise", "note": data.note, "nb_actifs": len(assets),
            "temoin": account.username, "ip": client_ip(request),
            "user_agent": (request.headers.get("user-agent") or "")[:200],
            "image": image_meta, "traits": data.strokes, "duree_ms": data.duration_ms,
        },
        ged_reference=reference,
    )
    session.add(signature)
    session.commit()
    session.refresh(signature)
    return signature


@router.get("/{assignment_id}/document")
def get_document(assignment_id: int, session: Session = Depends(get_session)):
    sig = session.exec(
        select(Signature).where(Signature.assignment_id == assignment_id)
    ).first()
    if not sig or not sig.ged_reference:
        raise HTTPException(404, "Document scelle introuvable")
    data = read_document(sig.ged_reference)
    # Detection d'alteration du stockage : l'empreinte enregistree a la signature doit correspondre.
    if sig.empreinte_doc and sha256_hex(data) != sig.empreinte_doc:
        audit("systeme", "document_altere", target=sig.ged_reference, status=500)
        raise HTTPException(500, "Integrite du document non verifiee (empreinte differente)")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="remise_{assignment_id}.pdf"'})
