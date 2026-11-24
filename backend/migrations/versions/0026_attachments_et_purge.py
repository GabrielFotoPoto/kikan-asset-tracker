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

"""pieces jointes transversales et suivi de purge RGPD (lot G3)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-24 20:40:00

Cree la table attachments (reutilisable pour tickets et futur chantier C5 sur actifs)
et ajoute la colonne type_doc ('pdf_scelle' | 'piece_jointe') sur purge_documents.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=24), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('storage_ref', sa.String(length=255), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('mime_type', sa.String(length=80), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=180), nullable=False),
        sa.Column('uploaded_by_account_id', sa.Integer(), nullable=True),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_attachments_entity', 'attachments', ['entity_type', 'entity_id'])
    op.create_index('ix_attachments_uploaded_by_account_id', 'attachments', ['uploaded_by_account_id'])

    op.add_column(
        'purge_documents',
        sa.Column('type_doc', sa.String(length=24), nullable=False, server_default='pdf_scelle'),
    )
    op.create_index('ix_purge_documents_type_doc', 'purge_documents', ['type_doc'])


def downgrade() -> None:
    op.drop_index('ix_purge_documents_type_doc', table_name='purge_documents')
    op.drop_column('purge_documents', 'type_doc')
    op.drop_table('attachments')
