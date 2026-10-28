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

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func
from sqlmodel import Session, select

from ..audit import audit
from ..auth import (
    check_password_policy,
    client_ip,
    create_access_token,
    generate_temp_password,
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
    must_change_password: bool = False


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,63}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 200 or not EMAIL_RE.match(value):
        raise ValueError("Adresse e-mail invalide")
    return value


def _clean_name(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    return value[:120] or None


class AccountCreate(BaseModel):
    username: str
    role: Role = Role.informatique
    nom_affiche: str | None = None
    email: str | None = None
    # Facultatif : sans mot de passe, un mot de passe provisoire est genere (affiche une seule fois).
    password: str | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("Identifiant invalide : 3 a 64 caracteres, minuscules, chiffres et . _ - @")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _clean_email(v)

    @field_validator("nom_affiche")
    @classmethod
    def _nom(cls, v):
        return _clean_name(v)


class AccountUpdate(BaseModel):
    actif: bool | None = None
    role: Role | None = None
    password: str | None = None
    nom_affiche: str | None = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _clean_email(v) if v is not None else None

    @field_validator("nom_affiche")
    @classmethod
    def _nom(cls, v):
        return _clean_name(v) if v is not None else None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    actif: bool
    nom_affiche: str | None = None
    email: str | None = None
    must_change_password: bool = False
    derniere_connexion: datetime | None = None


class AccountCreated(AccountOut):
    mot_de_passe_provisoire: str | None = None  # renvoye UNE fois, jamais journalise


class ResetResult(BaseModel):
    mot_de_passe_provisoire: str


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, session: Session = Depends(get_session)):
    ip = client_ip(request)
    wait = login_limiter.retry_after(ip, data.username)
    if wait:
        audit(data.username, "login_bloque", ip=ip, status=429)
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard",
                            headers={"Retry-After": str(wait)})

    account = session.exec(
        select(Account).where(func.lower(Account.username) == data.username.strip().lower())
    ).first()
    hashed = account.hashed_password if account else _DUMMY_HASH
    valid = verify_password(data.password, hashed)
    if not account or not account.actif or not valid:
        login_limiter.fail(ip, data.username)
        audit(data.username, "login_echec", ip=ip, status=401)
        raise HTTPException(401, "Identifiants invalides")

    login_limiter.success(ip, data.username)
    account.derniere_connexion = datetime.utcnow()
    session.add(account)
    session.commit()
    audit(account.username, "login_ok", ip=ip, status=200)
    token = create_access_token(account.username, account.role.value, account.token_epoch)
    return TokenResponse(access_token=token, username=account.username, role=account.role.value,
                         must_change_password=account.must_change_password)


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)):
    return account


@router.post("/change-password", response_model=TokenResponse)
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
    if verify_password(data.new_password, account.hashed_password):
        raise HTTPException(400, "Le nouveau mot de passe doit etre different de l'ancien")
    account.hashed_password = hash_password(data.new_password)
    account.must_change_password = False
    account.token_epoch += 1  # les autres sessions de ce compte sont revoquees
    session.add(account)
    session.commit()
    audit(account.username, "mot_de_passe_change", ip=ip, status=200)
    token = create_access_token(account.username, account.role.value, account.token_epoch)
    return TokenResponse(access_token=token, username=account.username, role=account.role.value)


def _other_admin_exists(session: Session, exclude_id: int) -> bool:
    return session.exec(
        select(Account).where(Account.role == Role.informatique,
                              Account.actif == True,  # noqa: E712
                              Account.id != exclude_id)
    ).first() is not None


@router.get("/accounts", response_model=list[AccountOut],
            dependencies=[Depends(require_roles("informatique"))])
def list_accounts(session: Session = Depends(get_session)):
    rows = session.exec(select(Account)).all()
    return sorted(rows, key=lambda a: a.username)


@router.post("/accounts", response_model=AccountCreated, status_code=201)
def create_account(data: AccountCreate, session: Session = Depends(get_session),
                   admin: Account = Depends(require_roles("informatique"))):
    provisional = None
    password = data.password
    if password is None:
        provisional = password = generate_temp_password()
    check_password_policy(password)
    if session.exec(select(Account).where(func.lower(Account.username) == data.username)).first():
        raise HTTPException(409, "Nom d'utilisateur deja pris")
    account = Account(
        username=data.username,
        role=data.role,
        actif=True,
        hashed_password=hash_password(password),
        nom_affiche=data.nom_affiche,
        email=data.email,
        must_change_password=provisional is not None,  # mot de passe choisi par l'appelant : pas de changement force
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    audit(admin.username, "compte_cree", target=account.username, detail=f"role : {account.role.value}")
    return AccountCreated(**AccountOut.model_validate(account).model_dump(), mot_de_passe_provisoire=provisional)


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

    if target.id == admin.id and data.actif is False:
        raise HTTPException(409, "Vous ne pouvez pas desactiver votre propre compte")
    removes_admin = (
        target.role == Role.informatique and target.actif
        and ((data.actif is False) or (data.role is not None and data.role != Role.informatique))
    )
    if removes_admin and not _other_admin_exists(session, target.id):
        raise HTTPException(409, "Impossible : ce serait le dernier compte informatique actif")

    changed = []
    revoke = False
    if data.actif is not None and data.actif != target.actif:
        target.actif = data.actif
        changed.append("actif")
        revoke = revoke or not data.actif
    if data.role is not None and data.role != target.role:
        target.role = data.role
        changed.append("role")
        revoke = True
    # Champ absent = inchange ; champ vide = efface (distinction par les champs effectivement envoyes).
    if "nom_affiche" in data.model_fields_set and data.nom_affiche != target.nom_affiche:
        target.nom_affiche = data.nom_affiche
        changed.append("nom")
    if "email" in data.model_fields_set and data.email != target.email:
        target.email = data.email
        changed.append("email")
    if data.password is not None:
        check_password_policy(data.password)
        target.hashed_password = hash_password(data.password)
        changed.append("password")
        revoke = True
    if revoke:
        target.token_epoch += 1  # les sessions ouvertes de ce compte sont revoquees
    session.add(target)
    session.commit()
    session.refresh(target)
    audit(admin.username, "compte_modifie", target=target.username,
          detail=",".join(changed) if changed else "aucun changement")
    return target


@router.post("/accounts/{account_id}/reset-password", response_model=ResetResult)
def reset_password(account_id: int, session: Session = Depends(get_session),
                   admin: Account = Depends(require_roles("informatique"))):
    """Nouveau mot de passe provisoire (affiche une seule fois), changement impose a la prochaine connexion."""
    target = session.get(Account, account_id)
    if not target:
        raise HTTPException(404, "Compte introuvable")
    provisional = generate_temp_password()
    target.hashed_password = hash_password(provisional)
    target.must_change_password = True
    target.token_epoch += 1
    session.add(target)
    session.commit()
    audit(admin.username, "mot_de_passe_reinitialise", target=target.username)
    return ResetResult(mot_de_passe_provisoire=provisional)
