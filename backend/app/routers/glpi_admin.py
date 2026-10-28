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

"""Connecteur GLPI : reglages, test, import (proposition puis application), export, historique. Informatique uniquement."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .. import appsettings, glpi
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..glpi import GlpiClient, GlpiError
from ..models import Account, Entite, IntegrationRun

router = APIRouter(prefix="/glpi", tags=["glpi"], dependencies=[Depends(require_roles("informatique"))])

MAX_SELECTION = 500


class GlpiConfigIn(BaseModel):
    actif: bool = False
    url: str = Field(default="", max_length=300)
    verifier_cert: bool = True
    types_computer: list[str] = Field(default_factory=list, max_length=10)
    types_phone: list[str] = Field(default_factory=list, max_length=10)
    entites: dict[str, int] = Field(default_factory=dict)
    entite_kikan: int | None = None
    entite_glpi: int = Field(default=0, ge=0)
    profil: str = Field(default="", max_length=60)


def _view(session: Session) -> dict:
    cfg = glpi.load_config(session)
    return {
        "config": {"actif": cfg.actif, "url": cfg.url, "verifier_cert": cfg.verifier_cert, "types_computer": cfg.types_computer,
                   "types_phone": cfg.types_phone, "entites": cfg.entites, "entite_kikan": cfg.entite_kikan, "entite_glpi": cfg.entite_glpi,
                   "profil": cfg.profil},
        "jeton_defini": bool(glpi.user_token()), "jeton_application_defini": bool(glpi.app_token()),
        "pret": cfg.pret and glpi.url_problem(cfg.url) is None,
        "probleme_url": glpi.url_problem(cfg.url) if cfg.url else None,
    }


@router.get("/config")
def get_config(session: Session = Depends(get_session)):
    return _view(session)


@router.put("/config")
def put_config(data: GlpiConfigIn, session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    url = data.url.strip()
    if url:
        problem = glpi.url_problem(url)
        if problem:
            raise HTTPException(400, problem)
    if data.actif and not url:
        raise HTTPException(400, "L'adresse du serveur GLPI est requise pour activer le connecteur")
    clean = lambda items: [" ".join(x.split()) for x in items if x.strip()]  # noqa: E731
    computers, phones = clean(data.types_computer), clean(data.types_phone)
    if {x.lower() for x in computers} & {x.lower() for x in phones}:
        raise HTTPException(400, "Un type ne peut pas etre a la fois ordinateur et telephone")
    if any("|" in x or len(x) > 100 for x in computers + phones):
        raise HTTPException(400, "Nom de type invalide")
    kikan_ids = {e.id for e in session.exec(select(Entite)).all()}
    if any(v not in kikan_ids for v in data.entites.values()) or (data.entite_kikan is not None and data.entite_kikan not in kikan_ids):
        raise HTTPException(400, "Entite Kikan inconnue")
    values = {"glpi_actif": "1" if data.actif else "0", "glpi_url": url, "glpi_verifier_cert": "1" if data.verifier_cert else "0",
              "glpi_types_computer": "|".join(computers), "glpi_types_phone": "|".join(phones),
              "glpi_entites": json.dumps({str(int(k)): v for k, v in data.entites.items()}),
              "glpi_entite_kikan": "" if data.entite_kikan is None else str(data.entite_kikan),
              "glpi_entite_glpi": str(data.entite_glpi), "glpi_profil": " ".join(data.profil.split())}
    for key, value in values.items():
        appsettings.put(session, key, value)
    session.commit()
    audit(admin.username, "glpi_reglages", detail="reglages enregistres")
    return _view(session)


def _ready(session: Session) -> glpi.GlpiConfig:
    cfg = glpi.load_config(session)
    if not cfg.actif:
        raise HTTPException(409, "Le connecteur GLPI n'est pas active (Parametrage, Integrations)")
    return cfg


def _client(cfg: glpi.GlpiConfig) -> GlpiClient:
    try:
        return GlpiClient(cfg)
    except GlpiError as exc:
        raise HTTPException(409, str(exc)) from exc


def _gateway(exc: GlpiError) -> HTTPException:
    return HTTPException(502, str(exc))


@router.post("/tester")
def test_connection(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    cfg = glpi.load_config(session)
    if not cfg.url:
        raise HTTPException(409, "Renseignez l'adresse du serveur GLPI")
    client = _client(cfg)
    try:
        with client:
            snap = glpi.read_glpi(client)
    except GlpiError as exc:
        audit(admin.username, "glpi_test", status=502, detail="echec")
        raise _gateway(exc) from exc
    audit(admin.username, "glpi_test", status=200)
    return {"ok": True, "ordinateurs": sum(1 for i in snap.items.values() if i["itemtype"] == "Computer"),
            "telephones": sum(1 for i in snap.items.values() if i["itemtype"] == "Phone"), "utilisateurs": len(snap.users),
            "entites": [{"id": k, "nom": v} for k, v in sorted(snap.entites.items())],
            "profil_trouve": (not cfg.profil) or cfg.profil in snap.profils}


def _read(session: Session):
    cfg = _ready(session)
    client = _client(cfg)
    try:
        with client:
            return cfg, client, glpi.read_glpi(client)
    except GlpiError as exc:
        raise _gateway(exc) from exc


def _run(session: Session, sens: str, admin: Account, outcome: dict, error: str | None = None) -> None:
    session.add(IntegrationRun(systeme=glpi.SYSTEME, sens=sens, lance_par=admin.username, fin=datetime.utcnow(),
                               resume=json.dumps(outcome.get("resume", {})), erreurs=error))
    session.commit()


@router.post("/import/apercu")
def import_preview(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    cfg, _, snap = _read(session)
    proposals = glpi.import_proposals(session, cfg, snap)
    audit(admin.username, "glpi_import_apercu", detail=f"{len(proposals['actifs'])} actif(s), {len(proposals['salaries'])} salarie(s) lus")
    return {**proposals, "types": {"Computer": glpi.type_for(cfg, "Computer"), "Phone": glpi.type_for(cfg, "Phone")}}


class Selection(BaseModel):
    externe_id: str = Field(max_length=60)
    entite_id: int | None = None
    homonyme: str | None = Field(default=None, pattern="^(lier|creer)$")


class ImportIn(BaseModel):
    actifs: list[Selection] = Field(default_factory=list, max_length=MAX_SELECTION)
    salaries: list[Selection] = Field(default_factory=list, max_length=MAX_SELECTION)


@router.post("/import/appliquer")
def import_apply(data: ImportIn, session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    if not data.actifs and not data.salaries:
        raise HTTPException(400, "Rien n'est selectionne")
    cfg, _, snap = _read(session)   # les donnees sont relues dans GLPI : le client ne fournit que le choix des elements
    outcome = glpi.import_apply(session, cfg, snap, [s.model_dump() for s in data.actifs], [s.model_dump() for s in data.salaries])
    _run(session, "import", admin, outcome)
    audit(admin.username, "glpi_import", detail=", ".join(f"{k}={v}" for k, v in sorted(outcome["resume"].items())))
    return outcome


@router.post("/export/apercu")
def export_preview(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    cfg, _, snap = _read(session)
    users = glpi.export_proposals(session, cfg, snap)
    audit(admin.username, "glpi_export_apercu", detail=f"{len(users)} salarie(s) examines")
    return {"salaries": users, "profil_trouve": (not cfg.profil) or cfg.profil in snap.profils, "profil": cfg.profil}


class ExportIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=MAX_SELECTION)


@router.post("/export/appliquer")
def export_apply(data: ExportIn, session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    cfg = _ready(session)
    client = _client(cfg)
    try:
        with client:
            snap = glpi.read_glpi(client)
            outcome = glpi.export_apply(session, cfg, client, snap, list(dict.fromkeys(data.user_ids)))
    except GlpiError as exc:
        raise _gateway(exc) from exc
    _run(session, "export", admin, outcome)
    audit(admin.username, "glpi_export", detail=", ".join(f"{k}={v}" for k, v in sorted(outcome["resume"].items())))
    return outcome


@router.get("/historique")
def history(session: Session = Depends(get_session)):
    rows = session.exec(select(IntegrationRun).where(IntegrationRun.systeme == glpi.SYSTEME).order_by(IntegrationRun.id.desc()).limit(50)).all()
    return [{"id": r.id, "sens": r.sens, "lance_par": r.lance_par, "debut": r.debut, "fin": r.fin,
             "resume": json.loads(r.resume or "{}"), "erreurs": r.erreurs} for r in rows]
