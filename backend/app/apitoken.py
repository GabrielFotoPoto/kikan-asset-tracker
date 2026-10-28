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

"""Jetons de l'API d'integration : generation, empreinte, authentification, limitation de debit.

Un jeton ("kik_..." ) n'est jamais stocke en clair (empreinte SHA-256, comme un secret a forte entropie) ; il n'ouvre que
l'API /v1, avec des droits et un perimetre limites et une date d'expiration. Il n'est pas un jeton de session : aucun autre
endpoint ne l'accepte.
"""
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from .db import get_session
from .models import ApiToken, ApiTokenScope
from .scope import GLOBAL, Scope, expand_scope

PREFIX = "kik_"
DROITS = ("assets_lecture", "assets_ecriture", "users_lecture", "users_ecriture")
RATE_PER_MIN = 300
MAX_BATCH = 100

_hits: dict[int, deque] = defaultdict(deque)
_lock = threading.Lock()


def new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class ApiAuth:
    token: ApiToken
    scope: Scope

    def need(self, droit: str) -> None:
        if droit not in self.token.droits.split(","):
            raise HTTPException(403, "Droit insuffisant pour ce jeton")

    @property
    def systeme(self) -> str:
        return self.token.source

    @property
    def actor(self) -> str:
        return f"api:{self.token.nom}"


def token_scope(session: Session, token: ApiToken) -> Scope:
    if token.portee_globale:
        return GLOBAL
    return expand_scope(session, {r.entite_id for r in session.exec(select(ApiTokenScope).where(ApiTokenScope.token_id == token.id)).all()})


def _throttle(token_id: int) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[token_id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_PER_MIN:
            raise HTTPException(429, "Trop de requetes : reessayez dans une minute")
        q.append(now)


def api_auth(request: Request, session: Session = Depends(get_session)) -> ApiAuth:
    header = request.headers.get("authorization", "")
    raw = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not raw.startswith(PREFIX):
        raise HTTPException(401, "Jeton d'API requis")
    token = session.exec(select(ApiToken).where(ApiToken.token_hash == digest(raw))).first()
    if token is None or not token.actif or token.expire_le < date.today():
        raise HTTPException(401, "Jeton d'API invalide, revoque ou expire")
    _throttle(token.id)
    token.derniere_utilisation = datetime.utcnow()
    token.utilisations += 1
    session.add(token)
    session.commit()
    return ApiAuth(token, token_scope(session, token))
