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

"""Generation du PDF d'accuse de remise (ReportLab)."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build_receipt(
    *,
    user: dict,
    entite_nom: str | None,
    assets: list[dict],
    policy_text: str | None = None,
    charte_info: dict | None = None,
    title: str = "Accuse de remise de materiel",
    kind: str = "remise",
    signature_png: bytes | None = None,
    signataire: str | None = None,
    temoin: str | None = None,
    signed_at: datetime | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 6 * mm))

    ligne = f"Salarie : {user.get('prenom', '')} {user.get('nom', '')}"
    if user.get("matricule"):
        ligne += f" (matricule {user['matricule']})"
    story.append(Paragraph(escape(ligne), styles["Normal"]))
    if entite_nom:
        story.append(Paragraph(escape(f"Entite : {entite_nom}"), styles["Normal"]))
    story.append(Paragraph(f"Date : {(signed_at or datetime.utcnow()):%Y-%m-%d %H:%M} UTC", styles["Normal"]))
    story.append(Spacer(1, 6 * mm))

    data = [["Type", "Marque", "Modele", "N de serie", "Id interne"]]
    for a in assets:
        data.append([
            a.get("type") or "",
            a.get("marque") or "",
            a.get("modele") or "",
            a.get("numero_serie") or "",
            a.get("identifiant_interne") or "",
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b4c7e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 8 * mm))

    if policy_text:
        story.append(Paragraph("Charte informatique", styles["Heading2"]))
        for para in policy_text.split("\n"):
            if para.strip():
                story.append(Paragraph(escape(para), styles["Normal"]))
        story.append(Spacer(1, 8 * mm))

    if kind == "restitution":
        declaration = "Je reconnais avoir restitue le materiel ci-dessus."
    elif charte_info:
        declaration = (
            "Je reconnais avoir recu le materiel ci-dessus et accepte la charte informatique "
            f"({charte_info['titre']}, version {charte_info['version']}, empreinte {charte_info['sha256'][:8]}), "
            f"jointe en annexe de ce document ({charte_info['nb_pages']} page(s))."
        )
    elif policy_text:
        declaration = "Je reconnais avoir recu le materiel ci-dessus et accepte la charte informatique."
    else:
        declaration = "Je reconnais avoir recu le materiel ci-dessus."

    # Bloc de signature : insecable (jamais coupe entre deux pages).
    block = [
        Paragraph(escape(declaration), styles["Normal"]),
        Spacer(1, 6 * mm),
        Paragraph("Signature de l'employe :", styles["Normal"]),
        Spacer(1, 2 * mm),
    ]
    if signature_png:
        with PILImage.open(io.BytesIO(signature_png)) as im:
            w_px, h_px = im.size
        max_w, max_h = 70 * mm, 28 * mm
        scale = min(max_w / w_px, max_h / h_px)
        block.append(Image(io.BytesIO(signature_png), width=w_px * scale, height=h_px * scale, hAlign="LEFT"))
    else:
        block.append(Spacer(1, 18 * mm))
    when = signed_at or datetime.utcnow()
    if signataire:
        block.append(Paragraph(escape(signataire), styles["Normal"]))
    block.append(Paragraph(f"Signe le {when:%Y-%m-%d a %H:%M} UTC", styles["Normal"]))
    if temoin:
        block.append(Paragraph(escape(f"Document conduit par : {temoin} (service informatique, temoin)"),
                               styles["Normal"]))
    story.append(KeepTogether(block))

    doc.build(story)
    return buf.getvalue()
