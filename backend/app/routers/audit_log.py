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

"""Consultation du journal d'audit (lecture seule, role informatique)."""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from ..auth import require_roles
from ..db import get_session
from ..models import AuditLog

router = APIRouter(
    prefix="/audit", tags=["audit"],
    dependencies=[Depends(require_roles("informatique"))],
)


@router.get("", response_model=list[AuditLog])
def list_audit(
    session: Session = Depends(get_session),
    actor: str | None = None,
    action: str | None = Query(default=None, description="filtre sur le debut de l'action"),
    limit: int = Query(default=200, ge=1, le=1000),
):
    stmt = select(AuditLog)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(col(AuditLog.action).startswith(action))
    return session.exec(stmt.order_by(col(AuditLog.id).desc()).limit(limit)).all()
