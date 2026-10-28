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

"""Entites / filiales : creation, modification (propagation du code, pas de cycle) et suppression protegee."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_account, writer_guard
from ..db import get_session
from ..models import Account, Application, Asset, Entite, EntiteBase, Policy, User
from ..scope import Scope, scope_dep
from ..rules import audit_change, changed_fields, count, refuse_delete, taken

router = APIRouter(
    prefix="/entites", tags=["entites"],
    dependencies=[Depends(writer_guard("informatique"))],
)


def _by_code(session: Session, code: str | None) -> Entite | None:
    return session.exec(select(Entite).where(Entite.code == code)).first() if code else None


def _clean(data: EntiteBase) -> dict:
    values = data.model_dump()
    values["code"] = (values["code"] or "").strip()
    values["nom"] = (values["nom"] or "").strip()
    values["code_parent"] = (values["code_parent"] or "").strip() or None
    if not values["code"] or not values["nom"]:
        raise HTTPException(400, "Le code et le nom sont obligatoires")
    return values


def _check_parent(session: Session, code: str, parent_code: str | None, own_id: int | None) -> None:
    """Le parent doit exister et ne doit pas creer de boucle dans la hierarchie."""
    if not parent_code:
        return
    if parent_code == code:
        raise HTTPException(400, "Une entite ne peut pas etre son propre parent")
    current = _by_code(session, parent_code)
    if current is None:
        raise HTTPException(400, f"Entite parente inconnue : {parent_code}")
    seen: set[int] = set()
    while current is not None and current.id not in seen:
        if own_id is not None and current.id == own_id:
            raise HTTPException(400, "Cette parente creerait une boucle dans la hierarchie des entites")
        seen.add(current.id)
        current = _by_code(session, current.code_parent)


@router.get("", response_model=list[Entite])
def list_entites(session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    return session.exec(scope.where(select(Entite), Entite.id)).all()


@router.post("", response_model=Entite, status_code=201)
def create_entite(data: EntiteBase, session: Session = Depends(get_session)):
    values = _clean(data)
    taken(session, Entite, Entite.code, values["code"], None, "Code d'entite")
    _check_parent(session, values["code"], values["code_parent"], None)
    obj = Entite(**values)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.get("/{entite_id}", response_model=Entite)
def get_entite(entite_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    obj = session.get(Entite, entite_id)
    if not obj or not scope.allows(obj.id):
        raise HTTPException(404, "Entite introuvable")
    return obj


@router.put("/{entite_id}", response_model=Entite)
def update_entite(
    entite_id: int, data: EntiteBase,
    session: Session = Depends(get_session), account: Account = Depends(get_current_account),
):
    obj = session.get(Entite, entite_id)
    if not obj:
        raise HTTPException(404, "Entite introuvable")
    values = _clean(data)
    taken(session, Entite, Entite.code, values["code"], obj.id, "Code d'entite")
    _check_parent(session, values["code"], values["code_parent"], obj.id)
    fields = changed_fields(obj, values)
    old_code = obj.code
    for key, value in values.items():
        setattr(obj, key, value)
    session.add(obj)
    if values["code"] != old_code:
        # Le lien parent est porte par le code : les filiales suivent le renommage.
        for child in session.exec(select(Entite).where(Entite.code_parent == old_code)).all():
            child.code_parent = values["code"]
            session.add(child)
    session.commit()
    session.refresh(obj)
    audit_change(account.username, "entites", obj.id, fields)
    return obj


@router.delete("/{entite_id}", status_code=204)
def delete_entite(entite_id: int, session: Session = Depends(get_session)):
    obj = session.get(Entite, entite_id)
    if not obj:
        raise HTTPException(404, "Entite introuvable")
    refuse_delete(
        "cette entite",
        {
            "salarie(s)": count(session, User, User.entite_id == obj.id),
            "actif(s)": count(session, Asset, Asset.entite_id == obj.id),
            "application(s)": count(session, Application, Application.entite_id == obj.id),
            "charte(s)": count(session, Policy, Policy.entite_id == obj.id),
            "entite(s) fille(s)": count(session, Entite, Entite.code_parent == obj.code),
        },
        "Desactivez l'entite (actif = non) plutot que de la supprimer.",
    )
    session.delete(obj)
    session.commit()
