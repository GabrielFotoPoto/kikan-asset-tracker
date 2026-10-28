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

"""Connexion unique Microsoft 365 (Entra ID) : OpenID Connect, flux code d'autorisation + PKCE, cote serveur.

Regles de securite appliquees ici :
- un seul tenant accepte (emetteur et `tid` fixes) ; jamais de point d'entree "common" ;
- jeton valide de bout en bout : algorithme RS256 uniquement, signature par les cles publiees du tenant,
  emetteur, public (client id), expiration, `nonce` ; `state` a usage unique lie au navigateur par un cookie ;
- adresse de retour fixee par la configuration (jamais deduite de la requete) ;
- aucun jeton ni secret journalise ; aucune redirection suivie lors des appels sortants ;
- le secret du client vient de l'environnement, jamais de la base.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from jwt.algorithms import RSAAlgorithm

from .models import Role

IS_PROD = os.environ.get("KIKAN_ENV", "development").lower() == "production"
COOKIE = "kikan_sso_state"
FLOW_TTL = 600
TICKET_TTL = 60
MAX_TOKEN_CHARS = 16384
LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}


class SsoError(Exception):
    """Echec SSO : `code` (stable, affiche a l'utilisateur) et `detail` (journal, sans secret)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


# --- Configuration (lue a chaque appel : l'environnement peut etre injecte au demarrage) ---

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def authority() -> str:
    return _env("KIKAN_SSO_AUTHORITY", "https://login.microsoftonline.com").rstrip("/")


def tenant() -> str:
    return _env("KIKAN_SSO_TENANT_ID")


def client_id() -> str:
    return _env("KIKAN_SSO_CLIENT_ID")


def client_secret() -> str:
    return _env("KIKAN_SSO_CLIENT_SECRET")


def public_url() -> str:
    return _env("KIKAN_PUBLIC_URL").rstrip("/")


def redirect_uri() -> str:
    return public_url() + "/api/auth/sso/callback"


def expected_issuer() -> str:
    return f"{authority()}/{tenant()}/v2.0"


def authority_ok() -> bool:
    """HTTPS obligatoire ; HTTP tolere uniquement vers la machine locale hors production (tests)."""
    parsed = urllib.parse.urlparse(authority())
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and parsed.hostname in LOOPBACK and not IS_PROD


def configured() -> bool:
    return bool(tenant() and client_id() and client_secret() and public_url() and authority_ok()
                and (public_url().startswith("https://") or not IS_PROD))


def config_summary() -> dict:
    """Etat de la configuration pour l'ecran de parametrage : jamais le secret ni les identifiants en clair."""
    def mask(v: str) -> str:
        return (v[:8] + "...") if len(v) > 8 else ("***" if v else "")
    return {
        "configure": configured(),
        "tenant": mask(tenant()), "client_id": mask(client_id()), "secret_present": bool(client_secret()),
        "public_url": public_url(), "redirect_uri": redirect_uri() if public_url() else "",
        "autorite": urllib.parse.urlparse(authority()).netloc,
        "manque": [n for n, v in (("KIKAN_SSO_TENANT_ID", tenant()), ("KIKAN_SSO_CLIENT_ID", client_id()),
                                  ("KIKAN_SSO_CLIENT_SECRET", client_secret()), ("KIKAN_PUBLIC_URL", public_url())) if not v],
    }


# --- Appels sortants (decouverte, cles, echange du code) ---

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # une redirection inattendue est une erreur, jamais suivie
        return None


def _opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context(cafile=_env("KIKAN_SSO_CA_BUNDLE") or None)
    proxy = _env("KIKAN_SSO_PROXY")
    return urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=ctx),
        urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}),
    )


def _fetch(url: str, form: dict | None = None, timeout: int = 10, max_bytes: int = 1_000_000) -> dict:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if form is not None else "GET",
                                 headers={"Accept": "application/json"})
    try:
        with _opener().open(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1)
        try:
            err = json.loads(body).get("error", "")
        except ValueError:
            err = ""
        raise SsoError("echange", f"HTTP {exc.code} {str(err)[:60]}") from exc
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        raise SsoError("reseau", f"{type(exc).__name__}: {str(exc)[:120]}") from exc
    if len(body) > max_bytes:
        raise SsoError("echange", "reponse trop volumineuse")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SsoError("echange", "reponse non JSON") from exc


_cache_lock = threading.Lock()
_discovery: dict = {"ts": 0.0, "doc": None}
_jwks: dict = {"ts": 0.0, "keys": {}, "last_try": 0.0}


def _same_authority(url: str) -> bool:
    a, u = urllib.parse.urlparse(authority()), urllib.parse.urlparse(url)
    return u.scheme == a.scheme and u.netloc == a.netloc


def discovery(force: bool = False) -> dict:
    with _cache_lock:
        if not force and _discovery["doc"] and time.time() - _discovery["ts"] < 3600:
            return _discovery["doc"]
    doc = _fetch(f"{authority()}/{tenant()}/v2.0/.well-known/openid-configuration")
    if doc.get("issuer") != expected_issuer():
        raise SsoError("config", "emetteur de la decouverte inattendu")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not _same_authority(str(doc.get(key, ""))):
            raise SsoError("config", f"{key} hors de l'autorite configuree")
    with _cache_lock:
        _discovery.update(ts=time.time(), doc=doc)
    return doc


