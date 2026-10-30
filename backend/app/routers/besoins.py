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

"""Besoins materiels : souhaits exprimes par les RH a l'arrivee d'un salarie, traites et soldes par l'informatique.

Les RH expriment un souhait (une categorie de la liste du Parametrage, par exemple "Smartphone Apple", et sa gamme : Normal, Pro,
XL...) depuis le formulaire d'entree du salarie : c'est leur seul acces (creation, dans leur perimetre). Le suivi (liste,
modification, statuts) est reserve a l'informatique, en lecture seule pour le role lecture. L'informatique choisit le materiel
precis a la remise. Cycle : demande -> en_preparation -> satisfait (par la remise) ; annule. Le statut "satisfait" ne s'obtient que
par une remise.
"""
import re
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlmodel import Session, select

from ..audit import audit
from ..auth import get_current_account, require_roles, writer_guard
from ..db import get_session
from ..models import Account, Besoin, BesoinCategorie, User
from ..scope import Scope, scope_dep, visible_user

router = APIRouter(
    prefix="/besoins", tags=["besoins"],
    dependencies=[Depends(get_current_account)],
)

# Acces par route : les RH ne peuvent que creer un souhait (formulaire d'entree) ; le suivi est a l'informatique.
SUIVI_LECTURE = Depends(require_roles("informatique", "lecture"))
SUIVI_ECRITURE = Depends(writer_guard("informatique"))
CREATION = Depends(writer_guard("rh", "informatique"))

OUVERTS = ("demande", "en_preparation")
STATUTS = ("demande", "en_preparation", "satisfait", "annule")


def _clean(value: str | None, limit: int) -> str | None:
    text = re.sub(r"[\x00-\x1f\x7f\s]+", " ", value or "").strip()[:limit]
    return text or None


class BesoinIn(BaseModel):
    user_id: int
    type: str = Field(min_length=1, max_length=100)
    gamme: str | None = Field(default=None, max_length=40)
    quantite: int = Field(default=1, ge=1, le=20)
    commentaire: str | None = Field(default=None, max_length=200)
    date_souhaitee: date | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = _clean(v, 100)
        if not v:
            raise ValueError("type requis")
        return v

    @field_validator("gamme")
    @classmethod
    def _gamme(cls, v: str | None) -> str | None:
        return _clean(v, 40)

    @field_validator("commentaire")
    @classmethod
    def _comment(cls, v: str | None) -> str | None:
        return _clean(v, 200)


class BesoinUpdate(BaseModel):
    type: str | None = Field(default=None, max_length=100)
    gamme: str | None = Field(default=None, max_length=40)
    quantite: int | None = Field(default=None, ge=1, le=20)
    commentaire: str | None = Field(default=None, max_length=200)
    date_souhaitee: date | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str | None) -> str | None:
        return _clean(v, 100) if v is not None else None

    @field_validator("gamme")
    @classmethod
    def _gamme(cls, v: str | None) -> str | None:
        return _clean(v, 40)

    @field_validator("commentaire")
    @classmethod
    def _comment(cls, v: str | None) -> str | None:
        return _clean(v, 200)


class StatutIn(BaseModel):
    statut: Literal["demande", "en_preparation", "annule"]


def known_type(session: Session, nom: str) -> str:
    """Nom canonique d'une categorie de besoin active (liste Parametrage) : les RH ne creent pas de categories."""
    found = session.exec(select(BesoinCategorie).where(func.lower(BesoinCategorie.nom) == nom.lower(), BesoinCategorie.actif == True)).first()  # noqa: E712
    if not found:
        raise HTTPException(400, "Categorie de besoin inconnue : choisissez une categorie de la liste")
    return found.nom


def known_gamme(session: Session, type_: str, gamme: str | None) -> str | None:
    """Gamme canonique, parmi celles proposees pour la categorie (liste du Parametrage) ; vide si aucune n'est choisie."""
    if not gamme:
        return None
    cat = session.exec(select(BesoinCategorie).where(func.lower(BesoinCategorie.nom) == type_.lower())).first()
    for g in (cat.gammes if cat and cat.gammes else []):
        if g.lower() == gamme.lower():
            return g
    raise HTTPException(400, "Gamme inconnue pour cette categorie : choisissez une gamme de la liste")


