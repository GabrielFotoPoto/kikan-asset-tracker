# Kikan - suivi des actifs et remise de materiel signee
# Copyright (C) 2026 Gabriel Chollet
# Developpe avec l'assistance d'une IA (Gemini, Google DeepMind).
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

"""Connecteur Active Directory local (LDAP / LDAPS) reserve au role demandeur (lot G5).

Securite :
- Parametres de connexion et secret de bind exclusivement en variables d'environnement.
- LDAPS (636) ou StartTLS (389) obligatoire par defaut ; chiffrement desactive refuse en production.
- Validation des hotes via netguard.py, echappement RFC 4515, refus des mots de passe vides.
- Flux en deux temps : bind compte de service lecture seule -> recherche DN -> bind utilisateur -> fermeture.
- Role demandeur uniquement, liaison stable par external_uid (objectGUID), audit pseudonyme dem-<id>.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fastapi import HTTPException
from ldap3 import BASE, Connection, NONE, SIMPLE, SUBTREE, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import func
from sqlmodel import Session, select

from . import appsettings, netguard
from .audit import audit
from .auth import IS_PROD, audit_actor, hash_password
from .models import Account, EmployeeStatus, PasswordResetToken, Role, User

log = logging.getLogger("kikan.ldap")

ATTRIBUTS_AUTORISES = ("mail", "userPrincipalName", "sAMAccountName")
TLS_MODES = ("ldaps", "starttls")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,63}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

KEY_ACTIF = "ldap_actif"
KEY_ATTRIBUT = "ldap_attribut"
KEY_GROUPE_DN = "ldap_groupe_dn"


@dataclass(frozen=True)
class LdapIdentity:
    external_uid: str
    email: str | None
    upn: str | None
    sam: str | None
    display_name: str | None
    attribut: str = "mail"


# Hook de test (uniquement pour tests/ldap_check.py avec annuaire simule)
_TEST_CLIENT_FACTORY: Callable[[str, int, bool, Tls | None, int], tuple[Server, str]] | None = None
# Moyenne glissante de la latence observee sur l'annuaire AD (pour uniformiser les 401 entre local et AD)
_OBSERVED_LATENCY_SEC: float = 0.35


def login_fail_floor_sec() -> float:
    """Plancher de latence pour les echecs 401 quand LDAP est actif (cale sur la latence AD observee, borne par le timeout)."""
    cap = min(float(_timeout()), 2.0)
    return max(0.35, min(_OBSERVED_LATENCY_SEC, cap))


def _record_latency(elapsed: float) -> None:
    global _OBSERVED_LATENCY_SEC
    if elapsed > 0:
        _OBSERVED_LATENCY_SEC = round(0.7 * _OBSERVED_LATENCY_SEC + 0.3 * elapsed, 3)


def _hosts() -> list[str]:
    raw = os.environ.get("KIKAN_LDAP_HOSTS", "")
    return [h.strip() for h in raw.split(",") if h.strip()]


def _tls_mode() -> str:
    mode = (os.environ.get("KIKAN_LDAP_TLS", "ldaps") or "ldaps").strip().lower()
    return mode


def _port() -> int:
    raw = (os.environ.get("KIKAN_LDAP_PORT", "") or "").strip()
    if raw.isdigit():
        p = int(raw)
        if 1 <= p <= 65535:
            return p
    return 636 if _tls_mode() == "ldaps" else 389


def _timeout() -> int:
    raw = (os.environ.get("KIKAN_LDAP_TIMEOUT_SEC", "5") or "5").strip()
    if raw.isdigit():
        return max(1, min(15, int(raw)))
    return 5


def _ca_bundle() -> str:
    return (os.environ.get("KIKAN_LDAP_CA_BUNDLE", "") or "").strip()


def _base_dn() -> str:
    return (os.environ.get("KIKAN_LDAP_BASE_DN", "") or "").strip()


def _bind_dn() -> str:
    return (os.environ.get("KIKAN_LDAP_BIND_DN", "") or "").strip()


def _bind_password() -> str:
    return os.environ.get("KIKAN_LDAP_BIND_PASSWORD", "") or ""


def _allow_insecure_dev() -> bool:
    return (not IS_PROD) and os.environ.get("KIKAN_LDAP_ALLOW_INSECURE", "").strip().lower() == "true"


def config_summary() -> dict:
    hosts = _hosts()
    tls = _tls_mode()
    manque: list[str] = []
    if not hosts:
        manque.append("KIKAN_LDAP_HOSTS")
    if not _base_dn():
        manque.append("KIKAN_LDAP_BASE_DN")
    if not _bind_dn():
        manque.append("KIKAN_LDAP_BIND_DN")
    if not _bind_password():
        manque.append("KIKAN_LDAP_BIND_PASSWORD")
    if tls not in TLS_MODES and not (tls == "none" and _allow_insecure_dev()):
        manque.append("KIKAN_LDAP_TLS (ldaps ou starttls)")
    return {
        "configure": len(manque) == 0,
        "manque": manque,
        "hosts": hosts,
        "port": _port(),
        "tls": tls,
        "base_dn": _base_dn(),
        "bind_dn": _bind_dn(),
        "bind_password_present": bool(_bind_password()),
        "ca_bundle": _ca_bundle() or None,
        "timeout_sec": _timeout(),
    }


def configured() -> bool:
    return config_summary()["configure"]


def read_settings(session: Session) -> dict:
    actif = appsettings.get(session, KEY_ACTIF, "0") == "1"
    attr = appsettings.get(session, KEY_ATTRIBUT, "mail") or "mail"
    if attr not in ATTRIBUTS_AUTORISES:
        attr = "mail"
    groupe = (appsettings.get(session, KEY_GROUPE_DN, "") or "").strip()
    return {"actif": actif, "attribut": attr, "groupe_dn": groupe}


def is_active(session: Session) -> bool:
    return configured() and read_settings(session)["actif"]


def escape_filter(value: str) -> str:
    """Echappement RFC 4515 strict avant construction de filtre LDAP."""
    return escape_filter_chars(value)


def _validate_hosts(hosts: list[str], *, expose_detail: bool = False) -> list[str]:
    valid: list[str] = []
    for h in hosts:
        err = netguard.probleme_hote(h)
        if err:
            if expose_detail:
                raise HTTPException(400, f"Hote LDAP refuse ({h}) : {err}")
            log.warning("Hote LDAP refuse par netguard : %s", err)
            continue
        valid.append(h)
    return valid


def _build_tls() -> Tls:
    ca = _ca_bundle()
    return Tls(
        validate=ssl.CERT_REQUIRED,
        version=ssl.PROTOCOL_TLS_CLIENT,
        ca_certs_file=ca if ca else None,
    )


def _open_connection(host: str, user_dn: str, password: str) -> Connection:
    tls_mode = _tls_mode()
    if tls_mode not in TLS_MODES and not (tls_mode == "none" and _allow_insecure_dev()):
        raise RuntimeError("Mode TLS LDAP interdit (ldaps ou starttls requis)")
    port = _port()
    timeout = _timeout()
    use_ssl = tls_mode == "ldaps"
    tls_obj = None if tls_mode == "none" else _build_tls()

    if _TEST_CLIENT_FACTORY is not None:
        server, strategy = _TEST_CLIENT_FACTORY(host, port, use_ssl, tls_obj, timeout)
        conn = Connection(
            server, user=user_dn, password=password,
            authentication=SIMPLE, client_strategy=strategy,
            auto_referrals=False, receive_timeout=timeout, raise_exceptions=False,
        )
        conn.bind()
        return conn

    server = Server(host, port=port, use_ssl=use_ssl, tls=tls_obj, connect_timeout=timeout, get_info=NONE)
    conn = Connection(
        server, user=user_dn, password=password,
        authentication=SIMPLE, auto_referrals=False, receive_timeout=timeout, raise_exceptions=False,
    )
    if tls_mode == "starttls":
        conn.open()
        if not conn.start_tls():
            conn.unbind()
            raise RuntimeError("Echec negociation StartTLS")
    conn.bind()
    return conn


def _normalize_guid(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).hex().lower()
    s = str(raw).strip().strip("{}").lower()
    return s[:255] if s else None


def _first_str(entry, attr: str) -> str | None:
    try:
        val = entry[attr].value
    except Exception:  # noqa: BLE001
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _member_of_list(entry) -> list[str]:
    try:
        val = entry["memberOf"].values
    except Exception:  # noqa: BLE001
        return []
    return [str(v).strip().lower() for v in (val or []) if v]


def test_connection() -> dict:
    """Teste la connexion de service (bind + lecture base DN) sans jamais exposer le secret."""
    summary = config_summary()
    if not summary["configure"]:
        raise HTTPException(409, "Configuration LDAP incomplete : " + ", ".join(summary["manque"]))
    hosts = _validate_hosts(summary["hosts"], expose_detail=True)
    base_dn = _base_dn()
    last_err = "injoignable"
    for host in hosts:
        conn = None
        try:
            conn = _open_connection(host, _bind_dn(), _bind_password())
            if not conn.bound:
                last_err = "bind compte de service refuse"
                continue
            ok = conn.search(search_base=base_dn, search_filter="(objectClass=*)", search_scope=BASE, attributes=["dn"])
            if not ok:
                last_err = "base DN introuvable ou inaccessible"
                continue
            return {"ok": True, "host": host, "tls": summary["tls"]}
        except (LDAPException, OSError, RuntimeError) as exc:
            last_err = type(exc).__name__
        finally:
            if conn is not None:
                try:
                    conn.unbind()
                except Exception:  # noqa: BLE001
                    pass
    raise HTTPException(502, f"Annuaire LDAP injoignable ou refuse ({last_err})")


def authenticate(
    username: str,
    password: str,
    *,
    attribut: str = "mail",
    groupe_dn: str = "",
) -> LdapIdentity | None:
    """Authentifie un salarie contre AD/LDAP en deux temps. Retourne None en cas d'echec."""
    # Refus strict des mots de passe vides (anti-bind anonyme) et controles de saisie
    if not username or not password or not password.strip():
        return None
    if len(username) > 200 or _CTRL_RE.search(username):
        return None
    if attribut not in ATTRIBUTS_AUTORISES:
        return None
    if not configured():
        return None

    hosts = _validate_hosts(_hosts(), expose_detail=False)
    if not hosts:
        return None
    base_dn = _base_dn()
    safe_user = escape_filter(username.strip())
    ldap_filter = f"(&(objectClass=user)(!(objectClass=computer))({attribut}={safe_user}))"
    attrs = ["objectGUID", "mail", "userPrincipalName", "sAMAccountName", "displayName", "memberOf"]
    wanted_group = (groupe_dn or "").strip().lower()

    for host in hosts:
        svc_conn = None
        user_conn = None
        t_start = time.monotonic()
        try:
            svc_conn = _open_connection(host, _bind_dn(), _bind_password())
            if not svc_conn.bound:
                log.warning("LDAP bind service refuse sur %s", host)
                continue
            svc_conn.search(
                search_base=base_dn,
                search_filter=ldap_filter,
                search_scope=SUBTREE,
                attributes=attrs,
                size_limit=2,
            )
            entries = list(svc_conn.entries or [])
            if len(entries) != 1:
                return None
            entry = entries[0]
            user_dn = str(entry.entry_dn or "").strip()
            if not user_dn:
                return None

            # Controle du groupe AD autorise (facultatif)
            if wanted_group and wanted_group not in _member_of_list(entry):
                return None

            # Etape 2 : bind utilisateur avec le DN exact et le mot de passe saisi
            user_conn = _open_connection(host, user_dn, password)
            if not user_conn.bound:
                return None

            guid = None
            try:
                raw_guid = entry["objectGUID"].raw_values
                guid = _normalize_guid(raw_guid[0] if raw_guid else None)
            except Exception:  # noqa: BLE001
                guid = None
            if not guid:
                guid = "dn:" + hashlib.sha256(user_dn.lower().encode("utf-8")).hexdigest()

            mail = _first_str(entry, "mail")
            upn = _first_str(entry, "userPrincipalName")
            sam = _first_str(entry, "sAMAccountName")
            disp = _first_str(entry, "displayName")
            return LdapIdentity(
                external_uid=guid,
                email=mail.lower() if mail else None,
                upn=upn.lower() if upn else None,
                sam=sam.lower() if sam else None,
                display_name=disp[:120] if disp else None,
                attribut=attribut,
            )
        except (LDAPException, OSError, RuntimeError) as exc:
            log.warning("Erreur LDAP sur %s : %s", host, type(exc).__name__)
            continue
        finally:
            _record_latency(time.monotonic() - t_start)
            for c in (user_conn, svc_conn):
                if c is not None:
                    try:
                        c.unbind()
                    except Exception:  # noqa: BLE001
                        pass
    return None


