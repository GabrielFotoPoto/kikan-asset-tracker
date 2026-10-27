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

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..models import Application, ApplicationBase

router = APIRouter(
    prefix="/applications", tags=["applications"],
    dependencies=[Depends(writer_guard("informatique"))],
)


@router.get("", response_model=list[Application])
def list_applications(
    session: Session = Depends(get_session), entite_id: int | None = None
):
    stmt = select(Application)
    if entite_id is not None:
        stmt = stmt.where(Application.entite_id == entite_id)
    return session.exec(stmt).all()


@router.post("", response_model=Application, status_code=201)
def create_application(data: ApplicationBase, session: Session = Depends(get_session)):
    obj = Application.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{application_id}", response_model=Application)
def get_application(application_id: int, session: Session = Depends(get_session)):
    obj = session.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application introuvable")
    return obj


@router.put("/{application_id}", response_model=Application)
def update_application(
    application_id: int, data: ApplicationBase, session: Session = Depends(get_session)
):
    obj = session.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application introuvable")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: int, session: Session = Depends(get_session)):
    obj = session.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application introuvable")
    session.delete(obj)
    session.commit()
