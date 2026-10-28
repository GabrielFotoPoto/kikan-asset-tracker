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

"""Connexion Microsoft 365 : parcours de connexion, ticket de session, administration du SSO."""
import json
import re
import secrets
import time
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .. import appsettings, sso, sso_policy
from ..audit import audit
from ..auth import client_ip, create_access_token, hash_password, login_limiter, require_roles
from ..db import get_session
from ..models import Account, AccountScope, Role
from .auth import USERNAME_RE, TokenResponse

router = APIRouter(prefix="/auth/sso", tags=["sso"])
admin_only = [Depends(require_roles("informatique"))]


def _cookie_args() -> dict:
    return {"path": "/api/auth/sso", "httponly": True, "samesite": "lax", "secure": sso.public_url().startswith("https://")}


PROTOCOL_ERRORS = {"session", "idp", "jeton", "echange", "reseau"}


def _protocol_failure(ip: str) -> None:
    """Echec de protocole (etat, jeton, echange) : compte uniquement dans la limite globale par adresse, jamais par
    compte, pour qu'une personne refusee ne bloque pas les autres utilisateurs du meme reseau."""
    login_limiter.fail(ip, "sso-" + secrets.token_hex(4))


def _front(path: str) -> RedirectResponse:
    resp = RedirectResponse(sso.public_url() + path, status_code=303)
    resp.delete_cookie(sso.COOKIE, path="/api/auth/sso")
    return resp


# --- Publique : etat pour la page de connexion ---

@router.get("/config")
def public_config(session: Session = Depends(get_session)):
    cfg = sso_policy.read(session)
    active = sso.configured() and cfg["actif"]
    return {"actif": active, "mode_local": cfg["mode_local"] if active else "autorise"}


@router.get("/login")
def login_start(session: Session = Depends(get_session)):
    """Redirige vers Microsoft (le navigateur est ensuite renvoye sur /callback)."""
    if not sso_policy.is_active(session):
        raise HTTPException(404, "Connexion Microsoft 365 non activee")
    try:
        url, state = sso.new_flow("login")
    except sso.SsoError as exc:
        audit("anonyme", "sso_refuse", detail=f"{exc.code} {exc.detail}"[:200])
        return RedirectResponse(sso.public_url() + f"/login?sso_erreur={exc.code}", status_code=303)
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(sso.COOKIE, state, max_age=sso.FLOW_TTL, **_cookie_args())
    return resp


# --- Retour de Microsoft ---

