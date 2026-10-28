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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from ..audit import audit
from ..auth import (
    check_password_policy,
    client_ip,
    create_access_token,
    get_current_account,
    hash_password,
    login_limiter,
    require_roles,
    verify_password,
)
from ..db import get_session
from ..models import Account, Role

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash factice : verifie un mot de passe meme si le compte n'existe pas, pour que le
# temps de reponse ne revele pas quels identifiants existent.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class AccountCreate(BaseModel):
    username: str
    password: str
    role: Role = Role.informatique


class AccountUpdate(BaseModel):
    actif: bool | None = None
    role: Role | None = None
    password: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    actif: bool


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, session: Session = Depends(get_session)):
    ip = client_ip(request)
    wait = login_limiter.retry_after(ip, data.username)
    if wait:
        audit(data.username, "login_bloque", ip=ip, status=429)
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard",
                            headers={"Retry-After": str(wait)})

    account = session.exec(
        select(Account).where(Account.username == data.username)
    ).first()
    hashed = account.hashed_password if account else _DUMMY_HASH
    valid = verify_password(data.password, hashed)
    if not account or not account.actif or not valid:
        login_limiter.fail(ip, data.username)
        audit(data.username, "login_echec", ip=ip, status=401)
        raise HTTPException(401, "Identifiants invalides")

    login_limiter.success(ip, data.username)
    audit(account.username, "login_ok", ip=ip, status=200)
    token = create_access_token(account.username, account.role.value)
    return TokenResponse(access_token=token, username=account.username, role=account.role.value)


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)):
    return account


@router.post("/change-password", status_code=204)
def change_password(
    data: PasswordChange,
    request: Request,
    account: Account = Depends(get_current_account),
    session: Session = Depends(get_session),
):
    ip = client_ip(request)
    wait = login_limiter.retry_after(ip, account.username)
    if wait:
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard",
                            headers={"Retry-After": str(wait)})
    if not verify_password(data.old_password, account.hashed_password):
        login_limiter.fail(ip, account.username)
        raise HTTPException(400, "Ancien mot de passe incorrect")
    check_password_policy(data.new_password)
    account.hashed_password = hash_password(data.new_password)
    session.add(account)
    session.commit()
    audit(account.username, "mot_de_passe_change", ip=ip, status=204)


@router.get("/accounts", response_model=list[AccountOut],
            dependencies=[Depends(require_roles("informatique"))])
def list_accounts(session: Session = Depends(get_session)):
    return session.exec(select(Account)).all()


@router.post("/accounts", response_model=AccountOut, status_code=201,
             dependencies=[Depends(require_roles("informatique"))])
def create_account(data: AccountCreate, session: Session = Depends(get_session)):
    check_password_policy(data.password)
    if session.exec(select(Account).where(Account.username == data.username)).first():
        raise HTTPException(409, "Nom d'utilisateur deja pris")
    account = Account(
        username=data.username,
        role=data.role,
        actif=True,
        hashed_password=hash_password(data.password),
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    data: AccountUpdate,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    target = session.get(Account, account_id)
    if not target:
        raise HTTPException(404, "Compte introuvable")

    removes_admin = (
        target.role == Role.informatique and target.actif
        and ((data.actif is False) or (data.role is not None and data.role != Role.informatique))
    )
    if removes_admin:
        remaining = session.exec(
            select(Account).where(Account.role == Role.informatique,
                                  Account.actif == True,  # noqa: E712
                                  Account.id != target.id)
        ).first()
        if not remaining:
            raise HTTPException(409, "Impossible : ce serait le dernier compte informatique actif")

    if data.actif is not None:
        target.actif = data.actif
    if data.role is not None:
        target.role = data.role
    if data.password is not None:
        check_password_policy(data.password)
        target.hashed_password = hash_password(data.password)
    session.add(target)
    session.commit()
    session.refresh(target)
    audit(admin.username, "compte_modifie", target=target.username,
          detail=",".join(k for k, v in (("actif", data.actif), ("role", data.role),
                                         ("password", data.password)) if v is not None))
    return target
