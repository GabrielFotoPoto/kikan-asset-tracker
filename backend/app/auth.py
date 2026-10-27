"""Authentification (JWT) et controle des roles."""
import datetime
import os

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from .db import engine, get_session
from .models import Account, Role

SECRET = os.environ.get("KIKAN_SECRET_KEY", "dev-secret-change-me")
ALGO = "HS256"
TOKEN_TTL_MIN = int(os.environ.get("KIKAN_TOKEN_TTL_MIN", "480"))
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

_bearer = HTTPBearer(auto_error=True)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:  # noqa: BLE001
        return False


def create_access_token(username: str, role: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=TOKEN_TTL_MIN),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def get_current_account(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Account:
    try:
        payload = jwt.decode(cred.credentials, SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Token invalide ou expire")
    account = session.exec(
        select(Account).where(Account.username == payload.get("sub"))
    ).first()
    if not account or not account.actif:
        raise HTTPException(401, "Compte inconnu ou desactive")
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
    """Cree un compte informatique par defaut si aucun compte n'existe."""
    with Session(engine) as session:
        if session.exec(select(Account)).first():
            return
        username = os.environ.get("KIKAN_ADMIN_USER", "admin")
        password = os.environ.get("KIKAN_ADMIN_PASSWORD", "admin")
        session.add(Account(
            username=username,
            role=Role.informatique,
            actif=True,
            hashed_password=hash_password(password),
        ))
        session.commit()
