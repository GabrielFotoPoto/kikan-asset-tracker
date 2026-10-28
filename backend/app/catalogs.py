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

"""Listes de parametrage "souples" (types d'actifs, services).

La liste alimente les menus ; une valeur nouvelle saisie (formulaire, import) est ajoutee a la liste, sans
jamais bloquer la saisie. Une valeur qui ne differe d'une entree existante que par la casse reprend la
graphie de la liste, ce qui evite de recreer des doublons.
"""
from sqlalchemy import func
from sqlmodel import Session, select

from .models import AssetType, Service

MAX_NAME = 100


def ensure_entry(session: Session, model, nom: str | None) -> str | None:
    """Nom canonique de `nom` dans la liste (l'ajoute si absent). Renvoie None si `nom` est vide."""
    value = (nom or "").strip()
    if not value:
        return None
    value = value[:MAX_NAME]
    existing = session.exec(select(model).where(func.lower(model.nom) == value.lower())).first()
    if existing:
        return existing.nom
    session.add(model(nom=value, actif=True))
    session.flush()
    return value


def canonical_type(session: Session, nom: str | None) -> str | None:
    return ensure_entry(session, AssetType, nom)


def canonical_service(session: Session, nom: str | None) -> str | None:
    return ensure_entry(session, Service, nom)
