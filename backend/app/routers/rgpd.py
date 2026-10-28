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

"""Retention RGPD : duree parametrable, previsualisation et purge des salaries sortis.

La suppression est en deux temps : previsualisation (liste) puis purge explicite
(validee par l'admin dans l'interface).
"""
import calendar
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import require_roles
from ..db import get_session
from ..models import (
    Assignment,
    AssignmentAsset,
    EmployeeStatus,
    Setting,
    Signature,
    User,
    UserApplication,
)
from ..filestore import delete_document

router = APIRouter(
    prefix="/rgpd", tags=["rgpd"],
    dependencies=[Depends(require_roles("informatique"))],
)

RETENTION_KEY = "retention_apres_sortie_mois"
RETENTION_DEFAUT = 36  # 3 ans


class RetentionSetting(BaseModel):
    mois: int


def _get_retention(session: Session) -> int:
    row = session.get(Setting, RETENTION_KEY)
    if row and row.value and row.value.isdigit():
        return int(row.value)
    return RETENTION_DEFAUT


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _candidats(session: Session) -> list[User]:
    """Salaries sortis dont la date de sortie + retention est atteinte."""
    retention = _get_retention(session)
    today = date.today()
    out = []
    users = session.exec(
        select(User).where(User.statut == EmployeeStatus.sorti)
    ).all()
    for u in users:
        if u.date_sortie and _add_months(u.date_sortie, retention) <= today:
            out.append(u)
    return out


@router.get("/retention")
def get_retention(session: Session = Depends(get_session)):
    return {"mois": _get_retention(session)}


@router.put("/retention")
def set_retention(data: RetentionSetting, session: Session = Depends(get_session)):
    if data.mois < 0:
        data.mois = 0
    row = session.get(Setting, RETENTION_KEY)
    if row:
        row.value = str(data.mois)
    else:
        row = Setting(key=RETENTION_KEY, value=str(data.mois))
    session.add(row)
    session.commit()
    return {"mois": data.mois}


@router.get("/purge-preview")
def purge_preview(session: Session = Depends(get_session)):
    retention = _get_retention(session)
    candidats = _candidats(session)
    return {
        "retention_mois": retention,
        "count": len(candidats),
        "candidats": [
            {"id": u.id, "matricule": u.matricule, "nom": u.nom, "prenom": u.prenom,
             "date_sortie": str(u.date_sortie),
             "suppression_prevue": str(_add_months(u.date_sortie, retention))}
            for u in candidats
        ],
    }


@router.post("/purge")
def purge(session: Session = Depends(get_session)):
    candidats = _candidats(session)
    supprimes = []
    documents: list[str] = []
    for user in candidats:
        assignments = session.exec(
            select(Assignment).where(Assignment.user_id == user.id)
        ).all()
        for assignment in assignments:
            # Signatures (et fichiers PDF locaux lies) + liens d'actifs.
            sigs = session.exec(
                select(Signature).where(Signature.assignment_id == assignment.id)
            ).all()
            for sig in sigs:
                if sig.ged_reference:
                    documents.append(sig.ged_reference)  # supprime apres la validation en base
                session.delete(sig)
            for link in session.exec(
                select(AssignmentAsset).where(AssignmentAsset.assignment_id == assignment.id)
            ).all():
                session.delete(link)
            # Sans relation declaree entre les modeles, SQLAlchemy ne garantit pas l'ordre des
            # suppressions : on vide d'abord les enfants (signatures, liens) avant le parent.
            session.flush()
            session.delete(assignment)
        session.flush()
        for ua in session.exec(
            select(UserApplication).where(UserApplication.user_id == user.id)
        ).all():
            session.delete(ua)
        session.flush()
        supprimes.append({"id": user.id, "nom": user.nom, "prenom": user.prenom})
        session.delete(user)
    session.commit()
    # Fichiers supprimes seulement une fois la base validee (volume local, partage SMB ou WebDAV).
    for reference in documents:
        delete_document(reference)
    return {"supprimes": supprimes, "count": len(supprimes), "documents_supprimes": len(documents)}
