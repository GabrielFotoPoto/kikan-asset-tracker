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

"""Ajout de la colonne unique accounts.external_uid pour l'identifiant stable AD/LDAP (lot G5)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("external_uid", sa.String(length=255), nullable=True))
    op.create_index("ix_accounts_external_uid", "accounts", ["external_uid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_accounts_external_uid", table_name="accounts")
    op.drop_column("accounts", "external_uid")
