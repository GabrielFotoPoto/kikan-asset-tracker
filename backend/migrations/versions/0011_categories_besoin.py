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

"""categories de besoin (liste geree par l'informatique, distincte des types d'actifs)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PAR_DEFAUT = [
    "PC portable avec pave numerique",
    "PC portable sans pave numerique",
    "Smartphone Apple",
    "Smartphone Android",
]


def upgrade() -> None:
    table = op.create_table(
        'besoin_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nom', sa.String(), nullable=False),
        sa.Column('actif', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_besoin_categories_nom'), 'besoin_categories', ['nom'])
    op.create_index('uq_besoin_categories_nom_lower', 'besoin_categories', [sa.text('lower(nom)')], unique=True)
    bind = op.get_bind()
    # Les besoins deja saisis gardent leur libelle : il devient une categorie, pour rester valide et modifiable.
    existants = [r[0] for r in bind.execute(sa.text("SELECT DISTINCT type FROM besoins")).fetchall()]
    vus: set[str] = set()
    lignes = []
    for nom in [*existants, *PAR_DEFAUT]:
        if nom and nom.lower() not in vus:
            vus.add(nom.lower())
            lignes.append({"nom": nom, "actif": True})
    if lignes:
        op.bulk_insert(table, lignes)


def downgrade() -> None:
    op.drop_table('besoin_categories')
