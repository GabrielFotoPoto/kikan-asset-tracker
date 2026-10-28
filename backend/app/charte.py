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

"""Chartes informatiques deposees : validation, normalisation en PDF, rendu des pages, annexe.

Le fichier depose est une donnee NON FIABLE. Il est toujours reconstruit en un PDF propre (pages seules,
sans annotations ni actions) avant d'etre stocke ; seul ce PDF normalise est annexe aux documents signes.
Le fichier d'origine est conserve tel quel pour archivage mais n'est jamais interprete ailleurs que
dans la normalisation.
"""
import io
import os
import re
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate
from sqlmodel import Session, select

from .models import Entite, Policy

MAX_BYTES = int(os.environ.get("KIKAN_MAX_CHARTE_MB", "10")) * 1024 * 1024
MAX_PAGES = 60
MAX_MARKDOWN_CHARS = 200_000
FORMAT_HELP = "deposez un PDF, un document Word (.docx) ou un fichier Markdown (.md)."


class CharteError(ValueError):
    """Fichier de charte refuse (message affichable)."""


def detect_format(filename: str, raw: bytes) -> str:
    """Format deduit du CONTENU (l'extension ne sert qu'a reconnaitre le texte Markdown)."""
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        return "docx"
    if raw[:2] == b"MZ" or raw[:4] == b"\x7fELF" or b"\x00" in raw[:4096]:
        raise CharteError("Format non pris en charge : " + FORMAT_HELP)
    if (filename or "").lower().endswith((".md", ".markdown", ".txt")):
        return "markdown"
    raise CharteError("Format non reconnu : " + FORMAT_HELP)


# --- PDF ---

def normalize_pdf(raw: bytes, title: str) -> tuple[bytes, int]:
    """Reconstruit un PDF propre : pages seules, sans annotations, liens ni actions."""
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise CharteError("Le PDF est protege par mot de passe : deposez une version non chiffree.")
        n = len(reader.pages)
        if n < 1:
            raise CharteError("Le PDF ne contient aucune page.")
        if n > MAX_PAGES:
            raise CharteError(f"Le PDF compte trop de pages (maximum {MAX_PAGES}).")
        writer = PdfWriter()
        for page in reader.pages:
            for key in ("/Annots", "/AA", "/B"):
                if key in page:
                    del page[key]
            writer.add_page(page)
        writer.add_metadata({"/Title": title})
        out = io.BytesIO()
        writer.write(out)
    except CharteError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, RecursionError, OSError) as exc:
        raise CharteError("PDF illisible ou corrompu.") from exc
    data = out.getvalue()
    check_renders(data, n)
    return data, n


def check_renders(pdf: bytes, expected_pages: int) -> None:
    """Controle independant : un second moteur doit ouvrir le PDF et en dessiner la premiere page."""
    try:
        doc = pdfium.PdfDocument(pdf)
        try:
            if len(doc) != expected_pages:
                raise CharteError("PDF incoherent (nombre de pages).")
            page = doc[0]
            page.render(scale=0.2).to_pil().close()
            page.close()
        finally:
            doc.close()
    except CharteError:
        raise
    except Exception as exc:  # noqa: BLE001  (pdfium leve plusieurs types d'erreurs)
        raise CharteError("PDF illisible ou corrompu.") from exc


def render_page_png(pdf: bytes, index: int, max_side: int = 1100) -> bytes:
    """Page rendue en PNG (taille bornee), pour l'apercu a l'ecran."""
    doc = pdfium.PdfDocument(pdf)
    try:
        if index < 0 or index >= len(doc):
            raise IndexError(index)
        page = doc[index]
        w, h = page.get_size()
        scale = min(max_side / max(w, h), 3.0)
        img = page.render(scale=scale).to_pil().convert("RGB")
        page.close()
    finally:
        doc.close()
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# --- Markdown ---

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")


def _inline(text: str) -> str:
    """Echappe tout le texte, puis n'autorise que gras et italique (aucune balise deposee n'est conservee)."""
    t = escape(text)
    t = _BOLD.sub(r"<b>\1</b>", t)
    return _ITALIC.sub(r"<i>\1</i>", t)


