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

"""Authentification (JWT), politique de mots de passe, limitation des tentatives."""
import datetime
import logging
import os
import secrets
import threading
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlmodel import Session, select

from .db import engine, get_session
from .models import Account, Role, Setting

log = logging.getLogger("kikan.security")

ENV = os.environ.get("KIKAN_ENV", "development").lower()
IS_PROD = ENV == "production"

ALGO = "HS256"
TOKEN_TTL_MIN = int(os.environ.get("KIKAN_TOKEN_TTL_MIN", "240"))
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
MIN_PASSWORD_LEN = 12
MAX_PASSWORD_BYTES = 72  # limite de bcrypt

_WEAK_SECRETS = {"", "dev-secret-change-me", "change-me", "secret"}


def _load_secret() -> str:
    value = os.environ.get("KIKAN_SECRET_KEY", "")
    if value in _WEAK_SECRETS or len(value) < 32:
        if IS_PROD:
            raise RuntimeError(
                "KIKAN_SECRET_KEY doit etre defini avec au moins 32 caracteres "
                "(ex. : python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
            )
        log.warning(
            "KIKAN_SECRET_KEY absent ou faible : une cle aleatoire est generee "
            "(les sessions seront perdues au redemarrage). Definissez-la dans .env."
        )
        return secrets.token_urlsafe(48)
    return value


SECRET = _load_secret()


# --- Mots de passe ---

def check_password_policy(password: str) -> None:
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise HTTPException(400, f"Mot de passe trop long ({MAX_PASSWORD_BYTES} octets maximum)")
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Mot de passe trop court ({MIN_PASSWORD_LEN} caracteres minimum)")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:  # noqa: BLE001
        return False


# --- Limitation des tentatives de connexion ---

