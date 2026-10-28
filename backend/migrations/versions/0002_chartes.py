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

"""chartes deposees (fichier, portee, version active)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STR = sqlmodel.sql.sqltypes.AutoString()


def upgrade() -> None:
    op.add_column('policies', sa.Column('titre', STR, nullable=True))
    op.add_column('policies', sa.Column('entite_id', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('format_source', STR, nullable=True))
    op.add_column('policies', sa.Column('statut', STR, nullable=False, server_default='active'))
    op.add_column('policies', sa.Column('fichier_ref', STR, nullable=True))
    op.add_column('policies', sa.Column('sha256', STR, nullable=True))
    op.add_column('policies', sa.Column('source_ref', STR, nullable=True))
    op.add_column('policies', sa.Column('source_sha256', STR, nullable=True))
    op.add_column('policies', sa.Column('source_nom', STR, nullable=True))
    op.add_column('policies', sa.Column('nb_pages', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('depose_par', STR, nullable=True))
    op.add_column('policies', sa.Column('depose_le', sa.DateTime(), nullable=True))
    op.create_foreign_key('policies_entite_id_fkey', 'policies', 'entite', ['entite_id'], ['id'])
    op.alter_column('policies', 'statut', server_default=None)
    op.create_index('uq_policy_active_scope', 'policies', [sa.text('coalesce(entite_id, 0)')], unique=True,
                    postgresql_where=sa.text("statut = 'active'"))


def downgrade() -> None:
    op.drop_index('uq_policy_active_scope', table_name='policies')
    op.drop_constraint('policies_entite_id_fkey', 'policies', type_='foreignkey')
    for col in ('depose_le', 'depose_par', 'nb_pages', 'source_nom', 'source_sha256', 'source_ref',
                'sha256', 'fichier_ref', 'statut', 'format_source', 'entite_id', 'titre'):
        op.drop_column('policies', col)
