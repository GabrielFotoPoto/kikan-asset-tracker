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

"""API d'integration : jetons et liens d'identifiants externes

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('prefixe', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('droits', sa.String(), nullable=False),
        sa.Column('portee_globale', sa.Boolean(), nullable=False),
        sa.Column('expire_le', sa.Date(), nullable=False),
        sa.Column('actif', sa.Boolean(), nullable=False),
        sa.Column('cree_par', sa.String(), nullable=True),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('derniere_utilisation', sa.DateTime(), nullable=True),
        sa.Column('utilisations', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)
    op.create_table(
        'api_token_scopes',
        sa.Column('token_id', sa.Integer(), nullable=False),
        sa.Column('entite_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['token_id'], ['api_tokens.id']),
        sa.ForeignKeyConstraint(['entite_id'], ['entite.id']),
        sa.PrimaryKeyConstraint('token_id', 'entite_id'),
    )
    op.create_table(
        'external_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('systeme', sa.String(), nullable=False),
        sa.Column('objet', sa.String(), nullable=False),
        sa.Column('kikan_id', sa.Integer(), nullable=False),
        sa.Column('externe_id', sa.String(), nullable=False),
        sa.Column('synchro_le', sa.DateTime(), nullable=False),
        sa.Column('empreinte', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_external_by_ext', 'external_links', ['systeme', 'objet', 'externe_id'], unique=True)
    op.create_index('uq_external_by_kikan', 'external_links', ['systeme', 'objet', 'kikan_id'], unique=True)


def downgrade() -> None:
    op.drop_table('external_links')
    op.drop_table('api_token_scopes')
    op.drop_table('api_tokens')
