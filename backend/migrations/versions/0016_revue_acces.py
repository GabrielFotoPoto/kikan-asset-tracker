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

"""revue periodique des droits d'acces (campagnes et lignes de revue)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-05 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'revues_acces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titre', sa.String(), nullable=False),
        sa.Column('statut', sa.String(), nullable=False),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('cree_par', sa.String(), nullable=True),
        sa.Column('echeance', sa.Date(), nullable=True),
        sa.Column('perimetre', sa.JSON(), nullable=True),
        sa.Column('cloture_le', sa.DateTime(), nullable=True),
        sa.Column('cloture_par', sa.String(), nullable=True),
        sa.Column('rapport_ref', sa.String(), nullable=True),
        sa.Column('rapport_empreinte', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'revue_lignes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('revue_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_application_id', sa.Integer(), nullable=True),
        sa.Column('entite_id', sa.Integer(), nullable=True),
        sa.Column('matricule', sa.String(), nullable=True),
        sa.Column('application', sa.String(), nullable=False),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('anomalie', sa.String(), nullable=True),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('commentaire', sa.String(), nullable=True),
        sa.Column('decide_par', sa.String(), nullable=True),
        sa.Column('decide_le', sa.DateTime(), nullable=True),
        sa.Column('retrait', sa.String(), nullable=True),
        sa.Column('retrait_par', sa.String(), nullable=True),
        sa.Column('retrait_le', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['revue_id'], ['revues_acces.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_revue_lignes_revue_id'), 'revue_lignes', ['revue_id'])
    op.create_index(op.f('ix_revue_lignes_user_id'), 'revue_lignes', ['user_id'])
    op.create_index(op.f('ix_revue_lignes_entite_id'), 'revue_lignes', ['entite_id'])
    op.create_index(op.f('ix_revue_lignes_decision'), 'revue_lignes', ['decision'])


def downgrade() -> None:
    op.drop_table('revue_lignes')
    op.drop_table('revues_acces')
