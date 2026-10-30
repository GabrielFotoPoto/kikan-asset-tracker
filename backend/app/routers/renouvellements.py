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

"""Renouvellements (informatique) : materiel a renouveler, detenteur, report ou avancement de l'echeance.

L'informatique est seule a decider du renouvellement : l'echeance n'est qu'un repere. Elle peut renouveler avant ou apres, et
reporter (ou avancer) l'echeance d'un materiel, avec un motif facultatif conserve dans un historique (jamais dans le journal
d'audit, qui ne recoit que des dates). Seul le materiel en stock ou affecte est concerne : un materiel rendu ou reforme n'est
plus a renouveler. Le renouvellement lui-meme est l'echange de materiel (page /renouveler)."""
import calendar
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from ..audit import audit
from ..auth import get_current_account, require_roles
from ..db import get_session
from ..models import (Account, Asset, AssetStatus, Assignment, AssignmentAsset, EcheanceReport, Entite, User)
from ..scope import Scope, restreindre_entite, scope_dep

router = APIRouter(
    prefix="/renouvellements", tags=["renouvellements"],
    dependencies=[Depends(require_roles("informatique"))],
)

A_RENOUVELER = (AssetStatus.stock, AssetStatus.affecte)


def _situation(echeance: date, today: date) -> str:
    if echeance < today:
        return "en_retard"
    fin_du_mois = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    return "ce_mois" if echeance <= fin_du_mois else "a_venir"


def _ajouter_mois(jour: date, n: int) -> date:
    index = jour.year * 12 + jour.month - 1 + n
    annee, mois = index // 12, index % 12 + 1
    return date(annee, mois, min(jour.day, calendar.monthrange(annee, mois)[1]))


def _fiche(session: Session, a: Asset, today: date, entites: dict, detenteurs: dict, reports: dict) -> dict:
    user = detenteurs.get(a.id)
    dernier = reports.get(a.id)
    return {
        "id": a.id, "identifiant_interne": a.identifiant_interne, "type": a.type, "marque": a.marque, "modele": a.modele,
        "numero_serie": a.numero_serie, "statut": a.statut.value, "entite": entites.get(a.entite_id),
        "echeance": a.echeance_renouvellement.isoformat(), "jours": (a.echeance_renouvellement - today).days,
        "situation": _situation(a.echeance_renouvellement, today),
        "detenteur": {"id": user.id, "nom": f"{user.prenom} {user.nom}".strip()} if user else None,
        "dernier_report": {"le": dernier.le.date().isoformat(), "par": dernier.par, "ancienne": dernier.ancienne.isoformat() if dernier.ancienne else None,
                           "nouvelle": dernier.nouvelle.isoformat() if dernier.nouvelle else None, "motif": dernier.motif} if dernier else None,
    }


@router.get("")
def lister(
    horizon_mois: int = Query(3, ge=0, le=24),   # 0 : seulement les echeances depassees
    entite_id: int | None = None,
    session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep),
):
    """Materiel dont l'echeance est depassee ou tombe dans l'horizon, avec son detenteur et le dernier report."""
    today = date.today()
    scope, entite = restreindre_entite(session, scope, entite_id)
    limite = _ajouter_mois(today, horizon_mois) if horizon_mois else today - timedelta(days=1)
    actifs = [a for a in session.exec(scope.where(select(Asset), Asset.entite_id)
                                       .where(Asset.echeance_renouvellement.is_not(None))).all()
              if a.statut in A_RENOUVELER and a.echeance_renouvellement <= limite]
    ids = [a.id for a in actifs]
    entites = {e.id: e.nom for e in session.exec(select(Entite)).all()}
    detenteurs: dict[int, User] = {}
    if ids:
        for asset_id, user_id in session.exec(
                select(AssignmentAsset.asset_id, Assignment.user_id)
                .join(Assignment, Assignment.id == AssignmentAsset.assignment_id)
                .where(AssignmentAsset.asset_id.in_(ids), Assignment.statut == "en_cours", AssignmentAsset.date_retour.is_(None))):
            detenteurs[asset_id] = session.get(User, user_id)
    reports: dict[int, EcheanceReport] = {}
    if ids:
        for r in session.exec(select(EcheanceReport).where(EcheanceReport.asset_id.in_(ids)).order_by(EcheanceReport.id)):
            reports[r.asset_id] = r
    items = [_fiche(session, a, today, entites, detenteurs, reports) for a in sorted(actifs, key=lambda x: (x.echeance_renouvellement, x.id))]
    totaux = {k: sum(1 for i in items if i["situation"] == k) for k in ("en_retard", "ce_mois", "a_venir")}
    return {"date": today.isoformat(), "horizon_mois": horizon_mois, "filtres": {"entite_id": entite.id if entite else None},
            "totaux": totaux, "items": items}


class ReportIn(BaseModel):
    nouvelle: date | None = None   # vide : aucun renouvellement prevu
    motif: str | None = Field(default=None, max_length=200)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str | None) -> str | None:
        return re.sub(r"[\x00-\x1f\x7f\s]+", " ", v or "").strip() or None


@router.post("/{asset_id}/reporter")
def reporter(asset_id: int, data: ReportIn, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep),
             account: Account = Depends(get_current_account)):
    """Reporte ou avance l'echeance de renouvellement d'un materiel (ou la supprime). Historique conserve, motif facultatif."""
    asset = session.exec(select(Asset).where(Asset.id == asset_id).with_for_update()).first()
    if not asset or not scope.allows(asset.entite_id):
        raise HTTPException(404, "Materiel introuvable")
    if asset.statut not in A_RENOUVELER:
        raise HTTPException(409, "Ce materiel n'est plus a renouveler (rendu ou reforme)")
    if data.nouvelle is not None and data.nouvelle < date.today():
        raise HTTPException(400, "La nouvelle echeance ne peut pas etre dans le passe")
    ancienne = asset.echeance_renouvellement
    if data.nouvelle == ancienne:
        raise HTTPException(409, "Cette echeance est deja celle du materiel")
    asset.echeance_renouvellement = data.nouvelle
    session.add(asset)
    session.add(EcheanceReport(asset_id=asset.id, ancienne=ancienne, nouvelle=data.nouvelle, motif=data.motif, par=account.username))
    session.commit()
    audit(account.username, "echeance_reportee", target=str(asset.id),
          detail=f"{ancienne or 'aucune'} -> {data.nouvelle or 'aucune'}")   # dates seulement : jamais le motif
    return {"id": asset.id, "echeance": data.nouvelle.isoformat() if data.nouvelle else None}
