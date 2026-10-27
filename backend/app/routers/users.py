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
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..models import EmployeeStatus, User, UserBase

router = APIRouter(
    prefix="/users", tags=["users"],
    dependencies=[Depends(writer_guard("rh", "informatique"))],
)


@router.get("", response_model=list[User])
def list_users(
    session: Session = Depends(get_session),
    entite_id: int | None = None,
    statut: EmployeeStatus | None = None,
    q: str | None = Query(default=None, description="recherche nom/prenom/matricule"),
):
    stmt = select(User)
    if entite_id is not None:
        stmt = stmt.where(User.entite_id == entite_id)
    if statut is not None:
        stmt = stmt.where(User.statut == statut)
    results = session.exec(stmt).all()
    if q:
        ql = q.lower()
        results = [
            u for u in results
            if ql in (u.nom or "").lower()
            or ql in (u.prenom or "").lower()
            or ql in (u.matricule or "").lower()
        ]
    return results


@router.post("", response_model=User, status_code=201)
def create_user(data: UserBase, session: Session = Depends(get_session)):
    obj = User.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{user_id}", response_model=User)
def get_user(user_id: int, session: Session = Depends(get_session)):
    obj = session.get(User, user_id)
    if not obj:
        raise HTTPException(404, "Utilisateur introuvable")
    return obj


@router.put("/{user_id}", response_model=User)
def update_user(user_id: int, data: UserBase, session: Session = Depends(get_session)):
    obj = session.get(User, user_id)
    if not obj:
        raise HTTPException(404, "Utilisateur introuvable")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    obj.maj_le = datetime.utcnow()
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, session: Session = Depends(get_session)):
    obj = session.get(User, user_id)
    if not obj:
        raise HTTPException(404, "Utilisateur introuvable")
    session.delete(obj)
    session.commit()
