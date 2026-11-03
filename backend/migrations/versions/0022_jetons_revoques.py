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


"""jetons de session revoques a la deconnexion

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-03 19:00:00

Jusqu'ici la deconnexion effacait seulement le cookie : un jeton copie avant restait valable jusqu'a son expiration.
La table ne garde que l'identifiant aleatoire du jeton (jti) et sa date d'expiration, purgee ensuite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(), nullable=False),
        sa.Column('expire_le', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('jti'),
    )
    op.create_index('ix_revoked_tokens_expire_le', 'revoked_tokens', ['expire_le'])


def downgrade() -> None:
    op.drop_index('ix_revoked_tokens_expire_le', table_name='revoked_tokens')
    op.drop_table('revoked_tokens')
