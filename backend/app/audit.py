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

"""Journal d'audit : ecritures dans une session dediee (conservees meme si la requete echoue)."""
import logging

from sqlmodel import Session

from .db import engine
from .models import AuditLog

log = logging.getLogger("kikan.audit")


def audit(actor: str, action: str, *, target: str | None = None, status: int | None = None,
          ip: str | None = None, detail: str | None = None) -> None:
    try:
        with Session(engine) as session:
            session.add(AuditLog(actor=actor, action=action, target=target,
                                 status=status, ip=ip, detail=detail))
            session.commit()
    except Exception:  # noqa: BLE001  (ne jamais faire echouer la requete a cause du journal)
        log.exception("Echec d'ecriture du journal d'audit")
