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

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    LoginLimiter,
    login_limiter,
    require_roles,
    verify_password,
)
from ..db import engine, get_session
from ..models import Account, AccountScope, Entite, PasswordResetToken, Role
from ..scope import compute_scope
from .. import mailer, sso_policy

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
    # Portee des comptes RH et lecture (l'informatique voit toujours tout). Absente : aucune portee, a definir.
    portee_globale: bool | None = None
    entites: list[int] = Field(default_factory=list, max_length=200)

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
    secours: bool | None = None
    portee_globale: bool | None = None
    entites: list[int] | None = Field(default=None, max_length=200)

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
    source_auth: str = "local"
    sso_upn: str | None = None
    sso_lie: bool = False
    secours: bool = False
    portee_globale: bool = True
    entites: list[int] = []          # entites choisies (les sous-entites sont incluses automatiquement)
    portee: dict | None = None       # portee effective du compte connecte (/auth/me)

    @classmethod
    def from_account(cls, a: "Account") -> "AccountOut":
        out = cls.model_validate(a)
        out.sso_lie = bool(a.sso_oid)
        return out


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

    if not sso_policy.local_login_allowed(session, account):
        login_limiter.success(ip, data.username)
        audit(account.username, "login_local_refuse", ip=ip, status=403, detail="reserve a Microsoft 365 ou aux comptes de secours")
        raise HTTPException(403, "Connexion par mot de passe reservee aux comptes de secours : utilisez Microsoft 365")
    login_limiter.success(ip, data.username)
    account.derniere_connexion = datetime.utcnow()
    session.add(account)
    session.commit()
    audit(account.username, "login_ok", ip=ip, status=200)
    token = create_access_token(account.username, account.role.value, account.token_epoch)
    return TokenResponse(access_token=token, username=account.username, role=account.role.value,
                         must_change_password=account.must_change_password)


# --- Mot de passe oublie (libre-service) ---
# Lien a usage unique envoye a l'adresse du compte ; reponse identique que le compte existe ou non (pas d'enumeration) ;
# envoi en tache de fond (le temps de reponse ne trahit rien) ; tentatives limitees par adresse IP et par identifiant.

RESET_TTL_MIN = 30
reset_limiter = LoginLimiter(max_per_account=3, max_per_ip=15, window=900)
_RESET_REPONSE = {"detail": "Si un compte correspond et que l'envoi d'e-mails est configure, un lien de reinitialisation "
                            "vient d'etre envoye a son adresse (valable 30 minutes)."}


