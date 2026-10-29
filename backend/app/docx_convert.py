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

"""Conversion d'un document Word (.docx) en PDF via le service isole 'converter' (LibreOffice).

L'API ne lit jamais le contenu du document : elle verifie sa structure (archive saine, pas de bombe de
decompression), le transmet au service sans acces reseau, et ne recupere qu'un PDF, qui est ensuite
reconstruit comme tout autre PDF depose (voir charte.normalize_pdf).
"""
import io
import os
import urllib.error
import urllib.request
import zipfile

from .charte import CharteError

CONVERTER_URL = os.environ.get("KIKAN_WORD_CONVERTER_URL", "").rstrip("/")
MAX_ENTRIES = 2000
MAX_UNCOMPRESSED = 150 * 1024 * 1024
UNAVAILABLE = ("La conversion des documents Word est indisponible : exportez la charte en PDF depuis Word "
               "(Fichier, Enregistrer sous, PDF) ou demandez a l'administrateur de demarrer le service de conversion.")


def check_docx(raw: bytes) -> None:
    """Structure d'un .docx valide, sans bombe de decompression ni macros."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        raise CharteError("Document Word illisible ou corrompu.") from exc
    if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise CharteError("Document Word refuse (archive anormalement volumineuse).")
    names = {i.filename for i in infos}
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise CharteError("Ce fichier n'est pas un document Word (.docx).")
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise CharteError("Les documents contenant des macros sont refuses : enregistrez-les en .docx sans macro.")


def docx_to_pdf(raw: bytes) -> bytes:
    check_docx(raw)
    if not CONVERTER_URL:
        raise CharteError(UNAVAILABLE)
    req = urllib.request.Request(CONVERTER_URL + "/convert", data=raw, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        # Faux positif B310 : CONVERTER_URL est une adresse interne fixee par l'administrateur (service de conversion de la pile Docker).
        with urllib.request.urlopen(req, timeout=100) as resp:  # nosec B310
            pdf = resp.read(60 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            raise CharteError("Ce document Word n'a pas pu etre converti : verifiez qu'il s'ouvre dans Word, "
                              "ou exportez-le en PDF.") from exc
        if exc.code == 504:
            raise CharteError("La conversion du document Word a pris trop de temps : exportez-le en PDF.") from exc
        raise CharteError(UNAVAILABLE) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise CharteError(UNAVAILABLE) from exc
    if pdf[:5] != b"%PDF-" or len(pdf) > 60 * 1024 * 1024:
        raise CharteError("Conversion du document Word invalide.")
    return pdf
