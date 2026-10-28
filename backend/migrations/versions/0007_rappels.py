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

"""rappels par e-mail : suivi des envois

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reminder_sent',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('cle', sa.String(), nullable=False),
        sa.Column('destinataire', sa.String(), nullable=False),
        sa.Column('envoye_le', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reminder_sent_kind'), 'reminder_sent', ['kind'])
    op.create_index(op.f('ix_reminder_sent_cle'), 'reminder_sent', ['cle'])
    op.create_index(op.f('ix_reminder_sent_destinataire'), 'reminder_sent', ['destinataire'])


def downgrade() -> None:
    op.drop_table('reminder_sent')
