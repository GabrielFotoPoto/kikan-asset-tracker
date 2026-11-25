# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

"""Service de lecture des detentions de materiel (partage entre portail et tickets)."""
from sqlmodel import Session, select

from .models import Asset, AssetStatus, Assignment, AssignmentAsset


def actifs_detenus_salarie(session: Session, user_id: int) -> list[tuple[Asset, Assignment]]:
    """Materiel actuellement detenu par le salarie : affectation en_cours, actif affecte et non restitue."""
    rows = session.exec(
        select(Asset, Assignment)
        .join(AssignmentAsset, AssignmentAsset.asset_id == Asset.id)
        .join(Assignment, Assignment.id == AssignmentAsset.assignment_id)
        .where(
            Assignment.user_id == user_id,
            Assignment.statut == "en_cours",
            Asset.statut == AssetStatus.affecte,
            AssignmentAsset.date_retour.is_(None),
        )
        .order_by(Asset.id)
    ).all()
    seen: set[int] = set()
    out: list[tuple[Asset, Assignment]] = []
    for asset, assign in rows:
        if asset.id not in seen:
            seen.add(asset.id)
            out.append((asset, assign))
    return out


def detenteur_actuel_actif(session: Session, asset_id: int) -> int | None:
    """Retourne le user_id du salarie detenant actuellement cet actif, ou None s'il n'est pas affecte."""
    return session.exec(
        select(Assignment.user_id)
        .join(AssignmentAsset, AssignmentAsset.assignment_id == Assignment.id)
        .join(Asset, Asset.id == AssignmentAsset.asset_id)
        .where(
            Asset.id == asset_id,
            Asset.statut == AssetStatus.affecte,
            Assignment.statut == "en_cours",
            AssignmentAsset.date_retour.is_(None),
        )
    ).first()
