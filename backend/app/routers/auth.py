from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import (
    create_access_token,
    get_current_account,
    hash_password,
    require_roles,
    verify_password,
)
from ..db import get_session
from ..models import Account, Role

router = APIRouter(prefix="/auth", tags=["auth"])


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


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    actif: bool


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, session: Session = Depends(get_session)):
    account = session.exec(
        select(Account).where(Account.username == data.username)
    ).first()
    if not account or not account.actif or not verify_password(data.password, account.hashed_password):
        raise HTTPException(401, "Identifiants invalides")
    token = create_access_token(account.username, account.role.value)
    return TokenResponse(access_token=token, username=account.username, role=account.role.value)


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)):
    return account


@router.get("/accounts", response_model=list[AccountOut],
            dependencies=[Depends(require_roles("informatique"))])
def list_accounts(session: Session = Depends(get_session)):
    return session.exec(select(Account)).all()


@router.post("/accounts", response_model=AccountOut, status_code=201,
             dependencies=[Depends(require_roles("informatique"))])
def create_account(data: AccountCreate, session: Session = Depends(get_session)):
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