def _signing_key(kid: str):
    with _cache_lock:
        known = _jwks["keys"].get(kid)
        recent = time.time() - _jwks["last_try"] < 60
        fresh = time.time() - _jwks["ts"] < 3600
    if known is not None and fresh:
        return known
    if recent and known is None and _jwks["keys"]:
        raise SsoError("jeton", "cle de signature inconnue")
    doc = _fetch(discovery()["jwks_uri"])
    keys = {}
    for jwk in doc.get("keys", []):
        if jwk.get("kty") == "RSA" and jwk.get("kid") and jwk.get("use", "sig") == "sig":
            keys[jwk["kid"]] = RSAAlgorithm.from_jwk(json.dumps(jwk))
    with _cache_lock:
        _jwks.update(ts=time.time(), keys=keys, last_try=time.time())
    if kid not in keys:
        raise SsoError("jeton", "cle de signature inconnue")
    return keys[kid]


def reset_caches() -> None:
    with _cache_lock:
        _discovery.update(ts=0.0, doc=None)
        _jwks.update(ts=0.0, keys={}, last_try=0.0)


# --- Flux d'autorisation ---

_pending: dict[str, dict] = {}
_tickets: dict[str, dict] = {}
_flow_lock = threading.Lock()


def _purge(store: dict, ttl: int) -> None:
    now = time.time()
    for k in [k for k, v in store.items() if now - v["ts"] > ttl]:
        store.pop(k, None)


def new_flow(mode: str = "login", test_by: str | None = None) -> tuple[str, str]:
    """Debut d'une connexion : (adresse d'autorisation, valeur du cookie d'etat)."""
    if not configured():
        raise SsoError("config", "SSO non configure")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with _flow_lock:
        _purge(_pending, FLOW_TTL)
        if len(_pending) > 2000:
            raise SsoError("trop_de_tentatives", "trop de connexions en cours")
        _pending[state] = {"ts": time.time(), "nonce": nonce, "verifier": verifier, "mode": mode, "test_by": test_by}
    params = {
        "client_id": client_id(), "response_type": "code", "redirect_uri": redirect_uri(), "response_mode": "query",
        "scope": "openid profile email", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }
    if mode == "test":
        params["prompt"] = "select_account"
    return discovery()["authorization_endpoint"] + "?" + urllib.parse.urlencode(params), state


def pop_flow(state: str) -> dict | None:
    """Etat a usage unique."""
    with _flow_lock:
        _purge(_pending, FLOW_TTL)
        return _pending.pop(state, None)


def new_ticket(username: str) -> str:
    ticket = secrets.token_urlsafe(32)
    with _flow_lock:
        _purge(_tickets, TICKET_TTL)
        _tickets[ticket] = {"ts": time.time(), "username": username}
    return ticket


def pop_ticket(ticket: str) -> str | None:
    with _flow_lock:
        _purge(_tickets, TICKET_TTL)
        entry = _tickets.pop(ticket, None)
    return entry["username"] if entry else None


def exchange_code(code: str, verifier: str) -> dict:
    tokens = _fetch(discovery()["token_endpoint"], form={
        "grant_type": "authorization_code", "client_id": client_id(), "client_secret": client_secret(),
        "code": code, "redirect_uri": redirect_uri(), "code_verifier": verifier,
    })
    if not tokens.get("id_token"):
        raise SsoError("echange", "pas de jeton d'identite")
    return tokens


def validate_id_token(id_token: str, nonce: str) -> dict:
    """Revendications du jeton d'identite, apres verification complete (sinon SsoError)."""
    if not isinstance(id_token, str) or len(id_token) > MAX_TOKEN_CHARS:
        raise SsoError("jeton", "jeton absent ou trop long")
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise SsoError("jeton", "en-tete illisible") from exc
    if header.get("alg") != "RS256":
        raise SsoError("jeton", f"algorithme refuse : {str(header.get('alg'))[:20]}")
    key = _signing_key(str(header.get("kid", "")))
    try:
        claims = jwt.decode(
            id_token, key=key, algorithms=["RS256"], audience=client_id(), issuer=expected_issuer(), leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise SsoError("jeton", f"{type(exc).__name__}") from exc
    if claims.get("tid") != tenant():
        raise SsoError("jeton", "tenant different")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("jeton", "nonce different")
    if not claims.get("oid"):
        raise SsoError("jeton", "identifiant oid absent")
    return claims


# --- Roles et MFA ---

def role_from_claims(claims: dict, role_it: str, role_rh: str) -> Role | None:
    roles = claims.get("roles")
    roles = [r for r in roles if isinstance(r, str)] if isinstance(roles, list) else []
    if role_it in roles:
        return Role.informatique
    if role_rh in roles:
        return Role.rh
    return None


def mfa_done(claims: dict) -> bool:
    amr = claims.get("amr")
    return isinstance(amr, list) and "mfa" in amr


def upn_of(claims: dict) -> str:
    return str(claims.get("preferred_username") or claims.get("upn") or claims.get("email") or "").strip().lower()