def _resolve_account(session: Session, claims: dict, role: Role, cfg: dict) -> Account:
    oid, upn = str(claims["oid"]), sso.upn_of(claims)
    name = str(claims.get("name") or "").strip()[:120] or None
    email = str(claims.get("email") or (upn if "@" in upn else "") or "").strip()[:200] or None
    account = session.exec(select(Account).where(Account.sso_oid == oid)).first()
    if account is None and upn:  # liaison preparee par l'administrateur : meme nom d'utilisateur Microsoft, pas encore lie
        account = session.exec(select(Account).where(func.lower(Account.sso_upn) == upn, Account.sso_oid.is_(None))).first()
    created = False
    if account is None:
        if not cfg["creation_auto"]:
            raise sso.SsoError("compte", "compte inconnu (creation automatique desactivee)")
        username = upn if USERNAME_RE.match(upn) else "sso-" + oid.replace("-", "")[:12].lower()
        if session.exec(select(Account).where(func.lower(Account.username) == username)).first():
            raise sso.SsoError("compte", "identifiant deja utilise par un autre compte : liaison necessaire")
        account = Account(username=username, role=role, actif=True, hashed_password=hash_password(secrets.token_urlsafe(48)),
                          source_auth="sso", secours=False,
                          portee_globale=(role == Role.informatique))  # RH : aucune portee tant qu'un administrateur n'en definit pas
        created = True
    if not account.actif:
        raise sso.SsoError("compte", "compte desactive dans Kikan")
    changed_role = (not created) and account.role != role
    if changed_role:
        if role == Role.informatique:
            account.portee_globale = True
        elif account.role == Role.informatique:  # retrograde par Microsoft : plus de portee tant qu'elle n'est pas redefinie
            account.portee_globale = False
            for row in session.exec(select(AccountScope).where(AccountScope.account_id == account.id)).all():
                session.delete(row)
    account.sso_oid, account.sso_upn, account.role = oid, upn or account.sso_upn, role
    account.nom_affiche = name or account.nom_affiche
    account.email = email or account.email
    if changed_role:
        account.token_epoch += 1  # le role vient de Microsoft : les sessions ouvertes sont recalculees
    account.derniere_connexion = datetime.utcnow()
    session.add(account)
    session.commit()
    session.refresh(account)
    if created:
        audit(account.username, "sso_compte_cree", target=account.username, detail=f"role : {role.value}")
    elif changed_role:
        audit(account.username, "sso_role_modifie", target=account.username, detail=f"role : {role.value}")
    return account


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             session: Session = Depends(get_session)):
    ip = client_ip(request)
    if login_limiter.retry_after(ip, "sso"):
        audit("anonyme", "sso_refuse", ip=ip, detail="trop de tentatives")
        return _front("/login?sso_erreur=trop_de_tentatives")
    cookie = request.cookies.get(sso.COOKIE, "")
    flow = sso.pop_flow(state) if state and cookie and secrets.compare_digest(state, cookie) else None
    if flow is None:
        _protocol_failure(ip)
        audit("anonyme", "sso_refuse", ip=ip, detail="etat invalide ou expire")
        return _front("/login?sso_erreur=session")
    test = flow["mode"] == "test"

    def refuse(code_: str, detail: str, who: str = "anonyme") -> RedirectResponse:
        if code_ in PROTOCOL_ERRORS:
            _protocol_failure(ip)  # un refus d'acces (role, MFA, compte) n'est pas une attaque : jamais compte
        audit(who, "sso_refuse_test" if test else "sso_refuse", ip=ip, detail=f"{code_} {detail}"[:200])
        return _front(f"/parametres?sso_test=refuse&motif={code_}" if test else f"/login?sso_erreur={code_}")

    if error or not code:
        return refuse("idp", f"retour de Microsoft : {(error or 'sans code')[:40]}")
    cfg = sso_policy.read(session)
    try:
        tokens = sso.exchange_code(code, flow["verifier"])
        claims = sso.validate_id_token(tokens["id_token"], flow["nonce"])
        upn = sso.upn_of(claims) or str(claims.get("oid"))
        role = sso.role_from_claims(claims, cfg["role_it"], cfg["role_rh"])
        if role is None:
            raise sso.SsoError("role", f"{upn} : aucun role Kikan")
        if cfg["exiger_mfa"] and not sso.mfa_done(claims):
            raise sso.SsoError("mfa", f"{upn} : MFA absente du jeton")
        if test:
            appsettings.put(session, sso_policy.KEYS["test"], json.dumps(
                {"par": flow["test_by"], "upn": upn, "role": role.value, "ts": time.time(), "mfa": sso.mfa_done(claims)}))
            session.commit()
            audit(flow["test_by"] or "anonyme", "sso_test_ok", ip=ip, detail=f"{upn} role {role.value}")
            return _front("/parametres?sso_test=ok")
        account = _resolve_account(session, claims, role, cfg)
    except sso.SsoError as exc:
        return refuse(exc.code, exc.detail, (flow["test_by"] or "anonyme") if test else "anonyme")
    login_limiter.success(ip, "sso")
    audit(account.username, "sso_login_ok", ip=ip, status=200, detail=upn)
    return _front("/sso?ticket=" + quote(sso.new_ticket(account.username)))


class Ticket(BaseModel):
    ticket: str = Field(max_length=200)


@router.post("/exchange", response_model=TokenResponse)
def exchange(data: Ticket, request: Request, session: Session = Depends(get_session)):
    """Echange le ticket a usage unique (60 s) contre la session Kikan."""
    ip = client_ip(request)
    if login_limiter.retry_after(ip, "sso-ticket"):
        raise HTTPException(429, "Trop de tentatives, reessayez plus tard")
    username = sso.pop_ticket(data.ticket)
    account = session.exec(select(Account).where(func.lower(Account.username) == username.lower())).first() if username else None
    if not account or not account.actif:
        login_limiter.fail(ip, "sso-ticket")
        raise HTTPException(401, "Ticket invalide ou expire")
    return TokenResponse(access_token=create_access_token(account.username, account.role.value, account.token_epoch),
                         username=account.username, role=account.role.value, must_change_password=False)


# --- Administration (informatique) ---

