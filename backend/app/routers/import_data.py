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

import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..auth import writer_guard
from ..db import get_session
from ..importer import as_bool, as_date, as_str, read_rows
from ..models import (
    Application,
    Asset,
    AssetStatus,
    Assignment,
    AssignmentAsset,
    EmployeeStatus,
    Entite,
    User,
    UserApplication,
)

router = APIRouter(
    prefix="/import", tags=["import"],
    dependencies=[Depends(writer_guard("informatique"))],
)

MAX_IMPORT_BYTES = int(os.environ.get("KIKAN_MAX_IMPORT_MB", "5")) * 1024 * 1024
MAX_IMPORT_ROWS = int(os.environ.get("KIKAN_MAX_IMPORT_ROWS", "20000"))

KINDS = ["entites", "applications", "utilisateurs", "materiel", "affectations", "acces_applicatifs"]


class Report:
    def __init__(self, kind: str, dry_run: bool):
        self.kind = kind
        self.dry_run = dry_run
        self.total = 0
        self.imported = 0
        self.skipped = 0
        self.errors: list[dict] = []

    def error(self, ligne: int, message: str):
        self.errors.append({"ligne": ligne, "message": message})

    def dict(self):
        return {
            "kind": self.kind,
            "dry_run": self.dry_run,
            "total": self.total,
            "imported": self.imported,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def _entite_map(session: Session) -> dict[str, int]:
    return {e.code: e.id for e in session.exec(select(Entite)).all()}


def _import_entites(rows, session, rep):
    existing = set(_entite_map(session).keys())
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        code = as_str(row.get("code"))
        nom = as_str(row.get("nom"))
        if not code or not nom:
            rep.error(i, "code et nom obligatoires")
            continue
        if code in existing:
            rep.skipped += 1
            continue
        obj = Entite(code=code, nom=nom, code_parent=as_str(row.get("code_parent")),
                     actif=as_bool(row.get("actif")))
        session.add(obj)
        existing.add(code)
        rep.imported += 1


def _import_applications(rows, session, rep):
    emap = _entite_map(session)
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        nom = as_str(row.get("nom"))
        if not nom:
            rep.error(i, "nom obligatoire")
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        session.add(Application(nom=nom, description=as_str(row.get("description")),
                                entite_id=entite_id, actif=as_bool(row.get("actif"))))
        rep.imported += 1


def _import_utilisateurs(rows, session, rep):
    emap = _entite_map(session)
    existing_mat = {u.matricule for u in session.exec(select(User)).all() if u.matricule}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        nom, prenom = as_str(row.get("nom")), as_str(row.get("prenom"))
        if not nom or not prenom:
            rep.error(i, "nom et prenom obligatoires")
            continue
        matricule = as_str(row.get("matricule"))
        if matricule and matricule in existing_mat:
            rep.skipped += 1
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        try:
            statut = EmployeeStatus(as_str(row.get("statut")) or "actif")
        except ValueError:
            rep.error(i, f"statut invalide: {row.get('statut')}")
            continue
        try:
            date_arr = as_date(row.get("date_arrivee"))
        except ValueError:
            rep.error(i, "date_arrivee invalide (attendu AAAA-MM-JJ)")
            continue
        session.add(User(matricule=matricule, nom=nom, prenom=prenom, entite_id=entite_id,
                         email=as_str(row.get("email")), service=as_str(row.get("service")),
                         statut=statut, date_arrivee=date_arr))
        if matricule:
            existing_mat.add(matricule)
        rep.imported += 1


def _import_materiel(rows, session, rep):
    emap = _entite_map(session)
    existing_sn = {a.numero_serie for a in session.exec(select(Asset)).all() if a.numero_serie}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        sn = as_str(row.get("numero_serie"))
        if sn and sn in existing_sn:
            rep.error(i, f"numero de serie deja present: {sn}")
            continue
        code_ent = as_str(row.get("code_entite"))
        entite_id = emap.get(code_ent) if code_ent else None
        if code_ent and entite_id is None:
            rep.error(i, f"entite inconnue: {code_ent}")
            continue
        try:
            statut = AssetStatus(as_str(row.get("statut")) or "stock")
            d_achat = as_date(row.get("date_achat"))
            d_gar = as_date(row.get("fin_garantie"))
            d_ren = as_date(row.get("echeance_renouvellement"))
        except ValueError as exc:
            rep.error(i, f"valeur invalide: {exc}")
            continue
        session.add(Asset(
            identifiant_interne=as_str(row.get("identifiant_interne")),
            type=as_str(row.get("type")), marque=as_str(row.get("marque")),
            modele=as_str(row.get("modele")), numero_serie=sn,
            date_achat=d_achat, fin_garantie=d_gar, echeance_renouvellement=d_ren,
            statut=statut, entite_id=entite_id, notes=as_str(row.get("notes")),
            source="import",
        ))
        if sn:
            existing_sn.add(sn)
        rep.imported += 1


def _import_affectations(rows, session, rep):
    users = {u.matricule: u for u in session.exec(select(User)).all() if u.matricule}
    assets = {a.identifiant_interne: a for a in session.exec(select(Asset)).all() if a.identifiant_interne}
    # Regroupe par salarie : une affectation par salarie avec tous ses actifs.
    groupes: dict[str, dict] = {}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        mat = as_str(row.get("matricule_utilisateur"))
        ident = as_str(row.get("identifiant_interne_actif"))
        if not mat or not ident:
            rep.error(i, "matricule_utilisateur et identifiant_interne_actif obligatoires")
            continue
        if mat not in users:
            rep.error(i, f"salarie inconnu: {mat}")
            continue
        if ident not in assets:
            rep.error(i, f"actif inconnu: {ident}")
            continue
        asset = assets[ident]
        if asset.statut == AssetStatus.affecte:
            rep.error(i, f"actif deja affecte: {ident}")
            continue
        try:
            d = as_date(row.get("date_remise"))
        except ValueError:
            rep.error(i, "date_remise invalide")
            continue
        g = groupes.setdefault(mat, {"user": users[mat], "assets": [], "date": None})
        g["assets"].append(asset)
        if d and (g["date"] is None or d < g["date"]):
            g["date"] = d

    for g in groupes.values():
        when = datetime.combine(g["date"], datetime.min.time()) if g["date"] else datetime.utcnow()
        assignment = Assignment(user_id=g["user"].id, date_remise=when,
                                statut="en_cours", cree_par="import")
        session.add(assignment)
        session.flush()  # pour obtenir l'id sans commit
        for asset in g["assets"]:
            asset.statut = AssetStatus.affecte
            session.add(asset)
            session.add(AssignmentAsset(assignment_id=assignment.id, asset_id=asset.id))
            rep.imported += 1


def _import_acces(rows, session, rep):
    users = {u.matricule: u for u in session.exec(select(User)).all() if u.matricule}
    apps = {a.nom: a for a in session.exec(select(Application)).all()}
    for i, row in enumerate(rows, start=2):
        rep.total += 1
        mat = as_str(row.get("matricule_utilisateur"))
        app_nom = as_str(row.get("application"))
        if not mat or not app_nom:
            rep.error(i, "matricule_utilisateur et application obligatoires")
            continue
        if mat not in users:
            rep.error(i, f"salarie inconnu: {mat}")
            continue
        if app_nom not in apps:
            rep.error(i, f"application inconnue: {app_nom}")
            continue
        session.add(UserApplication(
            user_id=users[mat].id, application_id=apps[app_nom].id,
            acces=as_bool(row.get("acces")), note=as_str(row.get("note")),
            attribue_par="import",
        ))
        rep.imported += 1


HANDLERS = {
    "entites": _import_entites,
    "applications": _import_applications,
    "utilisateurs": _import_utilisateurs,
    "materiel": _import_materiel,
    "affectations": _import_affectations,
    "acces_applicatifs": _import_acces,
}


@router.post("/{kind}")
async def import_csv(
    kind: str,
    file: UploadFile = File(...),
    dry_run: bool = False,
    session: Session = Depends(get_session),
):
    if kind not in HANDLERS:
        raise HTTPException(400, f"Type inconnu. Attendu: {', '.join(KINDS)}")
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux (maximum {MAX_IMPORT_BYTES // 1024 // 1024} Mo)")
    try:
        rows, _ = read_rows(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"CSV illisible: {exc}")

    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(413, f"Trop de lignes (maximum {MAX_IMPORT_ROWS})")

    rep = Report(kind, dry_run)
    HANDLERS[kind](rows, session, rep)

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return rep.dict()
