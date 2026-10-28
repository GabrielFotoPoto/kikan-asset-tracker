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

"""portee des comptes : globale ou limitee a des entites

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Les comptes existants restent globaux : aucun changement de comportement a la mise a jour.
    op.add_column('accounts', sa.Column('portee_globale', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('accounts', 'portee_globale', server_default=None)
    op.create_table(
        'account_scopes',
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('entite_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['entite_id'], ['entite.id']),
        sa.PrimaryKeyConstraint('account_id', 'entite_id'),
    )


def downgrade() -> None:
    op.drop_table('account_scopes')
    op.drop_column('accounts', 'portee_globale')