class Reglages(BaseModel):
    mode_local: str = "secours"
    creation_auto: bool = True
    exiger_mfa: bool = True
    role_it: str = Field(default="Kikan.IT", min_length=1, max_length=100)
    role_rh: str = Field(default="Kikan.RH", min_length=1, max_length=100)
    secret_expire: str = ""
    ttl: int = Field(default=240, ge=sso_policy.TTL_MIN, le=sso_policy.TTL_MAX)


def _state(session: Session, admin: Account) -> dict:
    cfg = sso_policy.read(session)
    return {
        "config": sso.config_summary(),
        "reglages": {k: cfg[k] for k in ("mode_local", "creation_auto", "exiger_mfa", "role_it", "role_rh", "secret_expire", "ttl")},
        "actif": cfg["actif"],
        "test": cfg["test"],
        "comptes_secours": sso_policy.breakglass_count(session),
        "blocages": [] if cfg["actif"] else sso_policy.activation_blockers(session, admin.username),
        "avertissement": sso_policy.secret_expiry_warning(session),
    }


@router.get("/admin/etat", dependencies=admin_only)
def admin_state(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    return _state(session, admin)


@router.put("/admin/reglages")
def admin_settings(data: Reglages, session: Session = Depends(get_session),
                   admin: Account = Depends(require_roles("informatique"))):
    if data.mode_local not in sso_policy.MODES:
        raise HTTPException(422, "Mode de connexion locale inconnu")
    if data.secret_expire:
        try:
            date.fromisoformat(data.secret_expire)
        except ValueError:
            raise HTTPException(422, "Date d'expiration invalide (AAAA-MM-JJ)")
    if not re.fullmatch(r"[A-Za-z0-9._ -]{1,100}", data.role_it + "") or not re.fullmatch(r"[A-Za-z0-9._ -]{1,100}", data.role_rh + ""):
        raise HTTPException(422, "Nom de role invalide")
    cfg = sso_policy.read(session)
    if cfg["actif"] and data.mode_local == "secours" and sso_policy.breakglass_count(session) < 1:
        raise HTTPException(409, "Mode secours impossible : aucun compte local de secours actif")
    before = {k: cfg[k] for k in ("mode_local", "creation_auto", "exiger_mfa", "role_it", "role_rh", "secret_expire", "ttl")}
    new = data.model_dump()
    for key in before:
        value = new[key]
        appsettings.put(session, sso_policy.KEYS[key], ("1" if value else "0") if isinstance(value, bool) else str(value))
    session.commit()
    audit(admin.username, "sso_reglages", detail="champs : " + (", ".join(k for k in before if before[k] != new[k]) or "aucun changement"))
    return _state(session, admin)


@router.post("/admin/tester-config", dependencies=admin_only)
def admin_test_config():
    """Verifie que la decouverte et les cles de signature de Microsoft sont joignables avec cette configuration."""
    if not sso.configured():
        raise HTTPException(409, "Configuration incomplete : " + ", ".join(sso.config_summary()["manque"] or ["autorite"]))
    try:
        sso.reset_caches()
        doc = sso.discovery(force=True)
        keys = sso._fetch(doc["jwks_uri"]).get("keys", [])
    except sso.SsoError as exc:
        raise HTTPException(502, f"Microsoft injoignable ou configuration refusee ({exc.code} : {exc.detail})") from exc
    return {"ok": True, "emetteur": doc["issuer"], "cles": len(keys)}


@router.post("/admin/test-start")
def admin_test_start(response: Response, admin: Account = Depends(require_roles("informatique"))):
    """Debut du test de connexion : renvoie l'adresse Microsoft vers laquelle envoyer le navigateur."""
    try:
        url, state = sso.new_flow("test", test_by=admin.username)
    except sso.SsoError as exc:
        raise HTTPException(409, f"Test impossible ({exc.code})") from exc
    response.set_cookie(sso.COOKIE, state, max_age=sso.FLOW_TTL, **_cookie_args())
    return {"url": url}


@router.post("/admin/activer")
def admin_activate(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    blockers = sso_policy.activation_blockers(session, admin.username)
    if blockers:
        raise HTTPException(409, "Activation impossible : " + " ; ".join(blockers))
    appsettings.put(session, sso_policy.KEYS["actif"], "1")
    session.commit()
    audit(admin.username, "sso_active")
    return _state(session, admin)


@router.post("/admin/desactiver")
def admin_deactivate(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    appsettings.put(session, sso_policy.KEYS["actif"], "0")
    session.commit()
    audit(admin.username, "sso_desactive")
    return _state(session, admin)
