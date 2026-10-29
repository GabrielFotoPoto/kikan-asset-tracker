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

"""acronyme du salarie et compteur de documents scelles (nom des PDF : AAAA_MM_JJ_NOM_PRENOM_ACR_NNN)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-02 11:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.docname import acronyme_defaut

    op.add_column('users', sa.Column('acronyme', sa.String(), nullable=True))
    op.add_column('users', sa.Column('compteur_documents', sa.Integer(), nullable=False, server_default='0'))
    bind = op.get_bind()
    # Acronyme des fiches existantes ; compteur = nombre de documents scelles deja produits pour le salarie.
    faits = dict(bind.execute(sa.text(
        "SELECT a.user_id, COUNT(DISTINCT s.ged_reference) FROM signatures s "
        "JOIN assignments a ON a.id = s.assignment_id WHERE s.ged_reference IS NOT NULL GROUP BY a.user_id"
    )).fetchall())
    for uid, prenom, nom in bind.execute(sa.text("SELECT id, prenom, nom FROM users")).fetchall():
        bind.execute(sa.text("UPDATE users SET acronyme = :a, compteur_documents = :n WHERE id = :i"),
                     {"a": acronyme_defaut(prenom, nom), "n": int(faits.get(uid, 0)), "i": uid})


def downgrade() -> None:
    op.drop_column('users', 'compteur_documents')
    op.drop_column('users', 'acronyme')
