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

"""Retention RGPD : duree et delai de grace parametrables, previsualisation, purge, quarantaine des PDF et liste pour la GED.

Reserve au role informatique. Le deroulement est decrit dans app/purge.py.
"""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import appsettings, purge
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..models import Account, PurgeDocument

router = APIRouter(
    prefix="/rgpd", tags=["rgpd"],
    dependencies=[Depends(require_roles("informatique"))],
)


class RetentionSetting(BaseModel):
    mois: int = Field(ge=0, le=purge.RETENTION_MAX)
    delai_grace_jours: int | None = Field(default=None, ge=0, le=purge.GRACE_MAX)


class PurgeRequest(BaseModel):
    ids: list[int] | None = None  # None : tous les salaries eligibles ; liste : seulement ceux de la previsualisation


class IdsRequest(BaseModel):
    ids: list[int] | None = None


def _reglages(session: Session) -> dict:
    return {"mois": purge.retention_mois(session), "delai_grace_jours": purge.delai_grace(session)}


@router.get("/retention")
def get_retention(session: Session = Depends(get_session)):
    return _reglages(session)


@router.put("/retention")
def set_retention(data: RetentionSetting, session: Session = Depends(get_session),
                  admin: Account = Depends(require_roles("informatique"))):
    before = _reglages(session)
    appsettings.put(session, purge.RETENTION_KEY, str(data.mois))
    if data.delai_grace_jours is not None:
        appsettings.put(session, purge.GRACE_KEY, str(data.delai_grace_jours))
    session.commit()
    after = _reglages(session)
    if after != before:
        audit(admin.username, "rgpd_retention",
              detail=f"conservation {before['mois']} -> {after['mois']} mois, grace {before['delai_grace_jours']} -> {after['delai_grace_jours']} jours")
    return after


@router.get("/etat")
def etat(session: Session = Depends(get_session)):
    return {**_reglages(session), **purge.etat(session)}


@router.get("/purge-preview")
def purge_preview(session: Session = Depends(get_session)):
    retention = purge.retention_mois(session)
    candidats = purge.candidats(session)
    return {
        "retention_mois": retention,
        "delai_grace_jours": purge.delai_grace(session),
        "count": len(candidats),
        "candidats": [
            {"id": u.id, "matricule": u.matricule, "nom": u.nom, "prenom": u.prenom,
             "date_sortie": str(u.date_sortie),
             "suppression_prevue": str(purge.add_months(u.date_sortie, retention))}
            for u in candidats
        ],
    }


@router.post("/purge")
def run_purge(data: PurgeRequest | None = None, session: Session = Depends(get_session),
              admin: Account = Depends(require_roles("informatique"))):
    """Purge la base ; les PDF du partage vont en quarantaine (A_PURGER), ceux de la GED sont listes pour l'equipe de la GED.

    Corps {"ids": []} : ne purge personne mais reessaie les deplacements restes en attente."""
    r = purge.purger(session, admin.username, (data.ids if data else None))
    return {"supprimes": [], **r}


@router.get("/documents")
def documents(session: Session = Depends(get_session)):
    today = date.today()
    rows = session.exec(select(PurgeDocument).order_by(PurgeDocument.echeance, PurgeDocument.id)).all()
    return {
        "aujourdhui": str(today),
        "documents": [
            {"id": d.id, "statut": d.statut, "moteur": d.moteur, "reference": d.reference, "echeance": str(d.echeance),
             "echu": d.echeance <= today, "empreinte": d.empreinte}
            for d in rows
        ],
    }


@router.post("/quarantaine/supprimer")
def supprimer_quarantaine(data: IdsRequest | None = None, session: Session = Depends(get_session),
                          admin: Account = Depends(require_roles("informatique"))):
    """Supprime definitivement les PDF de la quarantaine dont le delai de grace est ecoule (ceux qui ne le sont pas sont ignores)."""
    return purge.supprimer_echus(session, admin.username, data.ids if data else None)


@router.post("/quarantaine/restaurer")
def restaurer_quarantaine(data: IdsRequest, session: Session = Depends(get_session),
                          admin: Account = Depends(require_roles("informatique"))):
    return purge.restaurer(session, admin.username, data.ids or [])


@router.post("/ged/confirmer")
def confirmer_ged(data: IdsRequest, session: Session = Depends(get_session),
                  admin: Account = Depends(require_roles("informatique"))):
    """A appeler une fois les documents supprimes par l'equipe de la GED (SharePoint, DocuWare)."""
    return purge.confirmer_ged(session, admin.username, data.ids or [])
