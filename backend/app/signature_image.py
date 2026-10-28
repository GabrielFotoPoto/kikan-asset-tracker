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

"""Signature manuscrite a l'ecran : validation et assainissement de l'image recue.

L'image vient du navigateur : elle est traitee comme une donnee NON FIABLE. On verifie le
format reel (signature PNG), la taille, les dimensions AVANT decodage complet (protection contre
les bombes de decompression), on exige un trace reel, puis on RE-ENCODE une image propre
(sans metadonnees) recadree sur le trace.
"""
import base64
import binascii
import hashlib
import io
import os

from PIL import Image, ImageChops, UnidentifiedImageError

MAX_B64_CHARS = 600_000      # taille maximale de la chaine recue
MAX_BYTES = 400_000          # taille maximale de l'image decodee
MAX_W, MAX_H = 1200, 600     # dimensions maximales (pixels)
MIN_W, MIN_H = 100, 40       # dimensions minimales
MIN_INK_PIXELS = 150         # nombre minimal de pixels de trace
MIN_SPAN_PX = 40             # etendue minimale du trace dans au moins une dimension
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Signature manuscrite obligatoire par defaut (SPEC). KIKAN_SIGNATURE_MANUSCRITE_OBLIGATOIRE=false
# autorise une simple confirmation (methode "confirmation"), moins probante.
HANDWRITTEN_REQUIRED = os.environ.get("KIKAN_SIGNATURE_MANUSCRITE_OBLIGATOIRE", "true").strip().lower() \
    not in ("0", "false", "non", "no")


class SignatureImageError(ValueError):
    """Signature refusee (message affichable, sans donnee sensible)."""


def sanitize_signature_png(value: str) -> tuple[bytes, dict]:
    """Valide l'image (PNG en base64 ou data URL) et renvoie (png propre, meta)."""
    text = (value or "").strip()
    if text.startswith("data:"):
        head, _, text = text.partition(",")
        if not head.lower().startswith("data:image/png"):
            raise SignatureImageError("Format attendu : PNG")
    if not text:
        raise SignatureImageError("Signature manquante")
    if len(text) > MAX_B64_CHARS:
        raise SignatureImageError("Image de signature trop volumineuse")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SignatureImageError("Image de signature illisible") from exc
    if len(raw) > MAX_BYTES:
        raise SignatureImageError("Image de signature trop volumineuse")
    if raw[:8] != PNG_MAGIC:
        raise SignatureImageError("Format attendu : PNG")

    try:
        img = Image.open(io.BytesIO(raw))
        # Dimensions lues dans l'en-tete : refus AVANT tout decodage des pixels.
        width, height = img.size
        if img.format != "PNG":
            raise SignatureImageError("Format attendu : PNG")
        if width > MAX_W or height > MAX_H or width * height > MAX_W * MAX_H:
            raise SignatureImageError("Dimensions de la signature trop grandes")
        if width < MIN_W or height < MIN_H:
            raise SignatureImageError("Dimensions de la signature trop petites")
        img.load()
        img = img.convert("RGBA")
    except SignatureImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise SignatureImageError("Image de signature illisible") from exc

    # Pixels de trace : opaques (alpha > 40) et assez fonces (luminance < 200).
    alpha = img.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    dark = img.convert("L").point(lambda v: 255 if v < 200 else 0)
    ink = ImageChops.multiply(alpha, dark)
    bbox = ink.getbbox()
    ink_pixels = ink.histogram()[255]
    if bbox is None or ink_pixels < MIN_INK_PIXELS:
        raise SignatureImageError("Signature vide ou trop courte")
    if max(bbox[2] - bbox[0], bbox[3] - bbox[1]) < MIN_SPAN_PX:
        raise SignatureImageError("Signature vide ou trop courte")

    # Re-encodage propre, recadre sur le trace (marge de 10 px), sans metadonnees.
    margin = 10
    box = (max(bbox[0] - margin, 0), max(bbox[1] - margin, 0),
           min(bbox[2] + margin, width), min(bbox[3] + margin, height))
    cropped = img.crop(box)
    out = io.BytesIO()
    cropped.save(out, format="PNG", optimize=True)
    clean = out.getvalue()
    meta = {
        "sha256_source": hashlib.sha256(raw).hexdigest(),
        "sha256_pdf": hashlib.sha256(clean).hexdigest(),
        "largeur": cropped.size[0],
        "hauteur": cropped.size[1],
        "pixels_encre": ink_pixels,
        "octets": len(clean),
    }
    return clean, meta


def prepare_signature(consent: bool, image: str | None) -> tuple[bytes | None, dict, str]:
    """Regles communes remise / restitution. Renvoie (png|None, meta, methode)."""
    if not consent:
        raise SignatureImageError("L'acceptation du document est requise")
    if image:
        png, meta = sanitize_signature_png(image)
        return png, meta, "manuscrite_ecran"
    if HANDWRITTEN_REQUIRED:
        raise SignatureImageError("La signature manuscrite est obligatoire")
    return None, {}, "confirmation"
