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

"""Gestion transversale des pieces jointes (lot G3, reutilisable pour C5).

Controle strict par octets magiques, re-encodage Pillow des images (retrait EXIF, plafond 25 MP),
quotas par fichier/entite/volume global (507 avant saturation d'/archive), et suivi RGPD dans purge_documents.
"""
from __future__ import annotations

import io
import os
import re
import threading
import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func
from sqlmodel import Session, select

from . import appsettings, filestore
from .audit import audit
from .auth import audit_actor
from .models import Account, Attachment, PurgeDocument, utcnow

MAX_FILES_PER_ENTITY = 5
MAX_IMAGE_PIXELS = 25_000_000
MIN_DISK_RESERVE_BYTES = 100 * 1024 * 1024  # 100 Mio reserves sur /archive pour ne jamais bloquer les PDF scelles

TAILLE_MAX_KEY = "pj_taille_max_mio"
TAILLE_MAX_DEFAUT_MIO = 5
TAILLE_MAX_MIN_MIO = 1
TAILLE_MAX_MAX_MIO = 10

PLAFOND_GLOBAL_KEY = "pj_plafond_global_mio"
PLAFOND_GLOBAL_DEFAUT_MIO = 2048  # 2 Gio
PLAFOND_GLOBAL_MIN_MIO = 10
PLAFOND_GLOBAL_MAX_MIO = 51200

_FORBIDDEN_EXTS = {
    ".svg", ".svgz", ".html", ".htm", ".xhtml", ".js", ".mjs", ".csv",
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".msi", ".jar",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".docm", ".xlsm", ".pptm",
}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")
_CTRL_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PIL_LOCK = threading.Lock()


def _int_setting(session: Session, key: str, default: int, lo: int, hi: int) -> int:
    raw = appsettings.get(session, key)
    if raw is not None and raw.isdigit():
        return max(lo, min(hi, int(raw)))
    return default


def taille_max_mio(session: Session) -> int:
    return _int_setting(session, TAILLE_MAX_KEY, TAILLE_MAX_DEFAUT_MIO, TAILLE_MAX_MIN_MIO, TAILLE_MAX_MAX_MIO)


def plafond_global_mio(session: Session) -> int:
    return _int_setting(
        session, PLAFOND_GLOBAL_KEY, PLAFOND_GLOBAL_DEFAUT_MIO,
        PLAFOND_GLOBAL_MIN_MIO, PLAFOND_GLOBAL_MAX_MIO,
    )


def volume_total_octets(session: Session) -> int:
    total = session.exec(select(func.coalesce(func.sum(Attachment.size_bytes), 0))).one()
    return int(total or 0)


def nettoyer_nom_affichage(filename: str | None, ext: str) -> str:
    base = os.path.basename((filename or "").replace("\\", "/")).strip()
    base = _SAFE_NAME_RE.sub("_", base).strip(". ")
    if not base:
        base = f"piece_jointe.{ext}"
    return base[:180]


def _reencoder_image(data: bytes, expected_fmt: str, mime: str, ext: str) -> tuple[bytes, str, str]:
    with _PIL_LOCK:
        old_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format != expected_fmt:
                    raise HTTPException(422, "Format d'image incoherent")
                w, h = img.size
                if w <= 0 or h <= 0 or (w * h) > MAX_IMAGE_PIXELS:
                    raise HTTPException(422, "Image trop grande (max 25 megapixels)")
                img = ImageOps.exif_transpose(img)
                out = io.BytesIO()
                if expected_fmt == "JPEG":
                    clean = img.convert("RGB")
                    clean.save(out, format="JPEG", quality=88, optimize=True)
                elif expected_fmt == "PNG":
                    clean = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
                    clean.save(out, format="PNG", optimize=True)
                else:
                    clean = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
                    clean.save(out, format="WEBP", quality=85)
                return out.getvalue(), mime, ext
        except HTTPException:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
            raise HTTPException(422, f"Image invalide ou refusee : {type(exc).__name__}") from exc
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit


def valider_et_preparer(filename: str | None, data: bytes, max_bytes: int) -> tuple[bytes, str, str, str]:
    """Controle taille, extension interdite, magic bytes et re-encodage Pillow.

    Retourne (bytes_finaux, mime_type, extension, display_name).
    """
    if not data:
        raise HTTPException(422, "Fichier vide")
    if len(data) > max_bytes:
        raise HTTPException(413, f"Fichier trop volumineux (max {max_bytes // (1024 * 1024)} Mio)")

    ext_orig = os.path.splitext((filename or "").strip().lower())[1]
    if ext_orig in _FORBIDDEN_EXTS:
        raise HTTPException(422, f"Format de fichier interdit ({ext_orig})")

    head = data[:16]
    # Images : octets magiques stricts + re-encodage Pillow (retire EXIF et polyglottes)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        final_bytes, mime, ext = _reencoder_image(data, "PNG", "image/png", "png")
    elif head.startswith(b"\xff\xd8\xff"):
        final_bytes, mime, ext = _reencoder_image(data, "JPEG", "image/jpeg", "jpg")
    elif len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        final_bytes, mime, ext = _reencoder_image(data, "WEBP", "image/webp", "webp")
    elif head.startswith(b"%PDF-") and ext_orig in ("", ".pdf"):
        final_bytes, mime, ext = data, "application/pdf", "pdf"
    elif ext_orig in (".txt", ".log"):
        if b"\x00" in data:
            raise HTTPException(422, "Fichier texte invalide (octet nul detecte)")
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "Fichier texte invalide (encodage UTF-8 requis)") from exc
        if _CTRL_TEXT_RE.search(decoded):
            raise HTTPException(422, "Fichier texte invalide (caracteres de controle interdits)")
        # Rejet defensif de contenu HTML/SVG deguise en .txt (avec retrait d'un eventuel BOM UTF-8)
        low = decoded.lstrip("\ufeff \t\r\n")[:64].lower()
        if low.startswith(("<svg", "<!doctype html", "<html", "<script")):
            raise HTTPException(422, "Contenu HTML/SVG interdit")
        final_bytes, mime, ext = data, "text/plain", ext_orig.lstrip(".")
    else:
        raise HTTPException(422, "Type de fichier non autorise (PNG, JPEG, WEBP, PDF, TXT ou LOG uniquement)")

    if len(final_bytes) > max_bytes:
        raise HTTPException(413, f"Fichier trop volumineux apres traitement (max {max_bytes // (1024 * 1024)} Mio)")

    return final_bytes, mime, ext, nettoyer_nom_affichage(filename, ext)


