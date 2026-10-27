"""Acces applicatifs d'un salarie (relation plusieurs-a-plusieurs).

Attribuables par RH ou informatique (A.5.18).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import get_current_account, writer_guard
from ..db import get_session
from ..models import Account, Application, User, UserApplication

router = APIRouter(
    tags=["acces-applicatifs"],
    dependencies=[Depends(writer_guard("rh", "informatique"))],
)


class AccesInput(BaseModel):
    application_id: int
    acces: bool = True
    note: str | None = None


@router.get("/users/{user_id}/applications")
def list_acces(user_id: int, session: Session = Depends(get_session)):
    if not session.get(User, user_id):
        raise HTTPException(404, "Utilisateur introuvable")
    apps = {a.id: a for a in session.exec(select(Application)).all()}
    rows = session.exec(
        select(UserApplication).where(UserApplication.user_id == user_id)
    ).all()
    return [
        {
            "id": r.id,
            "application_id": r.application_id,
            "application_nom": apps[r.application_id].nom if r.application_id in apps else "?",
            "acces": r.acces,
            "note": r.note,
            "attribue_par": r.attribue_par,
            "date_maj": r.date_maj.isoformat() if r.date_maj else None,
        }
        for r in rows
    ]


@router.post("/users/{user_id}/applications", status_code=201)
def set_acces(
    user_id: int,
    data: AccesInput,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
):
    if not session.get(User, user_id):
        raise HTTPException(404, "Utilisateur introuvable")
    if not session.get(Application, data.application_id):
        raise HTTPException(404, "Application introuvable")
    # Upsert sur (user_id, application_id).
    existing = session.exec(
        select(UserApplication).where(
            UserApplication.user_id == user_id,
            UserApplication.application_id == data.application_id,
        )
    ).first()
    if existing:
        existing.acces = data.acces
        existing.note = data.note
        existing.attribue_par = account.username
        existing.date_maj = datetime.utcnow()
        row = existing
    else:
        row = UserApplication(
            user_id=user_id,
            application_id=data.application_id,
            acces=data.acces,
            note=data.note,
            attribue_par=account.username,
        )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.delete("/user-applications/{ua_id}", status_code=204)
def delete_acces(ua_id: int, session: Session = Depends(get_session)):
    row = session.get(UserApplication, ua_id)
    if not row:
        raise HTTPException(404, "Acces introuvable")
    session.delete(row)
    session.commit()
