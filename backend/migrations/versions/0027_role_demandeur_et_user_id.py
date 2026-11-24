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

"""role demandeur et liaison accounts.user_id (lot G4a)

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-24 21:30:00

Ajoute la valeur 'demandeur' au type enum PostgreSQL natif `role` (hors transaction)
et la colonne unique `user_id` sur `accounts` (FK users.id ON DELETE SET NULL).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'demandeur'")

    op.add_column('accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_accounts_user_id_users', 'accounts', 'users', ['user_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('uq_accounts_user_id', 'accounts', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_accounts_user_id', table_name='accounts')
    op.drop_constraint('fk_accounts_user_id_users', 'accounts', type_='foreignkey')
    op.drop_column('accounts', 'user_id')
