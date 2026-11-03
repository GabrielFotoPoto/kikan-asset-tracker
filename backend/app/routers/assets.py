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

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from ..auth import get_current_account, writer_guard
from ..asset_catalog import AssetCatalog
from ..audit import audit
from ..catalogs import canonical_type
from ..db import get_session
from ..models import Account, Asset, AssetBase, AssetStatus, AssetType, AssignmentAsset, EcheanceReport, Entite
from ..scope import Scope, scope_dep
from ..rules import audit_change, changed_fields, count, refuse_delete, taken

router = APIRouter(
    prefix="/assets", tags=["assets"],
    dependencies=[Depends(writer_guard("informatique"))],
)


@router.get("", response_model=list[Asset])
def list_assets(
    session: Session = Depends(get_session),
    entite_id: int | None = None,
    statut: AssetStatus | None = None,
    scope: Scope = Depends(scope_dep),
):
    stmt = scope.where(select(Asset), Asset.entite_id)
    if entite_id is not None:
        stmt = stmt.where(Asset.entite_id == entite_id)
    if statut is not None:
        stmt = stmt.where(Asset.statut == statut)
    return session.exec(stmt).all()


@router.get("/retours-stock")
def retours_stock(session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Materiels en stock qui ont deja ete remis puis restitues : `retour_le` est la date de leur dernier retour.

    Calcule a partir de l'historique des affectations (rien a saisir) ; sert a reperer ce qu'il reste a decider
    (remettre en circulation ou reformer). Un materiel qui repart en affectation ou est reforme n'y figure plus."""
    stmt = (
        select(Asset.id, func.max(AssignmentAsset.date_retour))
        .join(AssignmentAsset, AssignmentAsset.asset_id == Asset.id)
        .where(Asset.statut == AssetStatus.stock, AssignmentAsset.date_retour.is_not(None))
        .group_by(Asset.id)
    )
    stmt = scope.where(stmt, Asset.entite_id)
    return [{"asset_id": asset_id, "retour_le": retour.isoformat()} for asset_id, retour in session.exec(stmt).all()]


@router.get("/catalogue/marques")
def catalogue_marques(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    detail: bool = False,
    session: Session = Depends(get_session),
):
    """Marques deja saisies : recherche partielle (casse et accents ignores), plus utilisees d'abord.

    detail=true renvoie [{nom, count}] ; sinon une simple liste de noms."""
    items = AssetCatalog(session).suggest_marques(q, limit)
    return items if detail else [i["nom"] for i in items]


@router.get("/catalogue/types", response_model=list[str])
def catalogue_types(session: Session = Depends(get_session)):
    """Types d'actifs actifs (liste de parametrage) pour les menus."""
    rows = session.exec(select(AssetType.nom).where(AssetType.actif == True)).all()  # noqa: E712
    return sorted(rows, key=str.lower)


@router.get("/catalogue/modeles")
def catalogue_modeles(
    marque: str | None = None,
    type: str | None = None,
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    detail: bool = False,
    session: Session = Depends(get_session),
):
    """Modeles deja saisis, filtres par marque ; ceux deja vus avec ce type passent en premier."""
    items = AssetCatalog(session).suggest_modeles(marque, type, q, limit)
    return items if detail else [i["nom"] for i in items]


def _canonical_names(session: Session, data: AssetBase) -> None:
    """Marque et modele : a la casse, aux accents et aux espaces pres, reprend la graphie la plus utilisee."""
    catalog = AssetCatalog(session)
    data.marque = catalog.canon_marque(data.marque)
    data.modele = catalog.canon_modele(data.marque, data.modele)


def _check_asset(session: Session, data: AssetBase, own_id: int | None) -> None:
    taken(session, Asset, Asset.numero_serie, data.numero_serie, own_id, "Numero de serie")
    taken(session, Asset, Asset.identifiant_interne, data.identifiant_interne, own_id, "Identifiant interne")
    if data.entite_id is not None and not session.get(Entite, data.entite_id):
        raise HTTPException(400, "Entite inconnue")


@router.post("", response_model=Asset, status_code=201)
def create_asset(data: AssetBase, session: Session = Depends(get_session)):
    if data.statut in (AssetStatus.affecte, AssetStatus.rendu):
        raise HTTPException(409, "Le statut affecte ou rendu s'obtient par la remise ou la restitution")
    _check_asset(session, data, None)
    data.type = canonical_type(session, data.type)
    _canonical_names(session, data)
    obj = Asset.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{asset_id}", response_model=Asset)
def get_asset(asset_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    obj = session.get(Asset, asset_id)
    if not obj or not scope.allows(obj.entite_id):
        raise HTTPException(404, "Actif introuvable")
    return obj


@router.put("/{asset_id}", response_model=Asset)
def update_asset(
    asset_id: int, data: AssetBase,
    session: Session = Depends(get_session), account: Account = Depends(get_current_account),
):
    obj = session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Actif introuvable")
    _check_asset(session, data, obj.id)
    data.type = canonical_type(session, data.type)
    _canonical_names(session, data)
    new = data.model_dump()
    # Les statuts affecte et rendu viennent de la remise et de la restitution, pas d'une saisie manuelle.
    if new["statut"] != obj.statut:
        if obj.statut == AssetStatus.affecte:
            raise HTTPException(409, "Cet actif est affecte : il se libere par la restitution du salarie")
        if new["statut"] in (AssetStatus.affecte, AssetStatus.rendu):
            raise HTTPException(409, "Le statut affecte ou rendu s'obtient par la remise ou la restitution")
    fields = changed_fields(obj, new)
    for key, value in new.items():
        setattr(obj, key, value)
    obj.maj_le = datetime.utcnow()
    session.add(obj)
    session.commit()
    session.refresh(obj)
    audit_change(account.username, "assets", obj.id, fields)
    return obj


class ReformeLot(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    simulation: bool = True   # vrai : ne change rien, annonce seulement ce qui serait reforme ou refuse


@router.post("/reforme-lot")
def reform_assets_batch(
    data: ReformeLot, session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep), account: Account = Depends(get_current_account),
):
    """Passe plusieurs materiels au statut `reforme` en une fois (decision de mise au rebut apres un retour en stock).

    Un materiel actuellement remis (affecte) se libere par la restitution : il est refuse, comme les materiels deja reformes
    ou hors du perimetre. En simulation (par defaut), rien ne change : la reponse sert de recapitulatif."""
    ids = list(dict.fromkeys(data.ids))
    reformables: list[Asset] = []
    refuses: list[dict] = []
    for asset_id in ids:
        obj = session.get(Asset, asset_id)
        if not obj or not scope.allows(obj.entite_id):
            refuses.append({"id": asset_id, "raison": "Actif introuvable"})
        elif obj.statut == AssetStatus.affecte:
            refuses.append({"id": asset_id, "raison": "Affecte : il se libere par la restitution du salarie", "identifiant": obj.identifiant_interne})
        elif obj.statut == AssetStatus.reforme:
            refuses.append({"id": asset_id, "raison": "Deja reforme", "identifiant": obj.identifiant_interne})
        else:
            reformables.append(obj)
    ids_ok = [o.id for o in reformables]
    apercu = [
        {"id": o.id, "identifiant": o.identifiant_interne, "type": o.type, "marque": o.marque, "modele": o.modele, "numero_serie": o.numero_serie, "statut": o.statut}
        for o in reformables
    ]
    if not data.simulation:
        now = datetime.utcnow()
        for obj in reformables:
            obj.statut = AssetStatus.reforme
            obj.maj_le = now
            session.add(obj)
        session.commit()
        for asset_id in ids_ok:
            audit_change(account.username, "assets", asset_id, ["statut"])
    return {"simulation": data.simulation, "reformes": ids_ok, "refuses": refuses, "apercu": apercu if data.simulation else []}


class SuppressionLot(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    simulation: bool = True   # vrai : ne supprime rien, annonce seulement ce qui serait supprime ou refuse


@router.post("/suppression-lot")
def delete_assets_batch(
    data: SuppressionLot, session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep), account: Account = Depends(get_current_account),
):
    """Suppression de plusieurs actifs en une fois, avec les memes garde-fous que la suppression unitaire.

    Un actif deja remis (affectation) ou hors du perimetre du compte est refuse et liste avec sa raison ; les autres sont
    supprimes ensemble (une seule validation). En simulation (par defaut), rien n'est supprime : la reponse sert de recapitulatif."""
    ids = list(dict.fromkeys(data.ids))
    supprimables: list[Asset] = []
    refuses: list[dict] = []
    for asset_id in ids:
        obj = session.get(Asset, asset_id)
        if not obj or not scope.allows(obj.entite_id):
            refuses.append({"id": asset_id, "raison": "Actif introuvable"})
        elif count(session, AssignmentAsset, AssignmentAsset.asset_id == obj.id):
            refuses.append({"id": asset_id, "raison": "Deja remis : passez-le au statut reforme", "identifiant": obj.identifiant_interne})
        else:
            supprimables.append(obj)
    supprimes_ids = [o.id for o in supprimables]
    apercu = [
        {"id": o.id, "identifiant": o.identifiant_interne, "type": o.type, "marque": o.marque, "modele": o.modele, "numero_serie": o.numero_serie}
        for o in supprimables
    ]
    if not data.simulation:
        for obj in supprimables:
            for report in session.exec(select(EcheanceReport).where(EcheanceReport.asset_id == obj.id)).all():
                session.delete(report)
            session.flush()
            session.delete(obj)
        session.commit()
        for asset_id in supprimes_ids:
            audit(account.username, "suppression", target=f"assets/{asset_id}", detail="suppression en lot")
    return {
        "simulation": data.simulation,
        "supprimes": supprimes_ids,
        "refuses": refuses,
        "apercu": apercu if data.simulation else [],
    }


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, session: Session = Depends(get_session)):
    obj = session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Actif introuvable")
    refuse_delete(
        "cet actif",
        {"affectation(s)": count(session, AssignmentAsset, AssignmentAsset.asset_id == obj.id)},
        "Un actif deja remis se conserve : passez-le au statut reforme.",
    )
    for report in session.exec(select(EcheanceReport).where(EcheanceReport.asset_id == obj.id)).all():
        session.delete(report)   # l'historique des reports d'echeance d'un actif jamais remis part avec lui
    session.flush()
    session.delete(obj)
    session.commit()
