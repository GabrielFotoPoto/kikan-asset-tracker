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

"""API d'integration /v1 : un outil externe pousse du materiel et des salaries vers Kikan avec un jeton.

Authentification par jeton d'API uniquement (pas de session). Idempotent (cle : id_externe), jamais de suppression, lots de
100 elements au plus, simulation avec ?dry_run=1. Voir docs/API.md.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from .. import integration
from ..apitoken import MAX_BATCH, ApiAuth, api_auth
from ..audit import audit
from ..db import get_session
from ..models import Asset, Entite, ExternalLink, User

router = APIRouter(prefix="/v1", tags=["api-v1"])


class AssetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_externe: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    marque: str | None = Field(default=None, max_length=100)
    modele: str | None = Field(default=None, max_length=100)
    numero_serie: str | None = Field(default=None, max_length=100)
    identifiant_interne: str | None = Field(default=None, max_length=100)
    date_achat: date | None = None
    fin_garantie: date | None = None
    echeance_renouvellement: date | None = None
    entite_code: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_externe: str = Field(min_length=1, max_length=100)
    matricule: str | None = Field(default=None, max_length=50)
    nom: str | None = Field(default=None, max_length=200)
    prenom: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=100)
    date_arrivee: date | None = None
    entite_code: str | None = Field(default=None, max_length=100)
    homonyme: str | None = Field(default=None, pattern="^(lier|creer)$")  # decision si un salarie porte deja ce nom


class AssetPut(AssetIn):
    id_externe: str | None = Field(default=None, max_length=100)   # l'identifiant est dans l'adresse


class UserPut(UserIn):
    id_externe: str | None = Field(default=None, max_length=100)


class AssetBatch(BaseModel):
    items: list[AssetIn] = Field(min_length=1, max_length=MAX_BATCH)


class UserBatch(BaseModel):
    items: list[UserIn] = Field(min_length=1, max_length=MAX_BATCH)


def _run(session: Session, auth: ApiAuth, kind: str, items: list[dict], dry_run: bool) -> dict:
    fn = integration.upsert_asset if kind == "asset" else integration.upsert_user
    results = []
    for item in items:
        try:
            with session.begin_nested():
                results.append(fn(session, auth.systeme, auth.scope, item))
        except Exception:  # noqa: BLE001  (un element en erreur n'arrete pas le lot)
            results.append({"id_externe": item.get("id_externe"), "resultat": "refuse", "message": "Donnees non traitables"})
    if dry_run:
        session.rollback()
        for r in results:
            r["id"] = None
    else:
        session.commit()
    summary: dict[str, int] = {}
    for r in results:
        summary[r["resultat"]] = summary.get(r["resultat"], 0) + 1
    audit(auth.actor, f"api_{kind}s_{'simulation' if dry_run else 'import'}", detail=", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    return {"simulation": dry_run, "resume": summary, "resultats": results}


@router.get("/me")
def me(auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    codes = sorted(e.code for e in session.exec(select(Entite)).all() if auth.scope.allows(e.id))
    return {"nom": auth.token.nom, "source": auth.token.source, "droits": auth.token.droits.split(","),
            "expire_le": auth.token.expire_le, "perimetre": "global" if auth.scope.globale else codes}


@router.get("/assets")
def list_assets(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("assets_lecture")
    stmt = auth.scope.where(select(Asset), Asset.entite_id).order_by(Asset.id).offset(offset).limit(limit)
    assets = session.exec(stmt).all()
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    links = {l.kikan_id: l.externe_id for l in session.exec(select(ExternalLink).where(
        ExternalLink.systeme == auth.systeme, ExternalLink.objet == "asset")).all()}
    return [{"id": a.id, "id_externe": links.get(a.id), "type": a.type, "marque": a.marque, "modele": a.modele,
             "numero_serie": a.numero_serie, "identifiant_interne": a.identifiant_interne, "statut": a.statut.value,
             "entite_code": ents.get(a.entite_id)} for a in assets]


@router.get("/users")
def list_users(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("users_lecture")
    stmt = auth.scope.users(select(User)).order_by(User.id).offset(offset).limit(limit)
    users = session.exec(stmt).all()
    ents = {e.id: e.code for e in session.exec(select(Entite)).all()}
    links = {l.kikan_id: l.externe_id for l in session.exec(select(ExternalLink).where(
        ExternalLink.systeme == auth.systeme, ExternalLink.objet == "user")).all()}
    return [{"id": u.id, "id_externe": links.get(u.id), "matricule": u.matricule, "nom": u.nom, "prenom": u.prenom,
             "email": u.email, "service": u.service, "statut": u.statut.value, "entite_code": ents.get(u.entite_id)} for u in users]


@router.post("/assets/_batch")
def put_assets(data: AssetBatch, dry_run: bool = False, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("assets_ecriture")
    return _run(session, auth, "asset", [i.model_dump() for i in data.items], dry_run)


@router.put("/assets/{id_externe}")
def put_asset(id_externe: str, data: AssetPut, dry_run: bool = False, auth: ApiAuth = Depends(api_auth),
              session: Session = Depends(get_session)):
    auth.need("assets_ecriture")
    item = data.model_dump()
    item["id_externe"] = id_externe
    return _run(session, auth, "asset", [item], dry_run)["resultats"][0]


@router.post("/users/_batch")
def put_users(data: UserBatch, dry_run: bool = False, auth: ApiAuth = Depends(api_auth), session: Session = Depends(get_session)):
    auth.need("users_ecriture")
    return _run(session, auth, "user", [i.model_dump() for i in data.items], dry_run)


@router.put("/users/{id_externe}")
def put_user(id_externe: str, data: UserPut, dry_run: bool = False, auth: ApiAuth = Depends(api_auth),
             session: Session = Depends(get_session)):
    auth.need("users_ecriture")
    item = data.model_dump()
    item["id_externe"] = id_externe
    return _run(session, auth, "user", [item], dry_run)["resultats"][0]
