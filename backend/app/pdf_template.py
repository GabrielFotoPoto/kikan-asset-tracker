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

"""Modele de PDF : organisation, logo, mentions legales et pied de page.

Le logo est une image NON FIABLE : format verifie par son contenu, taille et dimensions bornees avant
decodage (bombes de decompression), puis ré-encodee en PNG propre (sans metadonnees). Les textes sont
echappes avant d'etre inseres dans un PDF. Le modele utilise est fige dans chaque document signe ;
son empreinte est enregistree avec la signature.
"""
import base64
import binascii
import hashlib
import io
import json
from xml.sax.saxutils import escape

from PIL import Image, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from sqlmodel import Session

from .models import Setting

TEXT_KEYS = {"organisation": "pdf_organisation", "mentions": "pdf_mentions", "pied": "pdf_pied"}
LOGO_KEY = "pdf_logo"
MAX_LEN = {"organisation": 120, "mentions": 1500, "pied": 300}

MAX_B64_CHARS = 450_000
MAX_BYTES = 300_000
MAX_W, MAX_H = 1000, 400
MIN_SIDE = 16
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class LogoError(ValueError):
    """Logo refuse (message affichable)."""


def sanitize_logo(value: str) -> tuple[bytes, dict]:
    """PNG ou JPEG depose -> PNG propre, plus ses caracteristiques."""
    if not value or len(value) > MAX_B64_CHARS:
        raise LogoError("Image trop volumineuse (300 Ko maximum)")
    payload = value
    if value.startswith("data:"):
        head, _, payload = value.partition(",")
        if not head.startswith(("data:image/png", "data:image/jpeg")) or ";base64" not in head:
            raise LogoError("Format attendu : PNG ou JPEG")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LogoError("Image illisible") from exc
    if len(raw) > MAX_BYTES:
        raise LogoError("Image trop volumineuse (300 Ko maximum)")
    if raw[:8] == PNG_MAGIC:
        kind = "PNG"
    elif raw[:3] == b"\xff\xd8\xff":
        kind = "JPEG"
    else:
        raise LogoError("Format attendu : PNG ou JPEG")
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format != kind:
            raise LogoError("Image illisible")
        width, height = im.size  # lu dans l'en-tete, avant tout decodage des pixels
        if width > MAX_W or height > MAX_H:
            raise LogoError(f"Dimensions trop grandes (maximum {MAX_W} x {MAX_H} pixels)")
        if width < MIN_SIDE or height < MIN_SIDE:
            raise LogoError("Dimensions trop petites")
        im.load()
        im = im.convert("RGBA")
    except LogoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise LogoError("Image illisible") from exc
    clean = Image.new("RGBA", im.size)
    clean.paste(im)
    out = io.BytesIO()
    clean.save(out, "PNG", optimize=True)
    data = out.getvalue()
    if len(data) > 600_000:
        raise LogoError("Image trop volumineuse apres traitement")
    return data, {"largeur": width, "hauteur": height, "octets": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def load_template(session: Session) -> dict:
    """Modele courant : textes, logo (octets PNG ou None) et empreinte globale."""
    values = {}
    for name, key in TEXT_KEYS.items():
        row = session.get(Setting, key)
        values[name] = (row.value if row and row.value else "").strip()
    row = session.get(Setting, LOGO_KEY)
    logo = base64.b64decode(row.value) if row and row.value else None
    digest = hashlib.sha256(json.dumps(
        {**values, "logo": hashlib.sha256(logo).hexdigest() if logo else None}, sort_keys=True).encode()).hexdigest()
    return {**values, "logo": logo, "sha256": digest,
            "vide": not any(values.values()) and not logo}


def public_view(template: dict) -> dict:
    """Description sans le logo lui-meme."""
    return {**{k: template[k] for k in TEXT_KEYS}, "logo": bool(template["logo"]), "sha256": template["sha256"]}


# --- Elements de mise en page (PDF) ---

def header_flowables(template: dict | None, styles) -> list:
    """Logo et nom de l'organisation en tete de document."""
    if not template or (not template.get("logo") and not template.get("organisation")):
        return []
    cells = []
    if template.get("logo"):
        with Image.open(io.BytesIO(template["logo"])) as im:
            w_px, h_px = im.size
        scale = min(45 * mm / w_px, 18 * mm / h_px)
        cells.append(RLImage(io.BytesIO(template["logo"]), width=w_px * scale, height=h_px * scale))
    org_style = ParagraphStyle("org", parent=styles["Normal"], fontSize=11, leading=14)
    if template.get("organisation"):
        cells.append(Paragraph("<b>" + escape(template["organisation"]) + "</b>", org_style))
    table = Table([cells], colWidths=[None] * len(cells), hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
    return [table, Spacer(1, 4 * mm)]


def mentions_flowables(template: dict | None, styles) -> list:
    """Mentions legales en petits caracteres, apres le contenu."""
    if not template or not template.get("mentions"):
        return []
    style = ParagraphStyle("mentions", parent=styles["Normal"], fontSize=7.5, leading=10, textColor=colors.HexColor("#555555"))
    lines = [Paragraph(escape(line), style) for line in template["mentions"].splitlines() if line.strip()]
    return [Spacer(1, 8 * mm), *lines]


def footer_callback(template: dict | None, pagesize=A4):
    """Pied de page (une ligne centree), dessine sur chaque page du document."""
    pied = (template or {}).get("pied")
    if not pied:
        return None

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(pagesize[0] / 2, 10 * mm, pied[:200])
        canvas.restoreState()

    return draw
