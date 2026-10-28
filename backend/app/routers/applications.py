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
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import get_current_account, writer_guard
from ..db import get_session
from ..models import Account, Application, ApplicationBase, Entite, UserApplication
from ..scope import Scope, scope_dep
from ..rules import audit_change, changed_fields, count, refuse_delete

router = APIRouter(
    prefix="/applications", tags=["applications"],
    dependencies=[Depends(writer_guard("informatique"))],
)


@router.get("", response_model=list[Application])
def list_applications(
    session: Session = Depends(get_session), entite_id: int | None = None, scope: Scope = Depends(scope_dep)
):
    stmt = select(Application)
    if not scope.globale:  # catalogue commun (sans entite) et applications des entites de la portee
        stmt = stmt.where(Application.entite_id.is_(None) | Application.entite_id.in_(scope.ids))
    if entite_id is not None:
        stmt = stmt.where(Application.entite_id == entite_id)
    return session.exec(stmt).all()


def _check_application(session: Session, data: ApplicationBase, own_id: int | None) -> None:
    nom = (data.nom or "").strip()
    if not nom:
        raise HTTPException(400, "Le nom est obligatoire")
    if data.entite_id is not None and not session.get(Entite, data.entite_id):
        raise HTTPException(400, "Entite inconnue")
    same_scope = (Application.entite_id == data.entite_id) if data.entite_id is not None else Application.entite_id.is_(None)
    stmt = select(Application).where(func.lower(Application.nom) == nom.lower(), same_scope)
    if own_id is not None:
        stmt = stmt.where(Application.id != own_id)
    if session.exec(stmt).first():
        raise HTTPException(409, f"Application deja presente : {nom}")


@router.post("", response_model=Application, status_code=201)
def create_application(data: ApplicationBase, session: Session = Depends(get_session)):
    _check_application(session, data, None)
    obj = Application.model_validate(data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{application_id}", response_model=Application)
def get_application(application_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    obj = session.get(Application, application_id)
    if not obj or (obj.entite_id is not None and not scope.allows(obj.entite_id)):
        raise HTTPException(404, "Application introuvable")
    return obj


@router.put("/{application_id}", response_model=Application)
def update_application(
    application_id: int, data: ApplicationBase,
    session: Session = Depends(get_session), account: Account = Depends(get_current_account),
):
    obj = session.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application introuvable")
    _check_application(session, data, obj.id)
    new = data.model_dump()
    fields = changed_fields(obj, new)
    for key, value in new.items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    audit_change(account.username, "applications", obj.id, fields)
    return obj


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: int, session: Session = Depends(get_session)):
    obj = session.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application introuvable")
    refuse_delete(
        "cette application",
        {"acces attribue(s)": count(session, UserApplication, UserApplication.application_id == obj.id)},
        "Desactivez l'application (actif = non) plutot que de la supprimer.",
    )
    session.delete(obj)
    session.commit()
