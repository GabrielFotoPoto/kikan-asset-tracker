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

"""Acces applicatifs d'un salarie (relation plusieurs-a-plusieurs).

Attribuables par RH ou informatique (A.5.18).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import get_current_account, writer_guard
from ..scope import Scope, scope_dep, visible_user
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
def list_acces(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    visible_user(session, scope, user_id)
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
    scope: Scope = Depends(scope_dep),
):
    visible_user(session, scope, user_id)
    app = session.get(Application, data.application_id)
    if not app or (app.entite_id is not None and not scope.allows(app.entite_id)):
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
def delete_acces(ua_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    row = session.get(UserApplication, ua_id)
    user = session.get(User, row.user_id) if row else None
    if not row or not user or not scope.allows(user.entite_id):
        raise HTTPException(404, "Acces introuvable")
    session.delete(row)
    session.commit()
