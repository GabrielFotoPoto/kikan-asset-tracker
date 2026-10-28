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

"""Supervision du stockage des PDF scelles (role informatique)."""
from collections import Counter

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from .. import filestore as storage
from ..auth import require_roles
from ..db import get_session
from ..models import Signature

router = APIRouter(
    prefix="/storage", tags=["storage"],
    dependencies=[Depends(require_roles("informatique"))],
)


@router.get("/status")
def status(session: Session = Depends(get_session)):
    """Etat du stockage : backend actif et repartition des documents (sans connexion distante)."""
    per_backend: Counter = Counter()
    pending = 0
    unreadable = 0
    for sig in session.exec(select(Signature)).all():
        if not sig.ged_reference:
            continue
        try:
            per_backend[storage.parse_reference(sig.ged_reference)[0]] += 1
        except storage.StorageError:
            unreadable += 1
        if storage.is_pending(sig.ged_reference):
            pending += 1
    return {
        "active": storage.ACTIVE,
        "backends": list(storage.BACKENDS),
        "documents": {"par_backend": dict(per_backend), "en_attente_de_depot": pending,
                      "references_illisibles": unreadable},
    }


@router.post("/test")
def test_connection():
    """Ecrit, relit et supprime un petit fichier de test sur le stockage actif."""
    return storage.check_active()


@router.post("/sync")
def sync(session: Session = Depends(get_session)):
    """Depose sur le partage distant les documents restes dans le tampon local."""
    return storage.sync_pending(session)
