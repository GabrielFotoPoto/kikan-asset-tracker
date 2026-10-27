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
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..models import (
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
from ..signing import seal_pdf

router = APIRouter(
    prefix="/assignments", tags=["assignments"],
    dependencies=[Depends(writer_guard("informatique"))],
)

ARCHIVE_DIR = os.environ.get("KIKAN_ARCHIVE_DIR", "/archive")


class AssignmentCreate(BaseModel):
    user_id: int
    asset_ids: list[int]
    policy_id: int | None = None
    cree_par: str | None = None


class SignRequest(BaseModel):
    signataire: str
    methode: str = "manuscrite_ecran"
    note: str | None = None


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


@router.post("/{assignment_id}/sign", response_model=Signature, status_code=201)
def sign_assignment(
    assignment_id: int, data: SignRequest, session: Session = Depends(get_session)
):
    assignment = session.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Affectation introuvable")

    user = session.get(User, assignment.user_id)
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

    pdf = build_receipt(
        user=user_d,
        entite_nom=entite.nom if entite else None,
        assets=assets_d,
        policy_text=policy.texte if policy else None,
    )
    sealed = seal_pdf(pdf, reason="Remise de materiel", name=data.signataire)
    empreinte = hashlib.sha256(sealed).hexdigest()

    now = datetime.utcnow()
    year_dir = os.path.join(ARCHIVE_DIR, str(now.year))
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"remise_{assignment_id}_{now:%Y%m%d%H%M%S}.pdf")
    with open(path, "wb") as f:
        f.write(sealed)

    signature = Signature(
        assignment_id=assignment_id,
        signataire=data.signataire,
        methode=data.methode,
        horodatage=now,
        empreinte_doc=empreinte,
        audit_json={"note": data.note, "nb_actifs": len(assets)},
        ged_reference=path,
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
    if not sig or not sig.ged_reference or not os.path.exists(sig.ged_reference):
        raise HTTPException(404, "Document scelle introuvable")
    return FileResponse(sig.ged_reference, media_type="application/pdf")
