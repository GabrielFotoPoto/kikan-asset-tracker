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

"""Depart d'un salarie et restitution signee du materiel (A.5.11).

Accessible aux roles RH et informatique (la restitution peut etre conduite par
l'un ou l'autre ; la remise a l'arrivee reste reservee a l'informatique).
"""
import hashlib
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from ..audit import audit
from ..auth import client_ip, get_current_account, require_roles, writer_guard
from ..scope import Scope, scope_dep, visible_user
from ..db import get_session
from ..models import (
    Account,
    Asset,
    AssetStatus,
    Assignment,
    AssignmentAsset,
    EmployeeStatus,
    Entite,
    MOTIFS_NON_RESTITUTION,
    Signature,
    User,
)
from ..pdf_template import load_template
from ..docname import heure_locale, nom_document
from ..pdfgen import build_receipt
from ..signature_image import (
    HANDWRITTEN_REQUIRED,
    MAX_B64_CHARS,
    SignatureImageError,
    prepare_signature,
)
from ..signing import seal_pdf
from ..filestore import meta_for, store_document

router = APIRouter(
    prefix="/lifecycle", tags=["lifecycle"],
    dependencies=[Depends(writer_guard("rh", "informatique"))],
)


class DepartRequest(BaseModel):
    date_sortie: date


class RestitutionRequest(BaseModel):
    """Le signataire n'est PAS fourni par le client : il est deduit de la fiche du salarie."""
    user_id: int
    asset_ids: list[int] | None = None  # None = tout le materiel detenu
    consent: bool = False
    signature_image: str | None = Field(default=None, max_length=MAX_B64_CHARS)
    strokes: int | None = Field(default=None, ge=0, le=1000)
    duration_ms: int | None = Field(default=None, ge=0, le=600000)


class NonRestitueRequest(BaseModel):
    user_id: int
    asset_ids: list[int] = Field(min_length=1, max_length=50)
    motif: str

    @field_validator("motif")
    @classmethod
    def _valider_motif(cls, v: str) -> str:
        if v not in MOTIFS_NON_RESTITUTION:
            raise ValueError(f"Motif invalide : doit etre parmi {', '.join(MOTIFS_NON_RESTITUTION)}")
        return v


def _cloturer_si_vide(session: Session, user: User) -> bool:
    """Si le salarie etait en_depart et n'a plus aucun actif affecte, il passe au statut sorti."""
    if user.statut == EmployeeStatus.en_depart and not _holdings(session, user.id):
        user.statut = EmployeeStatus.sorti
        user.maj_le = datetime.utcnow()
        session.add(user)
        return True
    return False


def _holdings(session: Session, user_id: int) -> list[tuple[Asset, int]]:
    """Actifs encore affectes a ce salarie, avec l'id d'affectation associe."""
    assignments = session.exec(
        select(Assignment).where(Assignment.user_id == user_id)
    ).all()
    aids = [a.id for a in assignments]
    if not aids:
        return []
    links = session.exec(
        select(AssignmentAsset).where(AssignmentAsset.assignment_id.in_(aids))
    ).all()
    result = []
    for link in links:
        asset = session.get(Asset, link.asset_id)
        if asset and asset.statut == AssetStatus.affecte:
            result.append((asset, link.assignment_id))
    return result


