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

"""SSO Microsoft 365 : origine du compte, identifiant Entra, compte de secours

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('source_auth', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='local'))
    op.add_column('accounts', sa.Column('sso_oid', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('accounts', sa.Column('sso_upn', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('accounts', sa.Column('secours', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('accounts', 'source_auth', server_default=None)
    op.alter_column('accounts', 'secours', server_default=None)
    op.create_unique_constraint('uq_accounts_sso_oid', 'accounts', ['sso_oid'])
    # Les comptes locaux informatique deja presents restent utilisables en secours : rien ne les bloque a l'activation.
    op.execute("UPDATE accounts SET secours = true WHERE role = 'informatique'")


def downgrade() -> None:
    op.drop_constraint('uq_accounts_sso_oid', 'accounts', type_='unique')
    for col in ('secours', 'sso_upn', 'sso_oid', 'source_auth'):
        op.drop_column('accounts', col)
