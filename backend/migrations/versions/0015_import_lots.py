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

"""lots d'import (annulation d'un import)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-04 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'import_lots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('cree_par', sa.String(), nullable=True),
        sa.Column('sha256', sa.String(), nullable=True),
        sa.Column('nb_creees', sa.Integer(), nullable=False),
        sa.Column('elements', sa.JSON(), nullable=True),
        sa.Column('statut', sa.String(), nullable=False),
        sa.Column('annule_le', sa.DateTime(), nullable=True),
        sa.Column('annule_par', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('import_lots')
