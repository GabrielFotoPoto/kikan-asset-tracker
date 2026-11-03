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

"""A propos : version, licence, auteur, composants (lecture, tous roles authentifies) et verification des mises a jour (informatique)."""
import json
import os
import platform
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from importlib.metadata import PackageNotFoundError, version as pkg_version

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_account, require_roles
from ..config import settings

router = APIRouter(
    prefix="/apropos", tags=["meta"],
    dependencies=[Depends(get_current_account)],
)

DEPOT = "https://github.com/GabrielFotoPoto/kikan-asset-tracker"
API_RELEASE_DEFAUT = "https://api.github.com/repos/GabrielFotoPoto/kikan-asset-tracker/releases/latest"
CACHE_TTL_SEC = 6 * 3600
ERROR_TTL_SEC = 300
FORCE_MIN_INTERVAL_SEC = 60
LOOPBACK = {"127.0.0.1", "localhost", "[::1]"}
_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")

_maj_lock = threading.Lock()
_maj_cache: dict = {"ts": 0.0, "version_locale": None, "data": None}

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
        "ia": "Developpe avec l'assistance d'IA (Claude, Anthropic ; relectures avec Gemini, Google).",
        "liens": {
            "depot": DEPOT,
            "problemes": f"{DEPOT}/issues",
            "journal": f"{DEPOT}/blob/main/CHANGELOG.md",
            "version": None if dev else f"{DEPOT}/releases/tag/v{ver}",
        },
        "composants": [{"nom": n, "role": r, "licence": lic, "version": _version(p)} for n, r, lic, p in COMPOSANTS],
    }


def _parse_semver(v: str | None) -> tuple[int, int, int, int, str] | None:
    """Transforme '0.5.0' ou 'v0.5.0-rc.1' en tuple comparable (majeur, mineur, correctif, est_finale, preversion)."""
    if not v:
        return None
    m = _SEMVER_RE.match(v.strip())
    if not m:
        return None
    maj, min_, pat, pre = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or ""
    # Une version finale (sans preversion) est superieure a sa preversion (ex. 0.5.0 > 0.5.0-rc.1).
    return (maj, min_, pat, 1 if not pre else 0, pre)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _interroger_github() -> dict:
    url = os.environ.get("KIKAN_UPDATE_CHECK_URL", API_RELEASE_DEFAUT).strip() or API_RELEASE_DEFAUT
    parsed = urllib.parse.urlparse(url)
    is_prod = os.environ.get("KIKAN_ENV", "development").lower() == "production"
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in LOOPBACK and not is_prod):
        raise ValueError("adresse de verification non HTTPS")
    ca = (os.environ.get("KIKAN_UPDATE_CA_BUNDLE") or os.environ.get("KIKAN_SSO_CA_BUNDLE") or "").strip() or None
    proxy = (os.environ.get("KIKAN_UPDATE_PROXY") or os.environ.get("KIKAN_SSO_PROXY") or "").strip()
    ctx = ssl.create_default_context(cafile=ca)
    opener = urllib.request.build_opener(
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}),
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Kikan-Update-Checker"},
    )
    with opener.open(req, timeout=5) as resp:
        raw = resp.read(262_144 + 1)
    if len(raw) > 262_144:
        raise ValueError("reponse trop volumineuse")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("reponse inattendue")
    return data


def reset_update_cache() -> None:
    with _maj_lock:
        _maj_cache.update(ts=0.0, version_locale=None, data=None)


@router.get("/mise-a-jour", dependencies=[Depends(require_roles("informatique"))])
def verifier_mise_a_jour(forcer: bool = Query(False)):
    ver = os.environ.get("KIKAN_VERSION", "dev").lstrip("v") or "dev"
    dev = ver == "dev"
    active = os.environ.get("KIKAN_UPDATE_CHECK", "true").strip().lower() not in ("0", "false", "no", "off")
    base = {
        "verification_active": active,
        "version_actuelle": ver,
        "developpement": dev,
        "derniere_version": None,
        "disponible": False,
        "date_publication": None,
        "url_release": f"{DEPOT}/releases",
        "erreur": None,
    }
    if not active:
        return base

    now = time.time()
    with _maj_lock:
        cached = _maj_cache["data"]
        age = now - _maj_cache["ts"]
        same_ver = _maj_cache["version_locale"] == ver
        if cached is not None and same_ver:
            ttl = ERROR_TTL_SEC if cached.get("erreur") else CACHE_TTL_SEC
            if not forcer and age < ttl:
                return cached
            if forcer and age < FORCE_MIN_INTERVAL_SEC:
                return cached

    try:
        rel = _interroger_github()
        tag = str(rel.get("tag_name") or "").strip().lstrip("v")
        v_dist = _parse_semver(tag)
        if not v_dist:
            raise ValueError("numero de version distant invalide")
        v_loc = _parse_semver(ver)
        dispo = bool(v_loc and v_dist > v_loc)
        pub = str(rel.get("published_at") or "").strip()
        date_pub = pub[:10] if len(pub) >= 10 else None
        html_url = str(rel.get("html_url") or "").strip()
        if not html_url.startswith("https://github.com/"):
            html_url = f"{DEPOT}/releases/tag/v{tag}"
        res = {
            **base,
            "derniere_version": tag,
            "disponible": dispo,
            "date_publication": date_pub,
            "url_release": html_url,
        }
    except (urllib.error.URLError, OSError, ssl.SSLError, ValueError) as exc:
        res = {**base, "erreur": f"Verification impossible ({type(exc).__name__})."}

    with _maj_lock:
        _maj_cache.update(ts=time.time(), version_locale=ver, data=res)
    return res

