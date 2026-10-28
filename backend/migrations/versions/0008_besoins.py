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

"""besoins materiels saisis par les RH

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'besoins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('quantite', sa.Integer(), nullable=False),
        sa.Column('commentaire', sa.String(), nullable=True),
        sa.Column('date_souhaitee', sa.Date(), nullable=True),
        sa.Column('statut', sa.String(), nullable=False),
        sa.Column('cree_par', sa.String(), nullable=True),
        sa.Column('traite_par', sa.String(), nullable=True),
        sa.Column('assignment_id', sa.Integer(), nullable=True),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('maj_le', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_besoins_user_id'), 'besoins', ['user_id'])
    op.create_index(op.f('ix_besoins_statut'), 'besoins', ['statut'])


def downgrade() -> None:
    op.drop_table('besoins')