class LoginLimiter:
    """Verrouille temporairement apres trop d'echecs (en memoire, mono-processus).

    Cle compte+IP : un attaquant distant ne peut pas verrouiller l'administrateur
    depuis une autre adresse. Une limite globale par IP freine aussi l'enumeration.
    """

    def __init__(self, max_per_account: int = 5, max_per_ip: int = 30, window: int = 900):
        self.max_per_account = max_per_account
        self.max_per_ip = max_per_ip
        self.window = window
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._fails.get(key, []) if now - t < self.window]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def retry_after(self, ip: str, username: str) -> int:
        """Secondes a attendre (0 = autorise)."""
        now = time.time()
        with self._lock:
            waits = []
            for key, limit in ((f"a|{ip}|{username.lower()}", self.max_per_account),
                               (f"i|{ip}", self.max_per_ip)):
                recent = self._recent(key, now)
                if len(recent) >= limit:
                    waits.append(int(self.window - (now - recent[0])) + 1)
            return max(waits) if waits else 0

    def fail(self, ip: str, username: str) -> None:
        now = time.time()
        with self._lock:
            for key in (f"a|{ip}|{username.lower()}", f"i|{ip}"):
                self._fails.setdefault(key, []).append(now)

    def success(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop(f"a|{ip}|{username.lower()}", None)


login_limiter = LoginLimiter(
    max_per_account=int(os.environ.get("KIKAN_LOGIN_MAX_FAILS", "5")),
    window=int(os.environ.get("KIKAN_LOGIN_WINDOW_SEC", "900")),
)


def client_ip(request: Request) -> str:
    # L'API n'est joignable que derriere Nginx (qui pose X-Real-IP) ou en local.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


# --- Jetons ---

def _ttl_minutes() -> int:
    """Duree de session reglable dans le parametrage (30 min a 12 h) ; sinon la valeur de l'environnement."""
    try:
        with Session(engine) as session:
            row = session.get(Setting, "session_ttl_min")
        if row and row.value:
            return max(30, min(720, int(row.value)))
    except Exception:  # noqa: BLE001  (base indisponible ou valeur invalide : on retombe sur la valeur par defaut)
        pass
    return TOKEN_TTL_MIN


def create_access_token(username: str, role: str, epoch: int = 0) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "te": epoch,  # version de session du compte : change a chaque revocation
        "iat": now,
        "exp": now + datetime.timedelta(minutes=_ttl_minutes()),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def actor_from_request(request: Request) -> str:
    """Identifiant de l'appelant (sans acces base) pour le journal d'audit."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer kik_"):
        return "api"  # jeton d'integration : le nom du jeton est ajoute au journal par l'API elle-meme
    if header.lower().startswith("bearer "):
        try:
            return str(jwt.decode(header[7:], SECRET, algorithms=[ALGO]).get("sub", "?"))
        except jwt.PyJWTError:
            return "jeton-invalide"
    return "anonyme"


_bearer = HTTPBearer(auto_error=False)


# Tant que le mot de passe est provisoire, seules ces routes sont accessibles.
ALLOWED_WHEN_PASSWORD_MUST_CHANGE = {"/auth/me", "/auth/change-password"}
_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # sans caracteres ambigus


def generate_temp_password() -> str:
    """Mot de passe provisoire (16 caracteres, ~90 bits) : XXXX-XXXX-XXXX-XXXX."""
    chars = [secrets.choice(_PASSWORD_ALPHABET) for _ in range(16)]
    return "-".join("".join(chars[i:i + 4]) for i in range(0, 16, 4))


def get_current_account(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Account:
    if cred is None:
        raise HTTPException(401, "Authentification requise", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(cred.credentials, SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Token invalide ou expire", headers={"WWW-Authenticate": "Bearer"})
    account = session.exec(
        select(Account).where(func.lower(Account.username) == str(payload.get("sub", "")).lower())
    ).first()
    if not account or not account.actif:
        raise HTTPException(401, "Compte inconnu ou desactive", headers={"WWW-Authenticate": "Bearer"})
    if int(payload.get("te", 0)) != account.token_epoch:
        raise HTTPException(401, "Session revoquee, reconnectez-vous", headers={"WWW-Authenticate": "Bearer"})
    if account.must_change_password and request.url.path not in ALLOWED_WHEN_PASSWORD_MUST_CHANGE:
        raise HTTPException(403, "Changement de mot de passe requis")
    return account


def writer_guard(*write_roles: str):
    """Authentifie toute requete ; limite les ecritures aux roles indiques."""
    allowed = set(write_roles)

    def dep(request: Request, account: Account = Depends(get_current_account)) -> Account:
        if request.method in MUTATING and account.role not in allowed:
            raise HTTPException(403, "Droits insuffisants pour cette action")
        return account

    return dep


def require_roles(*roles: str):
    allowed = set(roles)

    def dep(account: Account = Depends(get_current_account)) -> Account:
        if account.role not in allowed:
            raise HTTPException(403, "Droits insuffisants")
        return account

    return dep


def ensure_bootstrap_account() -> None:
    """Cree le premier compte informatique si aucun compte n'existe.

    Sans KIKAN_ADMIN_PASSWORD, un mot de passe aleatoire est genere et affiche
    UNE SEULE FOIS dans les journaux du conteneur (docker compose logs api).
    """
    with Session(engine) as session:
        if session.exec(select(Account)).first():
            return
        username = os.environ.get("KIKAN_ADMIN_USER", "admin")
        password = os.environ.get("KIKAN_ADMIN_PASSWORD", "")
        generated = False
        if not password:
            password = secrets.token_urlsafe(16)
            generated = True
        elif len(password) < MIN_PASSWORD_LEN:
            log.warning("KIKAN_ADMIN_PASSWORD est trop court (%d caracteres minimum) : "
                        "changez-le des la premiere connexion.", MIN_PASSWORD_LEN)
        session.add(Account(
            username=username,
            role=Role.informatique,
            actif=True,
            hashed_password=hash_password(password),
            must_change_password=generated,  # mot de passe affiche dans les journaux : inutilisable apres la 1re connexion
        ))
        session.commit()
        if generated:
            log.warning("COMPTE INITIAL CREE - identifiant : %s - mot de passe : %s "
                        "(affiche une seule fois, changez-le)", username, password)
