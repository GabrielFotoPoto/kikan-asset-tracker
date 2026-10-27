from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..models import Asset, AssetBase, AssetStatus

router = APIRouter(
    prefix="/assets", tags=["assets"],
    dependencies=[Depends(writer_guard("informatique"))],
)


@router.get("", response_model=list[Asset])
def list_assets(
    session: Session = Depends(get_session),
    entite_id: int | None = None,
    statut: AssetStatus | None = None,
):
    stmt = select(Asset)
    if entite_id is not None:
        stmt = stmt.where(Asset.entite_id == entite_id)
    if statut is not None:
        stmt = stmt.where(Asset.statut == statut)
    return session.exec(stmt).all()


@router.get("/catalogue/marques", response_model=list[str])
def catalogue_marques(
    q: str | None = Query(default=None), session: Session = Depends(get_session)
):
    """Autocompletion des marques deja saisies."""
    rows = session.exec(select(Asset.marque).distinct()).all()
    values = sorted({m for m in rows if m})
    if q:
        values = [m for m in values if q.lower() in m.lower()]
    return values


@router.get("/catalogue/modeles", response_model=list[str])
def catalogue_modeles(
    marque: str | None = None,
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Autocompletion des modeles, optionnellement filtree par marque."""
    stmt = select(Asset.modele, Asset.marque).distinct()
    rows = session.exec(stmt).all()
    values = sorted({mo for mo, ma in rows if mo and (marque is None or ma == marque)})
    if q:
        values = [m for m in values if q.lower() in m.lower()]
    return values


@router.post("", response_model=Asset, status_code=201)
def create_asset(data: AssetBase, session: Session = Depends(get_session)):
    obj = Asset.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{asset_id}", response_model=Asset)
def get_asset(asset_id: int, session: Session = Depends(get_session)):
    obj = session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Actif introuvable")
    return obj


@router.put("/{asset_id}", response_model=Asset)
def update_asset(asset_id: int, data: AssetBase, session: Session = Depends(get_session)):
    obj = session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Actif introuvable")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    obj.maj_le = datetime.utcnow()
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, session: Session = Depends(get_session)):
    obj = session.get(Asset, asset_id)
    if not obj:
        raise HTTPException(404, "Actif introuvable")
    session.delete(obj)
    session.commit()
