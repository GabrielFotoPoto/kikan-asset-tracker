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

"""Regles communes de modification et de suppression (donnees avec historique)."""
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from .audit import audit


def count(session: Session, model, *conditions) -> int:
    """Nombre de lignes de `model` verifiant les conditions."""
    return session.exec(select(func.count()).select_from(model).where(*conditions)).one()


def refuse_delete(what: str, usages: dict[str, int], advice: str) -> None:
    """409 explicite si l'element est encore utilise ailleurs ; `usages` : libelle -> nombre."""
    used = [f"{n} {label}" for label, n in usages.items() if n]
    if used:
        raise HTTPException(409, f"Suppression impossible : {what} est utilise(e) par {', '.join(used)}. {advice}")


def taken(session: Session, model, field, value, exclude_id: int | None, label: str) -> None:
    """409 si un autre element porte deja cette valeur (code, matricule, numero de serie...)."""
    if value is None or value == "":
        return
    stmt = select(model).where(field == value)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if session.exec(stmt).first():
        raise HTTPException(409, f"{label} deja utilise : {value}")


def changed_fields(obj, new: dict) -> list[str]:
    """Noms des champs dont la valeur change (jamais les valeurs : donnees personnelles)."""
    return [k for k, v in new.items() if getattr(obj, k, None) != v]


def audit_change(actor: str, resource: str, obj_id: int, fields: list[str]) -> None:
    audit(actor, "modification", target=f"{resource}/{obj_id}",
          detail="champs : " + (", ".join(fields) if fields else "aucun changement"))
