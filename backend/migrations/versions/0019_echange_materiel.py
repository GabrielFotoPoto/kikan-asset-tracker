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

"""echange de materiel (renouvellement) : type d'affectation, date de retour par actif, retours d'un echange

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-30 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assignments', sa.Column('type', sa.String(), nullable=False, server_default='remise'))
    op.add_column('assignment_assets', sa.Column('date_retour', sa.DateTime(), nullable=True))
    # Les affectations deja cloturees : leurs actifs ont ete rendus a la date de cloture.
    op.execute("""
        UPDATE assignment_assets SET date_retour = (SELECT a.date_restitution FROM assignments a WHERE a.id = assignment_assets.assignment_id)
        WHERE assignment_id IN (SELECT id FROM assignments WHERE statut = 'restitue' AND date_restitution IS NOT NULL)
    """)
    op.create_table(
        'echange_retours',
        sa.Column('assignment_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('destination', sa.String(), nullable=False, server_default='rendu'),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id']),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('assignment_id', 'asset_id'),
    )


def downgrade() -> None:
    op.drop_table('echange_retours')
    op.drop_column('assignment_assets', 'date_retour')
    op.drop_column('assignments', 'type')
