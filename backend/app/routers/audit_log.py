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
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session, col, select

from ..auth import require_roles
from ..db import get_session
from ..models import AuditLog
from ..rules import count

router = APIRouter(
    prefix="/audit", tags=["audit"],
    dependencies=[Depends(require_roles("informatique"))],
)

# Colonnes triables : liste blanche (le nom vient de l'appelant, il ne doit jamais atteindre la requete tel quel).
TRIS = {
    "id": col(AuditLog.id), "ts": col(AuditLog.ts), "actor": col(AuditLog.actor),
    "action": col(AuditLog.action), "status": col(AuditLog.status), "ip": col(AuditLog.ip),
}


@router.get("", response_model=list[AuditLog])
def list_audit(
    response: Response,
    session: Session = Depends(get_session),
    actor: str | None = None,
    action: str | None = Query(default=None, description="filtre sur le debut de l'action"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, description="nombre de lignes a sauter (pagination)"),
    tri: Literal["id", "ts", "actor", "action", "status", "ip"] = Query(default="id", description="colonne de tri"),
    sens: Literal["asc", "desc"] = Query(default="desc", description="sens du tri"),
):
    """Entrees du journal, les plus recentes d'abord par defaut. `X-Total-Count` donne le nombre total d'entrees
    qui verifient les filtres (toutes pages confondues), pour paginer avec `limit` et `offset`."""
    conditions = []
    if actor:
        conditions.append(AuditLog.actor == actor)
    if action:
        conditions.append(col(AuditLog.action).startswith(action))
    response.headers["X-Total-Count"] = str(count(session, AuditLog, *conditions))
    colonne = TRIS[tri]
    ordre = colonne.asc() if sens == "asc" else colonne.desc()
    # Valeurs vides (statut, IP) toujours en fin ; a valeur egale, l'ordre d'insertion departage dans le meme sens.
    stmt = (select(AuditLog).where(*conditions)
            .order_by(ordre.nulls_last(), col(AuditLog.id).asc() if sens == "asc" else col(AuditLog.id).desc())
            .offset(offset).limit(limit))
    return session.exec(stmt).all()
