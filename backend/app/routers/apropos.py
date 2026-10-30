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

"""A propos : version, licence, auteur et composants (lecture, tous roles authentifies)."""
import os
import platform
from importlib.metadata import PackageNotFoundError, version as pkg_version

from fastapi import APIRouter, Depends

from ..auth import get_current_account
from ..config import settings

router = APIRouter(
    prefix="/apropos", tags=["meta"],
    dependencies=[Depends(get_current_account)],
)

DEPOT = "https://github.com/GabrielFotoPoto/kikan-asset-tracker"

# Composants principaux : (nom, role, licence, paquet Python dont on lit la version installee ou None).
# Les licences sont celles declarees par chaque projet (relevees dans l'image) ; a revoir quand une dependance change.
COMPOSANTS = [
    ("FastAPI", "Interface de programmation (API)", "MIT", "fastapi"),
    ("SQLModel", "Modeles de donnees", "MIT", "sqlmodel"),
    ("SQLAlchemy", "Acces a la base de donnees", "MIT", "SQLAlchemy"),
    ("Alembic", "Migrations de la base", "MIT", "alembic"),
    ("Pydantic", "Validation des donnees", "MIT", "pydantic"),
    ("Uvicorn", "Serveur d'application", "BSD-3-Clause", "uvicorn"),
    ("ReportLab", "Generation des PDF", "BSD-3-Clause", "reportlab"),
    ("pyHanko", "Scellement PAdES des PDF", "MIT", "pyhanko"),
    ("pypdf", "Lecture et assemblage de PDF", "BSD-3-Clause", "pypdf"),
    ("Pillow", "Traitement des images", "MIT-CMU", "pillow"),
    ("cryptography", "Chiffrement et certificats", "Apache-2.0 ou BSD-3-Clause", "cryptography"),
    ("openpyxl", "Import et export Excel", "MIT", "openpyxl"),
    ("PyJWT", "Jetons de connexion", "MIT", "PyJWT"),
    ("bcrypt", "Hachage des mots de passe", "Apache-2.0", "bcrypt"),
    ("psycopg2", "Pilote PostgreSQL", "LGPL avec exceptions", "psycopg2-binary"),
    ("smbprotocol", "Stockage sur partage SMB", "MIT", "smbprotocol"),
    ("PostgreSQL", "Base de donnees", "PostgreSQL License", None),
    ("nginx", "Serveur web et HTTPS", "BSD-2-Clause", None),
    ("LibreOffice", "Conversion des chartes Word", "MPL-2.0", None),
    ("age", "Chiffrement des sauvegardes", "BSD-3-Clause", None),
    ("React", "Interface utilisateur", "MIT", None),
    ("React Router", "Navigation de l'interface", "MIT", None),
    ("Vite", "Compilation de l'interface", "MIT", None),
]


def _version(paquet: str | None) -> str | None:
    if not paquet:
        return None
    try:
        return pkg_version(paquet)
    except PackageNotFoundError:
        return None


@router.get("")
def a_propos():
    ver = os.environ.get("KIKAN_VERSION", "dev").lstrip("v") or "dev"
    dev = ver == "dev"
    return {
        "application": settings.app_name,
        "version": ver,
        "developpement": dev,
        "date_publication": (os.environ.get("KIKAN_RELEASE_DATE", "").strip() or None) if not dev else None,
        "python": platform.python_version(),
        "licence": {"nom": "GNU General Public License v3.0 ou ulterieure", "spdx": "GPL-3.0-or-later",
                    "texte": f"{DEPOT}/blob/main/LICENSE"},
        "auteur": "Gabriel Chollet",
        "copyright": "Copyright (C) 2026 Gabriel Chollet",
        "ia": "Developpe avec l'assistance d'une IA (Claude, Anthropic).",
        "liens": {
            "depot": DEPOT,
            "problemes": f"{DEPOT}/issues",
            "journal": f"{DEPOT}/blob/main/CHANGELOG.md",
            "version": None if dev else f"{DEPOT}/releases/tag/v{ver}",
        },
        "composants": [{"nom": n, "role": r, "licence": lic, "version": _version(p)} for n, r, lic, p in COMPOSANTS],
    }
