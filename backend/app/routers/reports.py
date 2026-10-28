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

"""Reporting : detentions a l'instant T, export CSV et PDF."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import xlsx_io
from ..pdf_template import footer_callback, header_flowables, load_template, mentions_flowables
from sqlmodel import Session, select

from ..auth import get_current_account
from ..db import get_session
from ..models import Asset, AssetStatus, Assignment, AssignmentAsset, Entite, User

router = APIRouter(
    prefix="/reports", tags=["reports"],
    dependencies=[Depends(get_current_account)],
)

COLUMNS = [
    ("entite", "Entite"),
    ("service", "Service"),
    ("matricule", "Matricule"),
    ("nom", "Nom"),
    ("prenom", "Prenom"),
    ("statut_salarie", "Statut"),
    ("type", "Type"),
    ("marque", "Marque"),
    ("modele", "Modele"),
    ("numero_serie", "N serie"),
    ("identifiant_interne", "Id interne"),
    ("date_remise", "Remise"),
]


def _rows(session: Session, entite_id: int | None, service: str | None) -> list[dict]:
    encours = {a.id: a for a in session.exec(
        select(Assignment).where(Assignment.statut == "en_cours")).all()}
    asset_to_assignment = {}
    for link in session.exec(select(AssignmentAsset)).all():
        if link.assignment_id in encours:
            asset_to_assignment[link.asset_id] = encours[link.assignment_id]

    entites = {e.id: e for e in session.exec(select(Entite)).all()}
    rows = []
    for asset in session.exec(select(Asset).where(Asset.statut == AssetStatus.affecte)).all():
        assignment = asset_to_assignment.get(asset.id)
        if not assignment:
            continue
        user = session.get(User, assignment.user_id)
        if not user:
            continue
        if entite_id is not None and user.entite_id != entite_id:
            continue
        if service and (user.service or "") != service:
            continue
        rows.append({
            "entite": entites[user.entite_id].nom if user.entite_id in entites else "",
            "service": user.service or "",
            "matricule": user.matricule or "",
            "nom": user.nom,
            "prenom": user.prenom,
            "statut_salarie": user.statut.value if hasattr(user.statut, "value") else user.statut,
            "type": asset.type or "",
            "marque": asset.marque or "",
            "modele": asset.modele or "",
            "numero_serie": asset.numero_serie or "",
            "identifiant_interne": asset.identifiant_interne or "",
            "date_remise": assignment.date_remise.strftime("%Y-%m-%d") if assignment.date_remise else "",
        })
    rows.sort(key=lambda r: (r["entite"], r["nom"], r["prenom"]))
    return rows


def _safe_cell(value) -> str:
    """Neutralise l'injection de formules : un tableur interprete =, +, -, @ en debut de cellule."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([label for _, label in COLUMNS])
    for r in rows:
        writer.writerow([_safe_cell(r[key]) for key, _ in COLUMNS])
    # BOM UTF-8 pour une ouverture correcte dans Excel FR.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _pdf(rows: list[dict], jour: str, template: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title="Detentions de materiel")
    styles = getSampleStyleSheet()
    story = [
        *header_flowables(template, styles),
        Paragraph("Detentions de materiel par salarie", styles["Title"]),
        Paragraph(f"Edite le {jour} - {len(rows)} ligne(s)", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]
    data = [[label for _, label in COLUMNS]]
    for r in rows:
        data.append([r[key] for key, _ in COLUMNS])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b4c7e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
    ]))
    story.append(table)
    story.extend(mentions_flowables(template, styles))
    footer = footer_callback(template, landscape(A4))
    if footer:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    else:
        doc.build(story)
    return buf.getvalue()


@router.get("/holdings")
def holdings_report(
    format: str = Query("json", pattern="^(json|csv|pdf|xlsx)$"),
    entite_id: int | None = None,
    service: str | None = None,
    session: Session = Depends(get_session),
):
    rows = _rows(session, entite_id, service)
    jour = date.today().isoformat()
    if format == "csv":
        return Response(
            content=_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="kikan-detentions-{jour}.csv"'},
        )
    if format == "xlsx":
        content = xlsx_io.build_table(
            "Detentions", [label for _, label in COLUMNS], [[r[key] for key, _ in COLUMNS] for r in rows],
            date_columns={[k for k, _ in COLUMNS].index("date_remise")})
        return Response(
            content=content,
            media_type=xlsx_io.XLSX_MIME,
            headers={"Content-Disposition": f'attachment; filename="kikan-detentions-{jour}.xlsx"'},
        )
    if format == "pdf":
        return Response(
            content=_pdf(rows, jour, load_template(session)),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="kikan-detentions-{jour}.pdf"'},
        )
    return {"date": jour, "count": len(rows), "rows": rows}
