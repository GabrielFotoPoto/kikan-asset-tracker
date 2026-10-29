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

"""Revue periodique des droits d'acces : rapport, anomalies, campagnes (voir app/revue_acces.py).

Lecture : tous les roles, dans leur perimetre. Decisions : RH (dans leur perimetre) et informatique.
Lancement, cloture, rapport scelle et confirmation des retraits : informatique.
"""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from .. import filestore, revue_acces, xlsx_io
from ..auth import get_current_account, require_roles, writer_guard
from ..db import get_session
from ..models import Account, RevueAcces, RevueLigne, User
from ..scope import Scope, scope_dep
from .reports import _safe_cell

router = APIRouter(prefix="/revues", tags=["revues"], dependencies=[Depends(writer_guard("rh", "informatique"))])

COLONNES = [("matricule", "Matricule"), ("salarie", "Salarie"), ("entite", "Entite"), ("service", "Service"), ("statut_salarie", "Statut du salarie"),
            ("application", "Application"), ("acces", "Acces"), ("note", "Precision"), ("attribue_par", "Attribue par"),
            ("date_maj", "Mis a jour le"), ("anomalie", "Anomalie")]


class RevueIn(BaseModel):
    titre: str = Field(min_length=1, max_length=120)
    echeance: date | None = None
    entite_ids: list[int] = []
    application_ids: list[int] = []


class DecisionIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    decision: str
    commentaire: str | None = Field(default=None, max_length=200)


class IdsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


def _revue(session: Session, revue_id: int) -> RevueAcces:
    revue = session.get(RevueAcces, revue_id)
    if not revue:
        raise HTTPException(404, "Revue introuvable")
    return revue


