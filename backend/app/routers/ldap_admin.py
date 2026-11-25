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

"""Administration du connecteur Active Directory local (LDAP / LDAPS), reserve au role informatique."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from .. import appsettings, ldap_auth
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..models import Account

router = APIRouter(
    prefix="/admin/ldap", tags=["ldap"],
    dependencies=[Depends(require_roles("informatique"))],
)


class LdapSettingsIn(BaseModel):
    actif: bool = False
    attribut: str = Field(default="mail", max_length=40)
    groupe_dn: str = Field(default="", max_length=500)


def _state(session: Session) -> dict:
    return {
        "config": ldap_auth.config_summary(),
        "reglages": ldap_auth.read_settings(session),
        "actif": ldap_auth.is_active(session),
    }


@router.get("")
def get_ldap_state(session: Session = Depends(get_session)):
    return _state(session)


@router.put("")
def update_ldap_settings(
    data: LdapSettingsIn,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    if data.attribut not in ldap_auth.ATTRIBUTS_AUTORISES:
        raise HTTPException(422, "Attribut de correspondance invalide (mail, userPrincipalName ou sAMAccountName)")
    if data.actif and not ldap_auth.configured():
        raise HTTPException(409, "Activation impossible : configuration LDAP incomplete dans l'environnement")
    before = ldap_auth.read_settings(session)
    groupe = data.groupe_dn.strip()
    appsettings.put(session, ldap_auth.KEY_ACTIF, "1" if data.actif else "0")
    appsettings.put(session, ldap_auth.KEY_ATTRIBUT, data.attribut)
    appsettings.put(session, ldap_auth.KEY_GROUPE_DN, groupe)
    session.commit()
    after = ldap_auth.read_settings(session)
    if after != before:
        audit(
            admin.username, "ldap_reglages",
            detail=f"actif={after['actif']} attribut={after['attribut']} groupe={'oui' if after['groupe_dn'] else 'non'}",
        )
    return _state(session)


@router.post("/test")
def test_ldap_connection():
    return ldap_auth.test_connection()
