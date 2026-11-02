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


"""unicite garantie par la base : matricule, numero de serie, identifiant interne, code d'entite

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-01 10:00:00

Jusqu'ici l'unicite n'etait verifiee que par l'application : deux creations simultanees pouvaient toutes deux reussir.
Les index sont insensibles a la casse (comme les controles et les imports) et ignorent les valeurs vides.
Si des doublons existent deja, la migration s'arrete avec la liste a corriger (rien n'est fusionne ni supprime automatiquement).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nom de l'index, table, colonne, insensible a la casse)
INDEXES = (
    ('uq_users_matricule_lower', 'users', 'matricule', True),
    ('uq_assets_numero_serie_lower', 'assets', 'numero_serie', True),
    ('uq_assets_identifiant_interne_lower', 'assets', 'identifiant_interne', True),
    ('uq_entite_code', 'entite', 'code', False),
)


def _doublons(bind) -> list[str]:
    problemes = []
    for _name, table, col, ci in INDEXES:
        expr = f"lower({col})" if ci else col
        rows = bind.execute(sa.text(
            f"SELECT {expr} AS v, count(*) AS n FROM {table} WHERE {col} IS NOT NULL AND {col} <> '' "
            f"GROUP BY {expr} HAVING count(*) > 1 ORDER BY {expr} LIMIT 20"
        )).all()
        for v, n in rows:
            problemes.append(f"  {table}.{col} = {v!r} : {n} lignes")
    return problemes


def upgrade() -> None:
    bind = op.get_bind()
    problemes = _doublons(bind)
    if problemes:
        raise RuntimeError(
            "Migration 0021 impossible : des doublons existent deja (a fusionner ou renommer, puis relancer) :\n"
            + "\n".join(problemes)
        )
    for name, table, col, ci in INDEXES:
        expr = sa.text(f"lower({col})") if ci else col
        op.create_index(name, table, [expr], unique=True,
                        postgresql_where=sa.text(f"{col} IS NOT NULL AND {col} <> ''") if ci else None)


def downgrade() -> None:
    for name, table, _col, _ci in reversed(INDEXES):
        op.drop_index(name, table_name=table)