def _purger_jetons_reset(session: Session, account_id: int) -> None:
    for tok in session.exec(select(PasswordResetToken).where(PasswordResetToken.account_id == account_id)).all():
        session.delete(tok)


def resolve_ldap_account(session: Session, ident: LdapIdentity) -> Account | None:
    """Resout ou provisionne le compte demandeur associe a une identite LDAP validee.

    Retourne None si le salarie n'est pas provisionne (refus uniforme 403).
    """
    now = datetime.utcnow()

    # 1. Liaison stable prioritaire par external_uid (objectGUID)
    account = session.exec(select(Account).where(Account.external_uid == ident.external_uid)).first()
    if account is not None:
        if not account.actif or account.role != Role.demandeur or account.source_auth != "ldap" or account.user_id is None:
            return None
        user = session.get(User, account.user_id)
        if not user or user.statut != EmployeeStatus.actif:
            return None
        account.nom_affiche = f"{user.prenom} {user.nom}".strip()[:120] or ident.display_name or account.nom_affiche
        account.email = user.email or ident.email or account.email
        account.derniere_connexion = now
        session.add(account)
        session.commit()
        session.refresh(account)
        return account

    # 2. Premiere connexion : correspondance sur une fiche salarie active unique selon l'attribut configure
    if ident.attribut == "sAMAccountName":
        if not ident.sam:
            return None
        matches = session.exec(
            select(User).where(
                func.lower(User.matricule) == ident.sam.lower(),
                User.statut == EmployeeStatus.actif,
            )
        ).all()
    elif ident.attribut == "userPrincipalName":
        lookup = ident.upn if ident.upn and "@" in ident.upn else None
        if not lookup:
            return None
        matches = session.exec(
            select(User).where(
                func.lower(User.email) == lookup.lower(),
                User.statut == EmployeeStatus.actif,
            )
        ).all()
    else:
        if not ident.email:
            return None
        matches = session.exec(
            select(User).where(
                func.lower(User.email) == ident.email.lower(),
                User.statut == EmployeeStatus.actif,
            )
        ).all()
    if len(matches) != 1:
        return None
    user = matches[0]

    # Conversion sans doublon d'un compte local demandeur existant
    existing = session.exec(select(Account).where(Account.user_id == user.id)).first()
    if existing is not None:
        if not existing.actif or existing.role != Role.demandeur:
            return None
        if existing.external_uid and existing.external_uid != ident.external_uid:
            return None
        existing.external_uid = ident.external_uid
        existing.source_auth = "ldap"
        existing.hashed_password = hash_password(secrets.token_urlsafe(48))
        existing.secours = False
        existing.portee_globale = False
        existing.must_change_password = False
        existing.token_epoch += 1
        existing.derniere_connexion = now
        _purger_jetons_reset(session, existing.id)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        audit(audit_actor(existing), "ldap_compte_lie", target=audit_actor(existing), detail="role : demandeur")
        return existing

    # Creation d'un nouveau compte demandeur LDAP
    preferred = (ident.email or ident.upn or ident.sam or "").strip().lower()
    candidate = preferred if USERNAME_RE.match(preferred) else ""
    if not candidate or session.exec(select(Account).where(func.lower(Account.username) == candidate)).first():
        candidate = "ldap-" + hashlib.sha256(ident.external_uid.encode("utf-8")).hexdigest()[:12]

    account = Account(
        username=candidate,
        role=Role.demandeur,
        actif=True,
        hashed_password=hash_password(secrets.token_urlsafe(48)),
        source_auth="ldap",
        external_uid=ident.external_uid,
        secours=False,
        portee_globale=False,
        user_id=user.id,
        nom_affiche=f"{user.prenom} {user.nom}".strip()[:120] or ident.display_name,
        email=user.email or ident.email,
        derniere_connexion=now,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    audit(audit_actor(account), "ldap_compte_cree", target=audit_actor(account), detail="role : demandeur")
    return account
