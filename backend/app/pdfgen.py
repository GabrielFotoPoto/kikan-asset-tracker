"""Generation du PDF d'accuse de remise (ReportLab)."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
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
    title: str = "Accuse de remise de materiel",
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
    story.append(Paragraph(ligne, styles["Normal"]))
    if entite_nom:
        story.append(Paragraph(f"Entite : {entite_nom}", styles["Normal"]))
    story.append(Paragraph(f"Date : {datetime.now():%Y-%m-%d %H:%M}", styles["Normal"]))
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
                story.append(Paragraph(para, styles["Normal"]))
        story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        "Je reconnais avoir recu le materiel ci-dessus et accepte la charte informatique.",
        styles["Normal"],
    ))
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("Signature :", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()
