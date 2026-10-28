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

"""Administration des integrations : jetons d'API (informatique uniquement)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from ..apitoken import DROITS, digest, new_token
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..models import Account, ApiToken, ApiTokenScope, Entite

router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_roles("informatique"))])


class TokenIn(BaseModel):
    nom: str = Field(min_length=3, max_length=60)
    source: str = Field(default="api", pattern="^[a-z][a-z0-9_-]{1,29}$")
    droits: list[str] = Field(min_length=1)
    portee_globale: bool = False
    entites: list[int] = Field(default_factory=list, max_length=200)
    jours: int = Field(default=90, ge=1, le=730)

    @field_validator("nom")
    @classmethod
    def _nom(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("nom trop court")
        return v


def _view(session: Session, t: ApiToken) -> dict:
    ids = sorted(r.entite_id for r in session.exec(select(ApiTokenScope).where(ApiTokenScope.token_id == t.id)).all())
    return {"id": t.id, "nom": t.nom, "prefixe": t.prefixe, "source": t.source, "droits": t.droits.split(","),
            "portee_globale": t.portee_globale, "entites": ids, "expire_le": t.expire_le, "actif": t.actif,
            "expire": t.expire_le < date.today(), "cree_par": t.cree_par, "cree_le": t.cree_le,
            "derniere_utilisation": t.derniere_utilisation, "utilisations": t.utilisations}


@router.get("/tokens")
def list_tokens(session: Session = Depends(get_session)):
    return [_view(session, t) for t in session.exec(select(ApiToken).order_by(ApiToken.id.desc())).all()]


@router.post("/tokens", status_code=201)
def create_token(data: TokenIn, session: Session = Depends(get_session),
                 admin: Account = Depends(require_roles("informatique"))):
    bad = [d for d in data.droits if d not in DROITS]
    if bad:
        raise HTTPException(422, "Droit inconnu : " + ", ".join(bad))
    if data.portee_globale and data.entites:
        raise HTTPException(400, "Un jeton global n'a pas de liste d'entites")
    if not data.portee_globale:
        if not data.entites:
            raise HTTPException(400, "Choisissez au moins une entite, ou un perimetre global")
        found = {e.id for e in session.exec(select(Entite).where(Entite.id.in_(data.entites))).all()}
        if found != set(data.entites):
            raise HTTPException(400, "Entite inconnue")
    raw = new_token()
    token = ApiToken(nom=data.nom, token_hash=digest(raw), prefixe=raw[:8], source=data.source,
                     droits=",".join(sorted(set(data.droits))), portee_globale=data.portee_globale,
                     expire_le=date.today() + timedelta(days=data.jours), cree_par=admin.username)
    session.add(token)
    session.flush()
    for eid in sorted(set(data.entites)):
        session.add(ApiTokenScope(token_id=token.id, entite_id=eid))
    session.commit()
    session.refresh(token)
    audit(admin.username, "jeton_api_cree", target=str(token.id), detail=f"{token.nom} ({token.droits})")
    return {**_view(session, token), "jeton": raw}   # le jeton n'est montre qu'ici, une seule fois


@router.post("/tokens/{token_id}/revoquer")
def revoke_token(token_id: int, session: Session = Depends(get_session),
                 admin: Account = Depends(require_roles("informatique"))):
    token = session.get(ApiToken, token_id)
    if not token:
        raise HTTPException(404, "Jeton introuvable")
    token.actif = False
    session.add(token)
    session.commit()
    audit(admin.username, "jeton_api_revoque", target=str(token.id), detail=token.nom)
    return _view(session, token)
