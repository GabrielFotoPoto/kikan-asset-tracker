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

"""suivi des documents de la purge RGPD (quarantaine SMB/local/WebDAV, liste a supprimer dans la GED)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-03 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'purge_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(), nullable=False),
        sa.Column('reference_quarantaine', sa.String(), nullable=True),
        sa.Column('moteur', sa.String(), nullable=False),
        sa.Column('statut', sa.String(), nullable=False),
        sa.Column('empreinte', sa.String(), nullable=True),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('echeance', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_purge_documents_statut'), 'purge_documents', ['statut'])


def downgrade() -> None:
    op.drop_table('purge_documents')