def _out(session: Session, b: Besoin, users: dict[int, User] | None = None) -> dict:
    user = (users or {}).get(b.user_id) or session.get(User, b.user_id)
    return {
        "id": b.id, "user_id": b.user_id,
        "salarie": f"{user.prenom} {user.nom}" if user else "?", "matricule": user.matricule if user else None,
        "entite_id": user.entite_id if user else None, "statut_salarie": user.statut.value if user else None,
        "date_arrivee": user.date_arrivee if user else None,
        "type": b.type, "gamme": b.gamme, "quantite": b.quantite, "commentaire": b.commentaire, "date_souhaitee": b.date_souhaitee,
        "statut": b.statut, "cree_par": b.cree_par, "traite_par": b.traite_par, "assignment_id": b.assignment_id,
        "cree_le": b.cree_le, "maj_le": b.maj_le,
    }


def _visible(session: Session, scope: Scope, besoin_id: int) -> Besoin:
    b = session.get(Besoin, besoin_id)
    user = session.get(User, b.user_id) if b else None
    if not b or not user or not scope.allows(user.entite_id):
        raise HTTPException(404, "Besoin introuvable")
    return b


@router.get("/categories", response_model=list[str])
def categories(session: Session = Depends(get_session)):
    """Categories de besoin actives, pour les menus (tous les roles)."""
    rows = session.exec(select(BesoinCategorie.nom).where(BesoinCategorie.actif == True)).all()  # noqa: E712
    return sorted(rows, key=str.lower)


@router.get("/choix")
def choix(session: Session = Depends(get_session)):
    """Categories actives avec leurs gammes, pour le formulaire d'entree (cases a cocher et choix de la gamme)."""
    rows = session.exec(select(BesoinCategorie).where(BesoinCategorie.actif == True)).all()  # noqa: E712
    rows.sort(key=lambda c: c.nom.lower())
    return [{"nom": c.nom, "gammes": list(c.gammes or [])} for c in rows]


@router.get("", dependencies=[SUIVI_LECTURE])
def list_besoins(
    statut: str | None = None, entite_id: int | None = None, user_id: int | None = None, type: str | None = None,
    session: Session = Depends(get_session), scope: Scope = Depends(scope_dep),
):
    stmt = select(Besoin, User).join(User, User.id == Besoin.user_id)
    stmt = scope.where(stmt, User.entite_id)
    if statut:
        if statut == "ouverts":
            stmt = stmt.where(Besoin.statut.in_(OUVERTS))
        elif statut in STATUTS:
            stmt = stmt.where(Besoin.statut == statut)
        else:
            raise HTTPException(400, "Statut inconnu")
    if entite_id is not None:
        stmt = stmt.where(User.entite_id == entite_id)
    if user_id is not None:
        stmt = stmt.where(Besoin.user_id == user_id)
    if type:
        stmt = stmt.where(func.lower(Besoin.type) == type.lower())
    rows = session.exec(stmt.order_by(Besoin.id.desc())).all()
    users = {u.id: u for _, u in rows}
    items = [_out(session, b, users) for b, _ in rows]
    # Les besoins ouverts d'abord, par date d'arrivee ou date souhaitee la plus proche.
    items.sort(key=lambda x: (x["statut"] not in OUVERTS, x["date_souhaitee"] or x["date_arrivee"] or date.max))
    return items


