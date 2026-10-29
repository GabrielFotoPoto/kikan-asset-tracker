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

"""liens de reinitialisation du mot de passe (mot de passe oublie)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('expire_le', sa.DateTime(), nullable=False),
        sa.Column('utilise_le', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_password_reset_tokens_account_id'), 'password_reset_tokens', ['account_id'])
    op.create_index(op.f('ix_password_reset_tokens_token_hash'), 'password_reset_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_table('password_reset_tokens')
