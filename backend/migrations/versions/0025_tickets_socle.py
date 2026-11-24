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

"""socle tickets natif (lot G1)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-24 20:00:00

Cree les tables du socle tickets (ticket_natures, ticket_compteurs, tickets, ticket_comments)
avec index sur toutes les cles etrangeres et colonnes de filtre, et pre-remplit le catalogue
initial de huit natures.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NATURES_INITIALES = [
    {"code": "panne_materiel", "libelle": "Panne materiel", "signale_securite": False, "actif": True, "ordre": 10},
    {"code": "perte_vol_materiel", "libelle": "Perte ou vol de materiel", "signale_securite": True, "actif": True, "ordre": 20},
    {"code": "incident_logiciel", "libelle": "Incident logiciel", "signale_securite": False, "actif": True, "ordre": 30},
    {"code": "reseau", "libelle": "Reseau", "signale_securite": False, "actif": True, "ordre": 40},
    {"code": "acces_compte", "libelle": "Acces / compte", "signale_securite": False, "actif": True, "ordre": 50},
    {"code": "message_suspect", "libelle": "Message suspect", "signale_securite": True, "actif": True, "ordre": 60},
    {"code": "demande_service", "libelle": "Demande de service", "signale_securite": False, "actif": True, "ordre": 70},
    {"code": "autre", "libelle": "Autre", "signale_securite": False, "actif": True, "ordre": 80},
]


def upgrade() -> None:
    ticket_natures = op.create_table(
        'ticket_natures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('libelle', sa.String(length=100), nullable=False),
        sa.Column('signale_securite', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('actif', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('ordre', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_ticket_natures_code'),
    )
    op.create_index('ix_ticket_natures_code', 'ticket_natures', ['code'], unique=True)

    op.bulk_insert(ticket_natures, NATURES_INITIALES)

    op.create_table(
        'ticket_compteurs',
        sa.Column('annee', sa.Integer(), nullable=False),
        sa.Column('dernier_numero', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('annee'),
    )

    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(length=20), nullable=False),
        sa.Column('entite_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('cree_par_account_id', sa.Integer(), nullable=True),
        sa.Column('assigne_a_account_id', sa.Integer(), nullable=True),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('assignment_id', sa.Integer(), nullable=True),
        sa.Column('materiel_type', sa.String(length=100), nullable=True),
        sa.Column('materiel_marque', sa.String(length=100), nullable=True),
        sa.Column('materiel_modele', sa.String(length=100), nullable=True),
        sa.Column('nature_code', sa.String(length=40), nullable=False),
        sa.Column('criticite_demandeur', sa.String(length=16), nullable=False),
        sa.Column('criticite', sa.String(length=16), nullable=False),
        sa.Column('statut', sa.String(length=20), nullable=False, server_default='nouveau'),
        sa.Column('titre', sa.String(length=200), nullable=True),
        sa.Column('description', sa.String(length=5000), nullable=True),
        sa.Column('canal', sa.String(length=16), nullable=False, server_default='it'),
        sa.Column('demandeur_verifie', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('niveau_securite', sa.String(length=16), nullable=False, server_default='aucun'),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.Column('premiere_reponse_le', sa.DateTime(), nullable=True),
        sa.Column('en_attente_depuis', sa.DateTime(), nullable=True),
        sa.Column('duree_attente_sec', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('resolu_le', sa.DateTime(), nullable=True),
        sa.Column('ferme_le', sa.DateTime(), nullable=True),
        sa.Column('nb_reouvertures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mtta_sec', sa.Integer(), nullable=True),
        sa.Column('mttr_sec', sa.Integer(), nullable=True),
        sa.Column('anonymise_le', sa.DateTime(), nullable=True),
        sa.Column('maj_le', sa.DateTime(), nullable=False),
        sa.Column('maj_publique_le', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entite_id'], ['entite.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['cree_par_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigne_a_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['nature_code'], ['ticket_natures.code']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference', name='uq_tickets_reference'),
    )
    op.create_index('ix_tickets_reference', 'tickets', ['reference'], unique=True)
    for col in (
        'entite_id', 'user_id', 'cree_par_account_id', 'assigne_a_account_id',
        'asset_id', 'assignment_id', 'nature_code', 'statut', 'canal',
        'niveau_securite', 'cree_le',
    ):
        op.create_index(f'ix_tickets_{col}', 'tickets', [col])

    op.create_table(
        'ticket_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('auteur_account_id', sa.Integer(), nullable=True),
        sa.Column('interne', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('contenu', sa.String(length=4000), nullable=False),
        sa.Column('cree_le', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['auteur_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ticket_comments_ticket_id', 'ticket_comments', ['ticket_id'])
    op.create_index('ix_ticket_comments_auteur_account_id', 'ticket_comments', ['auteur_account_id'])


def downgrade() -> None:
    op.drop_table('ticket_comments')
    op.drop_table('tickets')
    op.drop_table('ticket_compteurs')
    op.drop_table('ticket_natures')
