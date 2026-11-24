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

from .. import attachments as att_svc, filestore as storage
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..models import Account, Attachment, Signature

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
    pj_per_backend: Counter = Counter()
    pj_pending = 0
    pj_total = 0
    for att in session.exec(select(Attachment)).all():
        pj_total += 1
        try:
            pj_per_backend[storage.parse_reference(att.storage_ref)[0]] += 1
        except storage.StorageError:
            pass
        if storage.is_attachment_pending(att.storage_ref):
            pj_pending += 1
    pj_active = storage.attachments_active_name()
    return {
        "active": storage.ACTIVE,
        "backends": list(storage.BACKENDS),
        "description": storage.describe_active(),
        "documents_seulement": storage.ACTIVE in storage.DOCUMENT_ONLY,
        "documents": {"par_backend": dict(per_backend), "en_attente_de_depot": pending,
                      "references_illisibles": unreadable},
        "pieces_jointes": {
            "active": pj_active,
            "config_raw": storage.ATTACHMENTS_BACKEND_RAW,
            "description": storage.describe_attachments(),
            "par_backend": dict(pj_per_backend),
            "total": pj_total,
            "en_attente_de_depot": pj_pending,
            "volume_octets": att_svc.volume_total_octets(session),
            "plafond_octets": att_svc.plafond_global_mio(session) * 1024 * 1024,
            "espace_libre_octets": storage.archive_disk_free_bytes(),
        },
    }


@router.post("/test")
def test_connection():
    """Ecrit, relit et supprime un petit fichier de test sur le stockage actif."""
    return storage.check_active()


@router.post("/migrer")
def migrate(dry_run: bool = True, session: Session = Depends(get_session),
            admin: Account = Depends(require_roles("informatique"))):
    """Copie vers le moteur actif les documents rangés sur un autre moteur distant (simulation par defaut, aucune suppression)."""
    result = storage.migrate_to_active(session, dry_run=dry_run)
    if not dry_run:
        audit(admin.username, "stockage_copie", detail=f"{result['copies']} copie(s), {result['echecs']} echec(s)")
    return result


@router.post("/sync")
def sync(session: Session = Depends(get_session)):
    """Depose sur le partage distant les documents restes dans le tampon local."""
    return storage.sync_pending(session)


@router.post("/pieces-jointes/test")
def test_attachments_connection():
    """Teste ecriture, lecture et suppression sur le stockage dedie aux pieces jointes."""
    return storage.check_attachments()


@router.post("/pieces-jointes/sync")
def sync_attachments(session: Session = Depends(get_session)):
    """Depose sur le stockage PJ distant les pieces jointes restees dans le tampon local."""
    return storage.sync_pending_attachments(session)