def lister_pieces_jointes(session: Session, entity_type: str, entity_id: int) -> list[Attachment]:
    return session.exec(
        select(Attachment)
        .where(Attachment.entity_type == entity_type, Attachment.entity_id == entity_id)
        .order_by(Attachment.cree_le, Attachment.id)
    ).all()


def ajouter_piece_jointe(
    session: Session,
    actor_account: Account,
    *,
    entity_type: str,
    entity_id: int,
    filename: str | None,
    data: bytes,
    target_audit: str,
) -> Attachment:
    existantes = lister_pieces_jointes(session, entity_type, entity_id)
    if len(existantes) >= MAX_FILES_PER_ENTITY:
        raise HTTPException(409, f"Quota atteint ({MAX_FILES_PER_ENTITY} pieces jointes maximum)")

    max_bytes = taille_max_mio(session) * 1024 * 1024
    final_bytes, mime, ext, display_name = valider_et_preparer(filename, data, max_bytes)

    # Controle plafond global PJ + espace libre sur /archive (507 avant de saturer le volume des PDF scelles)
    plafond_bytes = plafond_global_mio(session) * 1024 * 1024
    actuel = volume_total_octets(session)
    if actuel + len(final_bytes) > plafond_bytes:
        raise HTTPException(507, "Plafond global de stockage des pieces jointes atteint")
    free_bytes = filestore.archive_disk_free_bytes()
    if free_bytes is not None and (free_bytes - len(final_bytes)) < MIN_DISK_RESERVE_BYTES:
        raise HTTPException(507, "Espace disque insuffisant sur le volume de stockage")

    now = utcnow()
    key = f"pieces-jointes/{now.year}/{uuid.uuid4().hex}.{ext}"
    digest = filestore.sha256_hex(final_bytes)
    storage_ref = filestore.store_attachment(key, final_bytes, {"type": "PieceJointe", "annee": str(now.year)})

    att = Attachment(
        entity_type=entity_type,
        entity_id=entity_id,
        storage_ref=storage_ref,
        sha256=digest,
        mime_type=mime,
        size_bytes=len(final_bytes),
        display_name=display_name,
        uploaded_by_account_id=actor_account.id,
        cree_le=now,
    )
    session.add(att)
    session.commit()
    session.refresh(att)
    audit(audit_actor(actor_account), "pj_ajout", target=target_audit, detail=f"mime={mime} size={len(final_bytes)}")
    return att


def supprimer_piece_jointe(session: Session, actor_account: Account, att: Attachment, target_audit: str) -> None:
    ref = att.storage_ref
    digest = att.sha256
    session.delete(att)
    session.commit()
    if not filestore.delete_attachment(ref):
        # Si le partage distant est indisponible, on conserve une trace de purge pour eviter un fichier orphelin.
        try:
            moteur = filestore.parse_reference(ref)[0]
        except filestore.StorageError:
            moteur = "inconnu"
        statut = "ged_a_supprimer" if moteur in filestore.DOCUMENT_ONLY else "a_deplacer"
        session.add(PurgeDocument(
            reference=ref, moteur=moteur, statut=statut, type_doc="piece_jointe",
            empreinte=digest, echeance=date.today(),
        ))
        session.commit()
    audit(audit_actor(actor_account), "pj_suppression", target=target_audit, detail=f"sha256={digest}")


def planifier_purge_attachments(
    session: Session,
    entity_type: str,
    entity_id: int,
    echeance: date,
) -> int:
    """Supprime les lignes Attachment et enregistre leur quarantaine/suppression dans purge_documents."""
    rows = lister_pieces_jointes(session, entity_type, entity_id)
    count = 0
    for att in rows:
        try:
            moteur = filestore.parse_reference(att.storage_ref)[0]
        except filestore.StorageError:
            moteur = "inconnu"
        statut = "ged_a_supprimer" if moteur in filestore.DOCUMENT_ONLY else "a_deplacer"
        session.add(PurgeDocument(
            reference=att.storage_ref,
            moteur=moteur,
            statut=statut,
            type_doc="piece_jointe",
            empreinte=att.sha256,
            echeance=echeance,
        ))
        session.delete(att)
        count += 1
    return count