@router.get("/ouverts/{user_id}", dependencies=[SUIVI_LECTURE])
def open_for_user(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Besoins encore ouverts d'un salarie (proposes a la creation d'une remise)."""
    visible_user(session, scope, user_id)
    rows = session.exec(select(Besoin).where(Besoin.user_id == user_id, Besoin.statut.in_(OUVERTS)).order_by(Besoin.id)).all()
    return [_out(session, b) for b in rows]


@router.post("", status_code=201, dependencies=[CREATION])
def create_besoin(data: BesoinIn, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep),
                  account: Account = Depends(get_current_account)):
    user = visible_user(session, scope, data.user_id)
    type_ = known_type(session, data.type)
    b = Besoin(user_id=user.id, type=type_, gamme=known_gamme(session, type_, data.gamme), quantite=data.quantite,
               commentaire=data.commentaire, date_souhaitee=data.date_souhaitee or user.date_arrivee, cree_par=account.username)
    session.add(b)
    session.commit()
    session.refresh(b)
    audit(account.username, "besoin_cree", target=str(b.id), detail=f"salarie {user.id}")
    return _out(session, b)


def _editable(b: Besoin) -> None:
    if b.statut not in OUVERTS:
        raise HTTPException(409, "Ce besoin n'est plus modifiable")


@router.put("/{besoin_id}", dependencies=[SUIVI_ECRITURE])
def update_besoin(besoin_id: int, data: BesoinUpdate, session: Session = Depends(get_session),
                  scope: Scope = Depends(scope_dep), account: Account = Depends(get_current_account)):
    b = _visible(session, scope, besoin_id)
    _editable(b)
    changed = []
    fields = data.model_fields_set
    if "type" in fields and data.type:
        new = known_type(session, data.type)
        if new != b.type:
            b.type = new
            changed.append("type")
            if "gamme" not in fields and b.gamme:  # la gamme n'est conservee que si la nouvelle categorie la propose
                try:
                    b.gamme = known_gamme(session, b.type, b.gamme)
                except HTTPException:
                    b.gamme = None
                    changed.append("gamme")
    if "gamme" in fields:
        new_gamme = known_gamme(session, b.type, data.gamme)
        if new_gamme != b.gamme:
            b.gamme = new_gamme
            changed.append("gamme")
    if "quantite" in fields and data.quantite and data.quantite != b.quantite:
        b.quantite = data.quantite
        changed.append("quantite")
    if "commentaire" in fields and data.commentaire != b.commentaire:
        b.commentaire = data.commentaire
        changed.append("commentaire")
    if "date_souhaitee" in fields and data.date_souhaitee != b.date_souhaitee:
        b.date_souhaitee = data.date_souhaitee
        changed.append("date")
    b.maj_le = datetime.utcnow()
    session.add(b)
    session.commit()
    audit(account.username, "besoin_modifie", target=str(b.id), detail="champs : " + (", ".join(changed) or "aucun changement"))
    return _out(session, b)


@router.post("/{besoin_id}/statut", dependencies=[SUIVI_ECRITURE])
def set_statut(besoin_id: int, data: StatutIn, session: Session = Depends(get_session),
               scope: Scope = Depends(scope_dep), account: Account = Depends(get_current_account)):
    """Changement de statut. "satisfait" n'est pas accepte ici : il resulte d'une remise."""
    b = _visible(session, scope, besoin_id)
    if b.statut in ("satisfait", "annule"):
        raise HTTPException(409, "Ce besoin est clos")
    if data.statut == b.statut:
        raise HTTPException(409, "Le besoin a deja ce statut")
    b.statut = data.statut
    b.traite_par = account.username
    b.maj_le = datetime.utcnow()
    session.add(b)
    session.commit()
    audit(account.username, "besoin_statut", target=str(b.id), detail=data.statut)
    return _out(session, b)


def settle(session: Session, besoin_ids: list[int], user_id: int, assignment_id: int, actor: str) -> int:
    """Solde des besoins ouverts d'un salarie par une remise (appele a la creation de la remise, sans commit)."""
    n = 0
    for bid in dict.fromkeys(besoin_ids):
        b = session.get(Besoin, bid)
        if not b or b.user_id != user_id:
            raise HTTPException(400, "Besoin inconnu ou d'un autre salarie")
        if b.statut not in OUVERTS:
            raise HTTPException(409, f"Le besoin {bid} est deja clos")
        b.statut, b.assignment_id, b.traite_par, b.maj_le = "satisfait", assignment_id, actor, datetime.utcnow()
        session.add(b)
        n += 1
    return n
