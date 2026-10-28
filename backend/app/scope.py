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

"""Portee des comptes : cloisonnement par entite (comptes RH et lecture ; l'informatique voit tout).

Un compte est global ou limite a des entites ; la portee effective comprend leurs sous-entites. Elle est recalculee
a chaque requete depuis la base : un changement prend effet immediatement. Hors portee, un element est "introuvable"
(404) et jamais "interdit" : on ne revele pas son existence. Les donnees sans entite ne sont visibles que des comptes
globaux. Tout le filtrage passe par ce module (jamais de verification dispersee).
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from sqlalchemy import false
from sqlmodel import Session, select

from .auth import get_current_account
from .db import get_session
from .models import Account, AccountScope, Assignment, Entite, Role, User


@dataclass(frozen=True)
class Scope:
    globale: bool
    ids: frozenset = frozenset()        # entites visibles : choisies et descendantes
    ancestors: frozenset = frozenset()  # entites parentes des entites choisies (leurs chartes s'appliquent)

    @property
    def vide(self) -> bool:
        return not self.globale and not self.ids

    def allows(self, entite_id: int | None) -> bool:
        return self.globale or (entite_id is not None and entite_id in self.ids)

    def where(self, stmt, column):
        """Restreint une requete aux lignes dont `column` (id d'entite) est dans la portee."""
        if self.globale:
            return stmt
        return stmt.where(column.in_(self.ids)) if self.ids else stmt.where(false())

    def users(self, stmt):
        return self.where(stmt, User.entite_id)

    def assignments(self, stmt):
        """Affectations des salaries de la portee."""
        if self.globale:
            return stmt
        if not self.ids:
            return stmt.where(false())
        return stmt.where(Assignment.user_id.in_(select(User.id).where(User.entite_id.in_(self.ids))))

    def allows_policy(self, entite_id: int | None) -> bool:
        """Une charte globale est lisible de tous ; une charte d'entite dans la portee ou parente d'une entite de la portee."""
        return self.globale or entite_id is None or entite_id in self.ids or entite_id in self.ancestors


GLOBAL = Scope(True)


def compute_scope(session: Session, account: Account) -> Scope:
    if account.role == Role.informatique or account.portee_globale:
        return GLOBAL
    chosen = {r.entite_id for r in session.exec(select(AccountScope).where(AccountScope.account_id == account.id)).all()}
    if not chosen:
        return Scope(False)
    entites = session.exec(select(Entite)).all()
    by_code = {e.code: e for e in entites}
    children: dict[str, list[Entite]] = {}
    for e in entites:
        if e.code_parent:
            children.setdefault(e.code_parent, []).append(e)
    visible, stack = set(), [e for e in entites if e.id in chosen]
    while stack:
        e = stack.pop()
        if e.id in visible:
            continue
        visible.add(e.id)
        stack.extend(children.get(e.code, []))
    ancestors = set()
    for e in entites:
        if e.id in chosen:
            parent = by_code.get(e.code_parent) if e.code_parent else None
            while parent is not None and parent.id not in ancestors and parent.id not in visible:
                ancestors.add(parent.id)
                parent = by_code.get(parent.code_parent) if parent.code_parent else None
    return Scope(False, frozenset(visible), frozenset(ancestors))


def scope_dep(account: Account = Depends(get_current_account), session: Session = Depends(get_session)) -> Scope:
    return compute_scope(session, account)


# --- Acces a un element par identifiant (404 hors portee) ---

def visible_user(session: Session, scope: Scope, user_id: int) -> User:
    user = session.get(User, user_id)
    if not user or not scope.allows(user.entite_id):
        raise HTTPException(404, "Utilisateur introuvable")
    return user


def visible_assignment(session: Session, scope: Scope, assignment_id: int) -> Assignment:
    assignment = session.get(Assignment, assignment_id)
    user = session.get(User, assignment.user_id) if assignment else None
    if not assignment or not user or not scope.allows(user.entite_id):
        raise HTTPException(404, "Affectation introuvable")
    return assignment


def require_in_scope(scope: Scope, entite_id: int | None) -> None:
    """Ecriture : l'entite demandee doit etre dans la portee (403 : la requete nomme elle-meme l'entite)."""
    if not scope.allows(entite_id):
        raise HTTPException(403, "Entite hors de votre perimetre" if entite_id is not None
                            else "Une entite de votre perimetre est requise")
