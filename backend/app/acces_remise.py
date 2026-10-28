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

"""Acces applicatifs dans l'accusé de remise : réglage, instantané et empreinte.

L'instantané ne contient que les acces ACCORDES sur des applications ACTIVES. Il est calcule au moment de la
signature (jamais fourni par le client) ; l'ecran de signature transmet l'empreinte de la liste qu'il a affichee,
ce qui garantit que le salarié signe exactement ce qu'il a vu.
"""
import hashlib
import json

from sqlmodel import Session, select

from .models import Application, Setting, UserApplication

KEY = "remise_inclure_acces"


def include_access(session: Session) -> bool:
    row = session.get(Setting, KEY)
    return bool(row and row.value == "1")


def set_include_access(session: Session, value: bool) -> None:
    row = session.get(Setting, KEY)
    if row:
        row.value = "1" if value else "0"
    else:
        row = Setting(key=KEY, value="1" if value else "0")
    session.add(row)


def snapshot(session: Session, user_id: int) -> list[dict]:
    """Acces accordes (applications actives), tries par nom : [{application, niveau}]."""
    apps = {a.id: a for a in session.exec(select(Application)).all()}
    rows = session.exec(
        select(UserApplication).where(UserApplication.user_id == user_id, UserApplication.acces == True)  # noqa: E712
    ).all()
    items = [
        {"application": apps[r.application_id].nom, "niveau": (r.note or "").strip()}
        for r in rows if r.application_id in apps and apps[r.application_id].actif
    ]
    return sorted(items, key=lambda i: (i["application"].lower(), i["niveau"]))


def fingerprint(items: list[dict]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def recap_view(session: Session, user_id: int) -> dict | None:
    """Pour l'ecran de signature : None si le reglage est desactive."""
    if not include_access(session):
        return None
    items = snapshot(session, user_id)
    return {"liste": items, "empreinte": fingerprint(items)}
