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

"""historique des synchronisations avec un systeme externe

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'integration_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('systeme', sa.String(), nullable=False),
        sa.Column('sens', sa.String(), nullable=False),
        sa.Column('lance_par', sa.String(), nullable=True),
        sa.Column('debut', sa.DateTime(), nullable=False),
        sa.Column('fin', sa.DateTime(), nullable=True),
        sa.Column('resume', sa.String(), nullable=True),
        sa.Column('erreurs', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_integration_runs_systeme'), 'integration_runs', ['systeme'])


def downgrade() -> None:
    op.drop_table('integration_runs')
