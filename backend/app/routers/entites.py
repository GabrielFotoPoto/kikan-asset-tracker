from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..models import Entite, EntiteBase

router = APIRouter(
    prefix="/entites", tags=["entites"],
    dependencies=[Depends(writer_guard("informatique"))],
)


@router.get("", response_model=list[Entite])
def list_entites(session: Session = Depends(get_session)):
    return session.exec(select(Entite)).all()


@router.post("", response_model=Entite, status_code=201)
def create_entite(data: EntiteBase, session: Session = Depends(get_session)):
    obj = Entite.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{entite_id}", response_model=Entite)
def get_entite(entite_id: int, session: Session = Depends(get_session)):
    obj = session.get(Entite, entite_id)
    if not obj:
        raise HTTPException(404, "Entite introuvable")
    return obj


@router.put("/{entite_id}", response_model=Entite)
def update_entite(entite_id: int, data: EntiteBase, session: Session = Depends(get_session)):
    obj = session.get(Entite, entite_id)
    if not obj:
        raise HTTPException(404, "Entite introuvable")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/{entite_id}", status_code=204)
def delete_entite(entite_id: int, session: Session = Depends(get_session)):
    obj = session.get(Entite, entite_id)
    if not obj:
        raise HTTPException(404, "Entite introuvable")
    session.delete(obj)
    session.commit()
