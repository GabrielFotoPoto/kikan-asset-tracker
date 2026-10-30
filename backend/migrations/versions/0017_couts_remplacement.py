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

"""couts de remplacement estimes par type de materiel (previsions de renouvellement)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-30 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'couts_remplacement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('marque', sa.String(), nullable=True),
        sa.Column('modele', sa.String(), nullable=True),
        sa.Column('montant_centimes', sa.Integer(), nullable=False),
        sa.Column('maj_le', sa.DateTime(), nullable=False),
        sa.Column('maj_par', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_couts_remplacement_type', 'couts_remplacement', ['type'])
    op.create_index('uq_couts_remplacement_cle', 'couts_remplacement',
                    [sa.text('lower(type)'), sa.text("lower(coalesce(marque, ''))"), sa.text("lower(coalesce(modele, ''))")],
                    unique=True)


def downgrade() -> None:
    op.drop_index('uq_couts_remplacement_cle', table_name='couts_remplacement')
    op.drop_index('ix_couts_remplacement_type', table_name='couts_remplacement')
    op.drop_table('couts_remplacement')
