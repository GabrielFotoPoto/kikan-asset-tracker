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

"""gammes des categories de besoin et gamme souhaitee sur chaque besoin

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-30 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Gammes proposees d'office aux categories d'origine (modifiables ensuite dans le Parametrage).
DEFAUTS = {
    "PC portable avec pave numerique": ["Standard", "Haut de gamme"],
    "PC portable sans pave numerique": ["Standard", "Haut de gamme"],
    "Smartphone Apple": ["Normal", "Pro", "XL"],
}


def upgrade() -> None:
    op.add_column('besoin_categories', sa.Column('gammes', sa.JSON(), nullable=True))
    op.add_column('besoins', sa.Column('gamme', sa.String(), nullable=True))
    table = sa.table('besoin_categories', sa.column('nom', sa.String), sa.column('gammes', sa.JSON))
    for nom, gammes in DEFAUTS.items():
        op.execute(table.update().where(sa.func.lower(table.c.nom) == nom.lower()).values(gammes=gammes))


def downgrade() -> None:
    op.drop_column('besoins', 'gamme')
    op.drop_column('besoin_categories', 'gammes')
