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

"""Reglages du SSO et regles de connexion locale (separes de la mecanique OIDC de sso.py)."""
import json
import os
import time
from datetime import date

from sqlalchemy import func
from sqlmodel import Session, select

from . import appsettings, sso
from .models import Account, Role

KEYS = {
    "actif": "sso_actif", "mode_local": "sso_mode_local", "creation_auto": "sso_creation_auto",
    "exiger_mfa": "sso_exiger_mfa", "role_it": "sso_role_it", "role_rh": "sso_role_rh",
    "secret_expire": "sso_secret_expire", "ttl": "session_ttl_min", "test": "sso_test_ok",
}
MODES = ("autorise", "secours")
TTL_MIN, TTL_MAX = 30, 720
TEST_VALIDITY_SEC = 1800


def default_ttl() -> int:
    try:
        return max(TTL_MIN, min(TTL_MAX, int(os.environ.get("KIKAN_TOKEN_TTL_MIN", "240"))))
    except ValueError:
        return 240


def read(session: Session) -> dict:
    g = lambda k, d=None: appsettings.get(session, KEYS[k], d)  # noqa: E731
    try:
        ttl = int(g("ttl", ""))
    except ValueError:
        ttl = default_ttl()
    test = None
    try:
        test = json.loads(g("test", "") or "null")
    except ValueError:
        test = None
    return {
        "actif": g("actif", "0") == "1",
        "mode_local": g("mode_local", "secours") if g("mode_local", "secours") in MODES else "secours",
        "creation_auto": g("creation_auto", "1") == "1",
        "exiger_mfa": g("exiger_mfa", "1") == "1",
        "role_it": g("role_it", "Kikan.IT") or "Kikan.IT",
        "role_rh": g("role_rh", "Kikan.RH") or "Kikan.RH",
        "secret_expire": g("secret_expire", "") or "",
        "ttl": max(TTL_MIN, min(TTL_MAX, ttl)),
        "test": test,
    }


def is_active(session: Session) -> bool:
    """SSO utilisable : configure dans l'environnement ET active dans le parametrage."""
    return sso.configured() and read(session)["actif"]


def local_login_allowed(session: Session, account: Account) -> bool:
    """Connexion par mot de passe : toujours permise tant que le SSO est inactif ; sinon selon le mode."""
    if not is_active(session):
        return True
    if account.source_auth == "sso":
        return False  # compte cree par Microsoft 365 : pas de mot de passe
    return account.secours or read(session)["mode_local"] == "autorise"


def breakglass_count(session: Session, exclude_id: int | None = None) -> int:
    """Comptes informatique actifs, avec mot de passe local, autorises a se connecter en secours."""
    stmt = select(func.count()).select_from(Account).where(
        Account.role == Role.informatique, Account.actif == True,  # noqa: E712
        Account.secours == True, Account.source_auth == "local",  # noqa: E712
    )
    if exclude_id is not None:
        stmt = stmt.where(Account.id != exclude_id)
    return session.exec(stmt).one()


def activation_blockers(session: Session, admin_username: str) -> list[str]:
    """Raisons pour lesquelles le SSO ne peut pas etre active (liste vide : activation permise)."""
    out = []
    if not sso.configured():
        out.append("La configuration de l'environnement est incomplete : " + ", ".join(sso.config_summary()["manque"] or ["autorite"]))
    test = read(session)["test"]
    if not test or time.time() - test.get("ts", 0) > TEST_VALIDITY_SEC or test.get("par") != admin_username \
            or test.get("role") != Role.informatique.value:
        out.append("Aucun test de connexion reussi par vous dans les 30 dernieres minutes (avec un role informatique)")
    if breakglass_count(session) < 1:
        out.append("Aucun compte local de secours actif (role informatique, case 'secours', mot de passe local)")
    return out


def secret_expiry_warning(session: Session) -> str | None:
    raw = read(session)["secret_expire"]
    try:
        days = (date.fromisoformat(raw) - date.today()).days
    except ValueError:
        return None
    if days < 0:
        return "Le secret du client Microsoft a expire : la connexion SSO ne fonctionne plus"
    if days <= 30:
        return f"Le secret du client Microsoft expire dans {days} jour(s) : renouvelez-le dans Entra et dans .env"
    return None
