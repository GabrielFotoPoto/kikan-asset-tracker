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

"""Identite visuelle : icone de l'application (menu, page de connexion, onglet du navigateur).

Lecture PUBLIQUE (la page de connexion n'a pas de session) ; l'icone est l'unique image servie sans authentification. Elle
est deposee par l'informatique (Parametrage) et passe par la meme verification que le logo des PDF : PNG ou JPEG,
taille et dimensions bornees, relue puis reecrite en PNG (aucune metadonnee, aucun SVG)."""
import base64
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session

from ..db import get_session
from ..models import Setting

router = APIRouter(prefix="/branding", tags=["branding"])

ICON_KEY = "app_icone"


def icon_bytes(session: Session) -> bytes | None:
    row = session.get(Setting, ICON_KEY)
    return base64.b64decode(row.value) if row and row.value else None


@router.get("")
def branding(session: Session = Depends(get_session)):
    """Empreinte courte de l'icone (sert a rafraichir l'affichage) ou null si aucune icone n'est definie."""
    png = icon_bytes(session)
    return {"icone": hashlib.sha256(png).hexdigest()[:16] if png else None}


@router.get("/icone")
def icone(session: Session = Depends(get_session)):
    png = icon_bytes(session)
    if not png:
        raise HTTPException(404, "Aucune icone")
    return Response(content=png, media_type="image/png")
