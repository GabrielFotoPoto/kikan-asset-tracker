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

"""Etat de la sauvegarde (lecture seule, informatique) : Kikan ne declenche rien, il lit l'etat ecrit par l'outil de sauvegarde."""
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends

from ..auth import require_roles

router = APIRouter(prefix="/backup", tags=["backup"], dependencies=[Depends(require_roles("informatique"))])


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


@router.get("/status")
def status():
    threshold = int(os.environ.get("KIKAN_BACKUP_ALERT_HOURS", "36") or 36)
    path = Path(os.environ.get("KIKAN_BACKUP_STATUS_DIR", "/backupstatus")) / "status.json"
    base = {"seuil_heures": threshold}
    try:
        data = json.loads(path.read_text()) if path.is_file() else None
    except (OSError, ValueError):
        data = None
    if not data:
        return {**base, "configure": False, "alerte": True, "message": "Aucune sauvegarde enregistree : voir docs/SAUVEGARDE.md"}
    success = _parse(data.get("dernier_succes"))
    age = round((datetime.utcnow() - success).total_seconds() / 3600, 1) if success else None
    failure = data.get("dernier_echec")
    return {
        **base, "configure": True, "dernier_succes": data.get("dernier_succes"), "age_heures": age, "fichier": data.get("fichier"),
        "taille": data.get("taille"), "conserves": data.get("conserves"), "supprimees": data.get("supprimees"),
        "destination": data.get("destination"), "retention": data.get("retention"), "duree_s": data.get("duree_s"),
        "dernier_echec": failure, "message": data.get("message"),
        "alerte": age is None or age > threshold or bool(failure),
    }