@router.get("/holdings/{user_id}", response_model=list[Asset])
def holdings(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    visible_user(session, scope, user_id)
    return [a for a, _ in _holdings(session, user_id)]


@router.post("/depart/{user_id}")
def declarer_depart(user_id: int, data: DepartRequest, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    user = visible_user(session, scope, user_id)
    user.statut = EmployeeStatus.en_depart
    user.date_sortie = data.date_sortie
    user.maj_le = datetime.utcnow()
    session.add(user)
    session.commit()
    held = [a for a, _ in _holdings(session, user_id)]
    return {
        "user_id": user_id,
        "statut": user.statut,
        "date_sortie": str(user.date_sortie),
        "materiel_a_recuperer": [
            {"id": a.id, "identifiant_interne": a.identifiant_interne,
             "type": a.type, "marque": a.marque, "modele": a.modele}
            for a in held
        ],
    }


@router.get("/recap/{user_id}")
def recap(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Recapitulatif affiche sur la tablette avant la signature de la restitution."""
    user = visible_user(session, scope, user_id)
    entite = session.get(Entite, user.entite_id) if user.entite_id else None
    return {
        "signature_obligatoire": HANDWRITTEN_REQUIRED,
        "salarie": {"prenom": user.prenom, "nom": user.nom, "matricule": user.matricule,
                    "service": user.service, "entite": entite.nom if entite else None,
                    "statut": user.statut.value if hasattr(user.statut, "value") else user.statut},
        "materiel": [
            {"id": a.id, "type": a.type, "marque": a.marque, "modele": a.modele,
             "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne}
            for a, _ in _holdings(session, user_id)
        ],
    }


@router.post("/restituer", response_model=Signature, status_code=201)
def restituer(
    data: RestitutionRequest,
    request: Request,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
    scope: Scope = Depends(scope_dep),
):
    user = visible_user(session, scope, data.user_id)
    # Verrou sur le salarie : deux restitutions simultanees se suivent, la seconde ne voit plus que le materiel restant.
    session.exec(select(User).where(User.id == data.user_id).with_for_update().execution_options(populate_existing=True)).first()

    held = _holdings(session, data.user_id)
    if data.asset_ids is not None:
        held = [(a, aid) for a, aid in held if a.id in data.asset_ids]
    if not held:
        raise HTTPException(400, "Aucun materiel a restituer pour ce salarie")
    try:
        signature_png, image_meta, methode = prepare_signature(data.consent, data.signature_image)
    except SignatureImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    signataire = f"{user.prenom} {user.nom}".strip()  # deduit de la fiche, jamais saisi librement

    entite = session.get(Entite, user.entite_id) if user.entite_id else None
    assets = [a for a, _ in held]
    assignment_ids = {aid for _, aid in held}

    now = datetime.utcnow()
    template = load_template(session)
    pdf = build_receipt(
        user={"nom": user.nom, "prenom": user.prenom, "matricule": user.matricule},
        entite_nom=entite.nom if entite else None,
        assets=[{"type": a.type, "marque": a.marque, "modele": a.modele,
                 "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne}
                for a in assets],
        title="Accuse de restitution de materiel",
        kind="restitution",
        signature_png=signature_png,
        signataire=signataire,
        temoin=account.username,
        signed_at=now,
        template=template,
    )
    sealed = seal_pdf(pdf, reason="Restitution de materiel", name=signataire)
    empreinte = hashlib.sha256(sealed).hexdigest()

    # Rangement par annee (AAAA/...) sur le stockage actif (volume, partage SMB ou WebDAV).
    reference = store_document(nom_document(session, user, now), sealed,
                               meta_for("Restitution", heure_locale(now).year, None, entite, user, now))

    # Marque les actifs rendus, avec leur date de retour (par actif : l'affectation ne se cloture que si tout est rendu).
    for asset, aid in held:
        asset.statut = AssetStatus.rendu
        asset.maj_le = now
        session.add(asset)
        link = session.get(AssignmentAsset, (aid, asset.id))
        if link is not None:
            link.date_retour = now
            session.add(link)

    # Cloture les affectations entierement restituees.
    for aid in assignment_ids:
        links = session.exec(
            select(AssignmentAsset).where(AssignmentAsset.assignment_id == aid)
        ).all()
        if all(session.get(Asset, l.asset_id).statut != AssetStatus.affecte for l in links):
            assignment = session.get(Assignment, aid)
            assignment.date_restitution = now
            assignment.statut = "restitue"
            session.add(assignment)

    signature = Signature(
        assignment_id=sorted(assignment_ids)[0],
        signataire=signataire,
        methode=methode,
        horodatage=now,
        empreinte_doc=empreinte,
        # Faisceau de preuves : l'image n'est PAS stockee en base (elle reste dans le PDF scelle).
        audit_json={"type": "restitution", "assignments": sorted(assignment_ids),
                    "assets": [a.id for a in assets], "temoin": account.username,
                    "ip": client_ip(request), "user_agent": (request.headers.get("user-agent") or "")[:200],
                    "image": image_meta, "traits": data.strokes, "duree_ms": data.duration_ms},
        ged_reference=reference,
    )
    session.add(signature)

    session.flush()
    _cloturer_si_vide(session, user)

    session.commit()
    session.refresh(signature)
    return signature


def _restant(session: Session, user_id: int, just_returned: list[Asset]) -> list[Asset]:
    returned_ids = {a.id for a in just_returned}
    return [a for a, _ in _holdings(session, user_id) if a.id not in returned_ids]


def _marquer_actifs_non_restitues(
    session: Session, cibles: list[tuple[Asset, int]], motif: str, now: datetime
) -> set[int]:
    """Passe les actifs verrouilles au statut non_restitue et renseigne le constat sur les lignes d'affectation."""
    assignment_ids: set[int] = set()
    for asset, assignment_id in cibles:
        asset.statut = AssetStatus.non_restitue
        asset.maj_le = now
        session.add(asset)
        assignment_ids.add(assignment_id)
        link = session.get(AssignmentAsset, (assignment_id, asset.id))
        if link is not None:
            link.non_restitue_le = now
            link.motif_non_restitution = motif
            session.add(link)
    return assignment_ids


def _cloturer_affectations_soldees(session: Session, assignment_ids: set[int]) -> None:
    """Marque restitue les affectations dont plus aucun actif n'est au statut affecte (sans renseigner date_restitution)."""
    for asg_id in assignment_ids:
        links = session.exec(select(AssignmentAsset).where(AssignmentAsset.assignment_id == asg_id)).all()
        if all(session.get(Asset, l.asset_id).statut != AssetStatus.affecte for l in links):
            assignment = session.get(Assignment, asg_id)
            if assignment and assignment.statut != "restitue":
                assignment.statut = "restitue"
                session.add(assignment)


@router.post("/non-restitue", dependencies=[Depends(require_roles("informatique"))])
def constat_non_restitue(
    data: NonRestitueRequest,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
    scope: Scope = Depends(scope_dep),
):
    """Constat d'impossibilite de restitution d'actifs (reserve a l'informatique seule)."""
    user = visible_user(session, scope, data.user_id)
    # Verrou sur le salarie : deux constats/restitutions simultanes se suivent.
    session.exec(select(User).where(User.id == data.user_id).with_for_update().execution_options(populate_existing=True)).first()
    if user.statut != EmployeeStatus.en_depart:
        raise HTTPException(409, "Le salarie doit etre en cours de depart")

    held_map = {a.id: (a, aid) for a, aid in _holdings(session, data.user_id)}
    for aid in data.asset_ids:
        if aid not in held_map:
            raise HTTPException(409, "Materiel non detenu par ce salarie ou deja traite")

    ids_sorted = sorted(set(data.asset_ids))
    locked = {
        a.id: a
        for a in session.exec(select(Asset).where(Asset.id.in_(ids_sorted)).order_by(Asset.id).with_for_update()).all()
    }
    now = datetime.utcnow()
    cibles = [(locked[aid], held_map[aid][1]) for aid in ids_sorted]
    assignment_ids = _marquer_actifs_non_restitues(session, cibles, data.motif, now)
    _cloturer_affectations_soldees(session, assignment_ids)

    session.flush()
    _cloturer_si_vide(session, user)
    session.commit()

    statut_str = user.statut.value if hasattr(user.statut, "value") else str(user.statut)
    audit(account.username, "constat_non_restitution", target=f"user:{user.id}",
          detail=f"{len(ids_sorted)} actif(s), motif:{data.motif}")
    return {
        "user_id": user.id,
        "statut_salarie": statut_str,
        "actifs_constates": ids_sorted,
        "non_restitue_le": now.isoformat(),
    }


@router.post("/depart/{user_id}/cloturer")
def cloturer_depart(
    user_id: int,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
    scope: Scope = Depends(scope_dep),
):
    """Cloture d'un depart sans materiel (ou dont tout le materiel a ete traite). RH ou informatique."""
    user = visible_user(session, scope, user_id)
    session.exec(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)).first()

    if user.statut != EmployeeStatus.en_depart:
        raise HTTPException(409, "Le salarie doit etre en cours de depart pour etre cloture")

    held = _holdings(session, user_id)
    if held:
        raise HTTPException(409, f"Impossible de cloturer : il reste {len(held)} materiel(s) affecte(s)")

    _cloturer_si_vide(session, user)
    session.commit()

    statut_str = user.statut.value if hasattr(user.statut, "value") else str(user.statut)
    audit(account.username, "depart_cloture", target=f"user:{user.id}", detail="sans materiel")

    return {
        "user_id": user.id,
        "statut": statut_str,
    }
