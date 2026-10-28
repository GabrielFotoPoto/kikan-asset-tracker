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

"""comptes nominatifs : nom, e-mail, mot de passe provisoire, revocation de sessions, derniere connexion

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('nom_affiche', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('accounts', sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('accounts', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('accounts', sa.Column('token_epoch', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('accounts', sa.Column('derniere_connexion', sa.DateTime(), nullable=True))
    op.alter_column('accounts', 'must_change_password', server_default=None)
    op.alter_column('accounts', 'token_epoch', server_default=None)
    # Identifiants uniques sans tenir compte de la casse (admin et Admin ne peuvent plus coexister).
    op.create_index('uq_accounts_username_lower', 'accounts', [sa.text('lower(username)')], unique=True)


def downgrade() -> None:
    op.drop_index('uq_accounts_username_lower', table_name='accounts')
    for col in ('derniere_connexion', 'token_epoch', 'must_change_password', 'email', 'nom_affiche'):
        op.drop_column('accounts', col)
