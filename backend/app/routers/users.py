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

from ..auth import get_current_account, require_roles, writer_guard
from ..catalogs import canonical_service
from ..db import get_session
from ..docname import acronyme_defaut, assurer_acronyme
from ..models import (
    Account,
    Assignment,
    Besoin,
    EmployeeStatus,
    Entite,
    User,
    Service,
    UserApplication,
    UserBase,
)
from ..scope import Scope, require_in_scope, scope_dep, visible_user
from ..rules import audit_change, changed_fields, count, refuse_delete, taken

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
    scope: Scope = Depends(scope_dep),
):
    stmt = scope.users(select(User))
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


def _check_entite(session: Session, entite_id: int | None) -> None:
    if entite_id is not None and not session.get(Entite, entite_id):
        raise HTTPException(400, "Entite inconnue")


@router.post("", response_model=User, status_code=201)
def create_user(data: UserBase, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    require_in_scope(scope, data.entite_id)
    taken(session, User, User.matricule, data.matricule, None, "Matricule")
    _check_entite(session, data.entite_id)
    data.service = canonical_service(session, data.service)
    obj = User.model_validate(data)
    assurer_acronyme(obj)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/catalogue/services", response_model=list[str])
def catalogue_services(session: Session = Depends(get_session)):
    """Services actifs (liste de parametrage) pour les menus."""
    rows = session.exec(select(Service.nom).where(Service.actif == True)).all()  # noqa: E712
    return sorted(rows, key=str.lower)


@router.get("/{user_id}", response_model=User)
def get_user(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    return visible_user(session, scope, user_id)


@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: int, data: UserBase,
    session: Session = Depends(get_session), account: Account = Depends(get_current_account),
    scope: Scope = Depends(scope_dep),
):
    obj = visible_user(session, scope, user_id)
    require_in_scope(scope, data.entite_id)  # ni sortir un salarie du perimetre, ni y en introduire un hors perimetre
    taken(session, User, User.matricule, data.matricule, obj.id, "Matricule")
    _check_entite(session, data.entite_id)
    data.service = canonical_service(session, data.service)
    new = data.model_dump()
    new["acronyme"] = new["acronyme"] or obj.acronyme or acronyme_defaut(data.prenom, data.nom)
    # Le depart passe par la page Sorties (restitution du materiel) ; un salarie sorti n'est pas reactive.
    if new["statut"] != obj.statut:
        if obj.statut == EmployeeStatus.sorti:
            raise HTTPException(409, "Un salarie sorti ne peut pas etre reactive")
        if new["statut"] in (EmployeeStatus.en_depart, EmployeeStatus.sorti):
            raise HTTPException(409, "Le depart se declare depuis la page Sorties (restitution du materiel)")
    fields = changed_fields(obj, new)
    for key, value in new.items():
        setattr(obj, key, value)
    obj.maj_le = datetime.utcnow()
    session.add(obj)
    session.commit()
    session.refresh(obj)
    audit_change(account.username, "users", obj.id, fields)
    return obj


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_roles("informatique"))])
def delete_user(user_id: int, session: Session = Depends(get_session)):
    obj = session.get(User, user_id)
    if not obj:
        raise HTTPException(404, "Utilisateur introuvable")
    refuse_delete(
        "ce salarie",
        {
            "affectation(s) de materiel": count(session, Assignment, Assignment.user_id == obj.id),
            "acces applicatif(s)": count(session, UserApplication, UserApplication.user_id == obj.id),
            "besoin(s) de materiel": count(session, Besoin, Besoin.user_id == obj.id),
        },
        "Un salarie avec historique se conserve (statut sorti via la page Sorties) ; "
        "son effacement definitif releve de la purge RGPD.",
    )
    session.delete(obj)
    session.commit()
