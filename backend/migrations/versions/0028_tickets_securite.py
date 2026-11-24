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

"""dossier d'investigation securite 1-1 sur les tickets (lot G2)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-24 22:00:00

Cree la table dediee ticket_security_details (1-1 avec tickets) pour isoler physiquement
les informations d'investigation securite et le suivi 72h DPO/CNIL (RGPD art. 33).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ticket_security_details',
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('signale_le', sa.DateTime(), nullable=False),
        sa.Column('signale_par', sa.String(length=16), nullable=False),
        sa.Column('qualifie_le', sa.DateTime(), nullable=True),
        sa.Column('qualification_sec', sa.Integer(), nullable=True),
        sa.Column('qualifie_par_account_id', sa.Integer(), nullable=True),
        sa.Column('sous_categorie', sa.String(length=40), nullable=True),
        sa.Column('escalade_le', sa.DateTime(), nullable=True),
        sa.Column('escalade_par_account_id', sa.Integer(), nullable=True),
        sa.Column('violation_donnees_potentielle', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('date_decouverte_violation', sa.DateTime(), nullable=True),
        sa.Column('notification_dpo_le', sa.DateTime(), nullable=True),
        sa.Column('notification_cnil_requise', sa.String(length=16), nullable=True),
        sa.Column('confine_le', sa.DateTime(), nullable=True),
        sa.Column('cause_racine', sa.String(length=3000), nullable=True),
        sa.Column('actions_correctives', sa.String(length=3000), nullable=True),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['qualifie_par_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['escalade_par_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('ticket_id'),
    )
    op.create_index('ix_ticket_security_details_qualifie_par_account_id', 'ticket_security_details', ['qualifie_par_account_id'])
    op.create_index('ix_ticket_security_details_escalade_par_account_id', 'ticket_security_details', ['escalade_par_account_id'])


def downgrade() -> None:
    op.drop_table('ticket_security_details')
