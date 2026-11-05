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

"""materiel non restitue et cloture de depart sans materiel

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-04 23:45:00

Lot 1bis (SPEC 6.3bis) : ajout du statut non_restitue a l'enumeration PostgreSQL assetstatus,
et des colonnes non_restitue_le et motif_non_restitution sur assignment_assets.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0023'
down_revision: Union[str, None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ajout de la valeur 'non_restitue' a l'enumeration native PostgreSQL 'assetstatus'.
    # En PostgreSQL, ALTER TYPE ... ADD VALUE ne peut pas s'executer dans une transaction ordinaire.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE assetstatus ADD VALUE IF NOT EXISTS 'non_restitue'")

    # 2. Nouvelles colonnes sur assignment_assets
    op.add_column('assignment_assets', sa.Column('non_restitue_le', sa.DateTime(), nullable=True))
    op.add_column('assignment_assets', sa.Column('motif_non_restitution', sa.String(), nullable=True))


def downgrade() -> None:
    # 1. Controle d'integrite : interdire le retour arriere si des actifs portent le statut 'non_restitue'
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT count(*) FROM assets WHERE statut = 'non_restitue'")).scalar()
    if count and count > 0:
        raise RuntimeError(f"Impossible de retrograder la migration : {count} actif(s) ont le statut 'non_restitue'")

    # 2. Suppression des colonnes sur assignment_assets
    op.drop_column('assignment_assets', 'motif_non_restitution')
    op.drop_column('assignment_assets', 'non_restitue_le')

    # 3. Retrait de la valeur 'non_restitue' de l'enum assetstatus en recreant le type initial
    op.execute("CREATE TYPE assetstatus_old AS ENUM ('stock', 'affecte', 'rendu', 'reforme')")
    op.execute("ALTER TABLE assets ALTER COLUMN statut TYPE assetstatus_old USING statut::text::assetstatus_old")
    op.execute("DROP TYPE assetstatus")
    op.execute("ALTER TYPE assetstatus_old RENAME TO assetstatus")