def markdown_to_pdf(raw: bytes, title: str) -> tuple[bytes, int]:
    """Markdown restreint : titres (#), listes (- ou 1.), paragraphes, **gras**, *italique*."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CharteError("Le fichier Markdown doit etre encode en UTF-8.") from exc
    if len(text) > MAX_MARKDOWN_CHARS:
        raise CharteError("Le fichier Markdown est trop volumineux.")
    if not text.strip():
        raise CharteError("Le fichier est vide.")

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=4)
    heads = {1: styles["Heading1"], 2: styles["Heading2"], 3: styles["Heading3"]}
    story = []
    para: list[str] = []
    items: list[str] = []
    ordered = False

    def flush_para():
        if para:
            story.append(Paragraph(_inline(" ".join(para)), body))
            para.clear()

    def flush_list():
        nonlocal ordered
        if items:
            story.append(ListFlowable([ListItem(Paragraph(_inline(i), body)) for i in items],
                                      bulletType="1" if ordered else "bullet", leftIndent=14))
            items.clear()
        ordered = False

    for line in text.splitlines():
        s = line.strip()
        m_h = re.match(r"^(#{1,6})\s+(.*)$", s)
        m_b = re.match(r"^[-*+]\s+(.*)$", s)
        m_n = re.match(r"^\d+[.)]\s+(.*)$", s)
        if not s:
            flush_para()
            flush_list()
        elif m_h:
            flush_para()
            flush_list()
            story.append(Paragraph(_inline(m_h.group(2)), heads[min(len(m_h.group(1)), 3)]))
        elif m_b or m_n:
            flush_para()
            if items and ordered != bool(m_n):
                flush_list()
            ordered = bool(m_n)
            items.append((m_b or m_n).group(1))
        else:
            flush_list()
            para.append(s)
    flush_para()
    flush_list()

    out = io.BytesIO()
    SimpleDocTemplate(out, pagesize=A4, title=title, leftMargin=22 * mm, rightMargin=22 * mm,
                      topMargin=20 * mm, bottomMargin=20 * mm).build(story)
    return normalize_pdf(out.getvalue(), title)


def normalize(filename: str, raw: bytes, title: str) -> tuple[str, bytes, int]:
    """(format_source, pdf_normalise, nb_pages), ou CharteError."""
    if not raw:
        raise CharteError("Le fichier est vide.")
    if len(raw) > MAX_BYTES:
        raise CharteError(f"Fichier trop volumineux (maximum {MAX_BYTES // 1024 // 1024} Mo).")
    fmt = detect_format(filename, raw)
    if fmt == "pdf":
        pdf, n = normalize_pdf(raw, title)
    elif fmt == "markdown":
        pdf, n = markdown_to_pdf(raw, title)
    else:
        raise CharteError("Les documents Word ne sont pas encore pris en charge : exportez-les en PDF.")
    return fmt, pdf, n


# --- Portee et annexe ---

def _scope(stmt, entite_id: int | None):
    if entite_id is not None:
        return stmt.where(Policy.entite_id == entite_id)
    return stmt.where(Policy.entite_id.is_(None))


def _active(session: Session, entite_id: int | None) -> Policy | None:
    stmt = select(Policy).where(Policy.statut == "active", Policy.fichier_ref.is_not(None))
    return session.exec(_scope(stmt, entite_id)).first()


def resolve_policy(session: Session, entite_id: int | None) -> Policy | None:
    """Charte applicable : celle de l'entite, sinon celle de ses entites parentes, sinon la charte globale."""
    seen: set[int] = set()
    current = entite_id
    while current is not None and current not in seen:
        seen.add(current)
        policy = _active(session, current)
        if policy:
            return policy
        ent = session.get(Entite, current)
        parent = None
        if ent and ent.code_parent:
            parent = session.exec(select(Entite).where(Entite.code == ent.code_parent)).first()
        current = parent.id if parent else None
    return _active(session, None)


def append_annex(receipt_pdf: bytes, charte_pdf: bytes) -> bytes:
    """Accuse de remise suivi des pages de la charte (avant scellement)."""
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(receipt_pdf)))
    writer.append(PdfReader(io.BytesIO(charte_pdf)))
    writer.add_metadata({"/Title": "Accuse de remise de materiel et charte informatique"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def next_version(session: Session, entite_id: int | None) -> str:
    nums = []
    for p in session.exec(_scope(select(Policy), entite_id)).all():
        m = re.fullmatch(r"v(\d+)", p.version or "")
        if m:
            nums.append(int(m.group(1)))
    return f"v{(max(nums) if nums else 0) + 1}"