def _empreinte(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ForgotRequest(BaseModel):
    identifiant: str = Field(min_length=1, max_length=200)


class ResetRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str


def _reset_disponible(session: Session) -> bool:
    cfg = mailer.load_config(session)
    return cfg.actif and cfg.pret and bool(mailer.public_url())


@router.get("/reset/config")
def reset_config(session: Session = Depends(get_session)):
    """Le lien « Mot de passe oublie ? » n'est propose que si l'envoi d'e-mails et l'adresse publique sont configures."""
    return {"disponible": _reset_disponible(session)}


def _send_reset_mail(to: str, link: str) -> None:
    try:
        with Session(engine) as session:
            cfg = mailer.load_config(session)
        mailer.send(cfg, [to], "[Kikan] Reinitialisation de votre mot de passe",
                    "Bonjour,\n\nUne reinitialisation du mot de passe de votre compte Kikan a ete demandee.\n\n"
                    f"Pour choisir un nouveau mot de passe (lien valable {RESET_TTL_MIN} minutes, usage unique) :\n{link}\n\n"
                    "Si vous n'etes pas a l'origine de cette demande, ignorez ce message : votre mot de passe reste inchange.\n")
    except Exception as exc:  # noqa: BLE001  (jamais d'echec visible : la reponse est deja partie)
        audit("systeme", "reset_mail_echec", detail=type(exc).__name__)


@router.post("/forgot", status_code=202)
def forgot_password(data: ForgotRequest, request: Request, background: BackgroundTasks,
                    session: Session = Depends(get_session)):
    ip = client_ip(request)
    ident = data.identifiant.strip().lower()
    wait = reset_limiter.retry_after(ip, ident)
    if wait:
        raise HTTPException(429, "Trop de demandes, reessayez plus tard", headers={"Retry-After": str(wait)})
    reset_limiter.fail(ip, ident)  # chaque demande compte, qu'elle aboutisse ou non
    now = datetime.utcnow()
    for old in session.exec(select(PasswordResetToken).where(PasswordResetToken.expire_le < now)).all():
        session.delete(old)  # menage des liens expires
    account = session.exec(select(Account).where(func.lower(Account.username) == ident)).first()
    if not account:  # a defaut, l'adresse e-mail, a condition qu'elle soit unique
        found = session.exec(select(Account).where(func.lower(Account.email) == ident)).all()
        account = found[0] if len(found) == 1 else None
    address = (account.email or "").strip() if account else ""
    if (account and account.actif and account.source_auth == "local" and mailer.valid_address(address)
            and sso_policy.local_login_allowed(session, account) and _reset_disponible(session)):
        for old in session.exec(select(PasswordResetToken).where(PasswordResetToken.account_id == account.id)).all():
            session.delete(old)  # un seul lien valide a la fois
        token = secrets.token_urlsafe(32)
        session.add(PasswordResetToken(account_id=account.id, token_hash=_empreinte(token),
                                       expire_le=now + timedelta(minutes=RESET_TTL_MIN)))
        session.commit()
        audit(account.username, "reset_demande", ip=ip, status=202)
        background.add_task(_send_reset_mail, address, f"{mailer.public_url()}/reinitialisation?token={token}")
    else:
        session.commit()
        audit(data.identifiant.strip()[:100], "reset_demande_ignoree", ip=ip, status=202)
    return _RESET_REPONSE


@router.post("/reset")
def reset_password_with_token(data: ResetRequest, request: Request, session: Session = Depends(get_session)):
    ip = client_ip(request)
    wait = reset_limiter.retry_after(ip, "lien")
    if wait:
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard", headers={"Retry-After": str(wait)})
    now = datetime.utcnow()
    row = session.exec(select(PasswordResetToken).where(PasswordResetToken.token_hash == _empreinte(data.token))).first()
    account = session.get(Account, row.account_id) if row else None
    if (not row or row.utilise_le or row.expire_le < now or not account or not account.actif
            or not sso_policy.local_login_allowed(session, account)):
        reset_limiter.fail(ip, "lien")
        audit("anonyme", "reset_lien_refuse", ip=ip, status=400)
        raise HTTPException(400, "Lien invalide ou expire : refaites une demande de reinitialisation")
    check_password_policy(data.new_password)  # un mot de passe refuse laisse le lien utilisable
    account.hashed_password = hash_password(data.new_password)
    account.must_change_password = False
    account.token_epoch += 1  # toutes les sessions ouvertes de ce compte sont revoquees
    session.add(account)
    for other in session.exec(select(PasswordResetToken).where(PasswordResetToken.account_id == account.id)).all():
        session.delete(other)  # le lien utilise, comme les autres, disparait
    session.commit()
    audit(account.username, "mot_de_passe_reinitialise_par_lien", ip=ip, status=200)
    return {"detail": "Mot de passe modifie : vous pouvez vous connecter."}


def account_out(session: Session, account: Account) -> AccountOut:
    out = AccountOut.from_account(account)
    out.entites = sorted(r.entite_id for r in session.exec(select(AccountScope).where(AccountScope.account_id == account.id)).all())
    return out


def _set_scope(session: Session, account: Account, globale: bool, entites: list[int]) -> None:
    ids = sorted(set(entites))
    if ids and {e.id for e in session.exec(select(Entite).where(Entite.id.in_(ids))).all()} != set(ids):
        raise HTTPException(400, "Entite inconnue dans la portee")
    if globale and ids:
        raise HTTPException(400, "Une portee globale n'a pas de liste d'entites")
    account.portee_globale = globale
    for row in session.exec(select(AccountScope).where(AccountScope.account_id == account.id)).all():
        session.delete(row)
    session.flush()
    for eid in ids:
        session.add(AccountScope(account_id=account.id, entite_id=eid))


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account), session: Session = Depends(get_session)):
    out = account_out(session, account)
    scope = compute_scope(session, account)
    out.portee = {"globale": scope.globale, "vide": scope.vide, "entites": sorted(scope.ids)}
    return out


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
    scopes: dict[int, list[int]] = {}
    for r in session.exec(select(AccountScope)).all():
        scopes.setdefault(r.account_id, []).append(r.entite_id)
    out = []
    for a in sorted(rows, key=lambda a: a.username):
        item = AccountOut.from_account(a)
        item.entites = sorted(scopes.get(a.id, []))
        out.append(item)
    return out


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
        portee_globale=(data.role == Role.informatique),  # RH et lecture : aucune portee tant qu'elle n'est pas definie
    )
    if data.role == Role.informatique and (data.portee_globale is False or data.entites):
        raise HTTPException(400, "Les comptes informatique sont administrateurs : acces a toute l'organisation")
    session.add(account)
    session.flush()
    if data.role != Role.informatique and (data.portee_globale is not None or data.entites):
        _set_scope(session, account, bool(data.portee_globale), data.entites)
    session.commit()
    session.refresh(account)
    audit(admin.username, "compte_cree", target=account.username, detail=f"role : {account.role.value}")
    return AccountCreated(**account_out(session, account).model_dump(), mot_de_passe_provisoire=provisional)


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

    if data.role is not None and data.role != target.role and target.sso_oid:
        raise HTTPException(409, "Le role de ce compte est gere par Microsoft 365 (roles d'application Entra)")
    if data.secours is not None and data.secours != target.secours:
        if data.secours and target.source_auth == "sso":
            raise HTTPException(409, "Ce compte a ete cree par Microsoft 365 : il n'a pas de mot de passe local")
        if not data.secours and target.role == Role.informatique and target.actif and sso_policy.is_active(session) \
                and sso_policy.breakglass_count(session, exclude_id=target.id) < 1:
            raise HTTPException(409, "Impossible : ce serait le dernier compte de secours actif")
    if (data.actif is False) and target.role == Role.informatique and target.secours and target.source_auth == "local" \
            and sso_policy.is_active(session) and sso_policy.breakglass_count(session, exclude_id=target.id) < 1:
        raise HTTPException(409, "Impossible : ce serait le dernier compte de secours actif")
    changed = []
    old_role = target.role
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
    if data.secours is not None and data.secours != target.secours:
        target.secours = data.secours
        changed.append("secours")
    if data.password is not None:
        if target.source_auth == "sso":
            raise HTTPException(409, "Ce compte est gere par Microsoft 365 : pas de mot de passe local")
        check_password_policy(data.password)
        target.hashed_password = hash_password(data.password)
        changed.append("password")
        revoke = True
    if revoke:
        target.token_epoch += 1  # les sessions ouvertes de ce compte sont revoquees
    # Portee : l'informatique est toujours globale ; un compte qui quitte l'informatique repart sans portee.
    scope_before = (target.portee_globale, sorted(r.entite_id for r in session.exec(select(AccountScope).where(AccountScope.account_id == target.id)).all()))
    if target.role == Role.informatique:
        if data.portee_globale is False or data.entites:
            raise HTTPException(400, "Les comptes informatique sont administrateurs : acces a toute l'organisation")
        _set_scope(session, target, True, [])
    else:
        if old_role == Role.informatique:  # un administrateur retrograde repart sans portee
            _set_scope(session, target, False, [])
        if data.portee_globale is not None or data.entites is not None:
            _set_scope(session, target, bool(data.portee_globale), data.entites or [])
    scope_after = (target.portee_globale, sorted(r.entite_id for r in session.exec(select(AccountScope).where(AccountScope.account_id == target.id)).all()))
    if scope_after != scope_before:
        changed.append("portee")
    session.add(target)
    session.commit()
    session.refresh(target)
    audit(admin.username, "compte_modifie", target=target.username,
          detail=",".join(changed) if changed else "aucun changement")
    return account_out(session, target)


