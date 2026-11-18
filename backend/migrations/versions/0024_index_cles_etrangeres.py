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

"""index sur les cles etrangeres sans index

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-14 12:00:00

Dix cles etrangeres n'avaient aucun index (releve par la requete de diagnostic pg_constraint / pg_index sur la base de test). Les colonnes
entite_id servent au cloisonnement par entite ; asset_id (cles primaires composites assignment_assets et echange_retours) et
assignment_id / policy_id servent aux recherches inverses et aux controles de suppression. Migration additive : aucune donnee n'est modifiee.
Les tables sont petites (parc d'une organisation) : la creation d'index classique, brievement bloquante en ecriture, est suffisante.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, colonne) : nom de l'index = ix_<table>_<colonne>, comme celui genere par SQLModel (index=True)
INDEXES = (
    ('users', 'entite_id'),
    ('assets', 'entite_id'),
    ('applications', 'entite_id'),
    ('policies', 'entite_id'),
    ('assignments', 'policy_id'),
    ('assignment_assets', 'asset_id'),
    ('echange_retours', 'asset_id'),
    ('account_scopes', 'entite_id'),
    ('api_token_scopes', 'entite_id'),
    ('besoins', 'assignment_id'),
)


def upgrade() -> None:
    for table, col in INDEXES:
        op.create_index(f'ix_{table}_{col}', table, [col], if_not_exists=True)


def downgrade() -> None:
    for table, col in reversed(INDEXES):
        op.drop_index(f'ix_{table}_{col}', table_name=table, if_exists=True)