@router.get("/anomalies")
def get_anomalies(session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Acces actifs qui posent probleme (salarie sorti, date de sortie depassee, application desactivee), dans le perimetre."""
    rows = revue_acces.anomalies(session, scope)
    return {"count": len(rows), "anomalies": rows}


@router.get("/acces")
def get_acces(format: str = Query("json", pattern="^(json|csv|xlsx)$"), entite_id: int | None = None, application_id: int | None = None,
              session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    """Rapport "qui a acces a quoi", dans le perimetre (filtres : entite, application ; export CSV ou Excel)."""
    if entite_id is not None and not scope.allows(entite_id):
        raise HTTPException(404, "Entite introuvable")
    rows = revue_acces.acces(session, scope, entite_id, application_id)
    jour = date.today().isoformat()
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow([label for _, label in COLONNES])
        for r in rows:
            w.writerow([_safe_cell(r[k]) for k, _ in COLONNES])
        return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="kikan-acces-{jour}.csv"'})
    if format == "xlsx":
        return Response(xlsx_io.build_table("Acces", [label for _, label in COLONNES], [[r[k] for k, _ in COLONNES] for r in rows], {9}),
                        media_type=xlsx_io.XLSX_MIME, headers={"Content-Disposition": f'attachment; filename="kikan-acces-{jour}.xlsx"'})
    return {"date": jour, "count": len(rows), "rows": rows}


@router.get("")
def list_revues(session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    out = []
    for r in session.exec(select(RevueAcces).order_by(RevueAcces.id.desc())).all():
        c = revue_acces.compteurs(session, r.id, scope)
        if c["total"] or scope.globale:
            out.append({"id": r.id, "titre": r.titre, "statut": r.statut, "cree_le": r.cree_le, "cree_par": r.cree_par, "echeance": r.echeance,
                        "cloture_le": r.cloture_le, "cloture_par": r.cloture_par, "rapport": bool(r.rapport_ref), **c})
    return out


@router.post("", status_code=201, dependencies=[Depends(require_roles("informatique"))])
def create_revue(data: RevueIn, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    revue = revue_acces.creer(session, account, data.titre.strip(), data.echeance, data.entite_ids, data.application_ids)
    return {"id": revue.id, "titre": revue.titre, **revue_acces.compteurs(session, revue.id, Scope(True))}


@router.get("/retraits", dependencies=[Depends(require_roles("informatique"))])
def list_retraits(session: Session = Depends(get_session)):
    """Acces passes a "non" dans Kikan et dont le retrait reste a faire (ou a confirmer) dans l'application concernee."""
    return revue_acces.retraits(session)


@router.post("/retraits/confirmer", dependencies=[Depends(require_roles("informatique"))])
def confirm_retraits(data: IdsIn, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    return {"confirmes": revue_acces.confirmer_retraits(session, account, data.ids)}


@router.get("/{revue_id}")
def get_revue(revue_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    r = _revue(session, revue_id)
    c = revue_acces.compteurs(session, r.id, scope)
    if not c["total"] and not scope.globale:
        raise HTTPException(404, "Revue introuvable")
    return {"id": r.id, "titre": r.titre, "statut": r.statut, "cree_le": r.cree_le, "cree_par": r.cree_par, "echeance": r.echeance, "cloture_le": r.cloture_le,
            "cloture_par": r.cloture_par, "perimetre": r.perimetre, "rapport": bool(r.rapport_ref), "empreinte": r.rapport_empreinte, **c}


@router.get("/{revue_id}/lignes")
def get_lignes(revue_id: int, decision: str | None = Query(None, pattern="^(a_traiter|maintenu|a_retirer)$"), anomalies: bool = False, q: str | None = None,
               limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
               session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    _revue(session, revue_id)

    def filtre(stmt):
        stmt = scope.where(stmt.join(User, User.id == RevueLigne.user_id, isouter=True).where(RevueLigne.revue_id == revue_id), RevueLigne.entite_id)
        if decision:
            stmt = stmt.where(RevueLigne.decision == decision)
        if anomalies:
            stmt = stmt.where(RevueLigne.anomalie.is_not(None))
        if q:
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(RevueLigne.application).like(like) | func.lower(func.coalesce(RevueLigne.matricule, "")).like(like)
                              | func.lower(func.coalesce(User.nom, "")).like(like) | func.lower(func.coalesce(User.prenom, "")).like(like))
        return stmt

    total = session.exec(filtre(select(func.count(RevueLigne.id)).select_from(RevueLigne))).one()
    rows = session.exec(filtre(select(RevueLigne, User)).order_by(RevueLigne.id).offset(offset).limit(limit)).all()
    return {"total": total, "lignes": [
        {"id": l.id, "matricule": l.matricule, "salarie": f"{u.prenom} {u.nom}".strip() if u else None, "application": l.application, "note": l.note,
         "anomalie": l.anomalie, "decision": l.decision, "commentaire": l.commentaire, "decide_par": l.decide_par, "decide_le": l.decide_le,
         "retrait": l.retrait} for l, u in rows]}


@router.post("/{revue_id}/decisions")
def post_decisions(revue_id: int, data: DecisionIn, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep),
                   account: Account = Depends(get_current_account)):
    r = _revue(session, revue_id)
    return {"mises_a_jour": revue_acces.decider(session, account, scope, r, data.ids, data.decision, data.commentaire)}


@router.post("/{revue_id}/cloturer", dependencies=[Depends(require_roles("informatique"))])
def post_cloturer(revue_id: int, session: Session = Depends(get_session), account: Account = Depends(get_current_account)):
    return revue_acces.cloturer(session, account, _revue(session, revue_id))


@router.get("/{revue_id}/rapport", dependencies=[Depends(require_roles("informatique"))])
def get_rapport(revue_id: int, session: Session = Depends(get_session)):
    r = _revue(session, revue_id)
    if not r.rapport_ref:
        raise HTTPException(404, "Le rapport n'existe qu'une fois la revue cloturee")
    try:
        data = filestore.read_document(r.rapport_ref)
    except filestore.StorageError as exc:
        raise HTTPException(503, f"Rapport momentanement indisponible : {exc}") from exc
    if filestore.sha256_hex(data) != r.rapport_empreinte:
        raise HTTPException(409, "Le rapport stocke ne correspond plus a son empreinte : document altere")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="revue-acces-{r.id}.pdf"'})