@router.post("/accounts/{account_id}/reset-password", response_model=ResetResult)
def reset_password(account_id: int, session: Session = Depends(get_session),
                   admin: Account = Depends(require_roles("informatique"))):
    """Nouveau mot de passe provisoire (affiche une seule fois), changement impose a la prochaine connexion."""
    target = session.get(Account, account_id)
    if not target:
        raise HTTPException(404, "Compte introuvable")
    if target.source_auth == "sso":
        raise HTTPException(409, "Ce compte est gere par Microsoft 365 : pas de mot de passe local")
    provisional = generate_temp_password()
    target.hashed_password = hash_password(provisional)
    target.must_change_password = True
    target.token_epoch += 1
    session.add(target)
    session.commit()
    audit(admin.username, "mot_de_passe_reinitialise", target=target.username)
    return ResetResult(mot_de_passe_provisoire=provisional)


class LierSso(BaseModel):
    upn: str = Field(max_length=200)

    @field_validator("upn")
    @classmethod
    def _upn(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Nom d'utilisateur Microsoft invalide (adresse du type prenom.nom@domaine)")
        return v


@router.post("/accounts/{account_id}/lier-sso", response_model=AccountOut)
def link_sso(account_id: int, data: LierSso, session: Session = Depends(get_session),
             admin: Account = Depends(require_roles("informatique"))):
    """Prepare la liaison d'un compte local a Microsoft 365 : la premiere connexion SSO de ce nom d'utilisateur
    Microsoft est rattachee a ce compte (jamais de rapprochement automatique par e-mail)."""
    target = session.get(Account, account_id)
    if not target:
        raise HTTPException(404, "Compte introuvable")
    if target.sso_oid:
        raise HTTPException(409, "Ce compte est deja lie a un compte Microsoft 365")
    if session.exec(select(Account).where(func.lower(Account.sso_upn) == data.upn, Account.id != target.id)).first():
        raise HTTPException(409, "Ce nom d'utilisateur Microsoft est deja associe a un autre compte")
    target.sso_upn = data.upn
    session.add(target)
    session.commit()
    session.refresh(target)
    audit(admin.username, "compte_lie_sso", target=target.username, detail=f"upn : {data.upn}")
    return AccountOut.from_account(target)


@router.post("/accounts/{account_id}/delier-sso", response_model=AccountOut)
def unlink_sso(account_id: int, session: Session = Depends(get_session),
               admin: Account = Depends(require_roles("informatique"))):
    target = session.get(Account, account_id)
    if not target:
        raise HTTPException(404, "Compte introuvable")
    if target.source_auth == "sso":
        raise HTTPException(409, "Ce compte a ete cree par Microsoft 365 : desactivez-le plutot que de le delier")
    if not (target.sso_oid or target.sso_upn):
        raise HTTPException(409, "Ce compte n'est pas lie a Microsoft 365")
    target.sso_oid, target.sso_upn = None, None
    target.token_epoch += 1
    session.add(target)
    session.commit()
    session.refresh(target)
    audit(admin.username, "compte_delie_sso", target=target.username)
    return AccountOut.from_account(target)
