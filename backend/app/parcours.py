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

"""Assistants partages des parcours guides en etapes (arrivee, depart)."""
from datetime import datetime


def _etape(cle: str, titre: str, qui: str, etat: str, detail: str, **extra) -> dict:
    res = {"cle": cle, "titre": titre, "qui": qui, "etat": etat, "detail": detail}
    for k, v in extra.items():
        if v is not None:
            res[k] = v
    return res


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None
