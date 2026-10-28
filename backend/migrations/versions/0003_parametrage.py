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

"""parametrage : types d'actifs actifs/inactifs, services

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('asset_types', sa.Column('actif', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('asset_types', 'actif', server_default=None)
    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('actif', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_services_nom'), 'services', ['nom'], unique=False)
    op.create_index('uq_services_nom_lower', 'services', [sa.text('lower(nom)')], unique=True)
    op.create_index('uq_asset_types_nom_lower', 'asset_types', [sa.text('lower(nom)')], unique=True)
    # Les listes demarrent avec les valeurs deja saisies (une entree par nom, sans tenir compte de la casse).
    op.execute(
        "INSERT INTO asset_types (nom, actif) SELECT DISTINCT ON (lower(btrim(type))) btrim(type), true FROM assets "
        "WHERE type IS NOT NULL AND btrim(type) <> '' "
        "AND NOT EXISTS (SELECT 1 FROM asset_types t WHERE lower(t.nom) = lower(btrim(assets.type))) "
        "ORDER BY lower(btrim(type)), btrim(type)"
    )
    op.execute(
        "INSERT INTO services (nom, actif) SELECT DISTINCT ON (lower(btrim(service))) btrim(service), true FROM users "
        "WHERE service IS NOT NULL AND btrim(service) <> '' "
        "AND NOT EXISTS (SELECT 1 FROM services v WHERE lower(v.nom) = lower(btrim(users.service))) "
        "ORDER BY lower(btrim(service)), btrim(service)"
    )


def downgrade() -> None:
    op.drop_index('uq_asset_types_nom_lower', table_name='asset_types')
    op.drop_index('uq_services_nom_lower', table_name='services')
    op.drop_index(op.f('ix_services_nom'), table_name='services')
    op.drop_table('services')
    op.drop_column('asset_types', 'actif')
