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

"""historique des reports d'echeance de renouvellement

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-30 19:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'echeance_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('ancienne', sa.Date(), nullable=True),
        sa.Column('nouvelle', sa.Date(), nullable=True),
        sa.Column('motif', sa.String(), nullable=True),
        sa.Column('par', sa.String(), nullable=True),
        sa.Column('le', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_echeance_reports_asset_id', 'echeance_reports', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_echeance_reports_asset_id', table_name='echeance_reports')
    op.drop_table('echeance_reports')
