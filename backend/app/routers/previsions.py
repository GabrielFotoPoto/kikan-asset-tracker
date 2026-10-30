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

"""Previsions de renouvellement (C3) : echeances a venir, budget estime par mois, annee, type et entite.

Le budget estime est la somme des couts de remplacement (Parametrage) du materiel dont l'echeance tombe dans la periode ;
le materiel reforme est ignore. Le materiel dont le cout n'est pas renseigne est compte a part ("sans estimation") et
n'entre pas dans les totaux. Le cloisonnement par entite s'applique (B2). Aucune donnee de salarie n'est renvoyee.
"""
import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session, select

from .. import xlsx_io
from ..auth import get_current_account
from ..db import get_session
from ..models import Asset, AssetStatus, CoutRemplacement, Entite
from ..pdf_template import footer_callback, header_flowables, load_template, mentions_flowables
from ..scope import Scope, restreindre_entite, scope_dep

router = APIRouter(
    prefix="/previsions", tags=["previsions"],
    dependencies=[Depends(get_current_account)],
)

MAX_MOIS = 60


def _ajouter_mois(jour: date, n: int) -> date:
    index = jour.year * 12 + jour.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def _periode(du: date | None, au: date | None) -> tuple[date, date]:
    """Par defaut : du premier jour du mois courant a la fin du onzieme mois suivant (12 mois)."""
    debut = du or date.today().replace(day=1)
    fin = au or _ajouter_mois(debut.replace(day=1), 12) - timedelta(days=1)
    if debut > fin:
        raise HTTPException(422, "La date de debut est posterieure a la date de fin")
    if (fin.year - debut.year) * 12 + fin.month - debut.month >= MAX_MOIS:
        raise HTTPException(422, f"La periode ne peut pas depasser {MAX_MOIS} mois")
    return debut, fin


def _couts(session: Session) -> dict[tuple[str, str, str], int]:
    return {((c.type or "").lower(), (c.marque or "").lower(), (c.modele or "").lower()): c.montant_centimes
            for c in session.exec(select(CoutRemplacement)).all()}


def _cout_asset(index: dict, a: Asset) -> tuple[int | None, str | None]:
    """Cout d'un materiel : l'exception de son modele si elle existe, sinon le cout de son type."""
    type_ = (a.type or "").lower()
    precis = index.get((type_, (a.marque or "").lower(), (a.modele or "").lower())) if a.marque and a.modele else None
    if precis is not None:
        return precis, "modele"
    general = index.get((type_, "", ""))
    return (general, "type") if general is not None else (None, None)


def _euros(centimes: int) -> float:
    return round(centimes / 100, 2)


def calculer(session: Session, scope: Scope, entite_id: int | None = None,
             du: date | None = None, au: date | None = None) -> dict:
    debut, fin = _periode(du, au)
    scope, entite = restreindre_entite(session, scope, entite_id)
    entites = {e.id: e.nom for e in session.exec(select(Entite)).all()}
    index = _couts(session)
    actifs = [a for a in session.exec(scope.where(select(Asset), Asset.entite_id)).all()
              if a.statut != AssetStatus.reforme and a.echeance_renouvellement]

    def bloc() -> dict:
        return {"nombre": 0, "centimes": 0, "sans_estimation": 0}

    def cumuler(b: dict, centimes: int | None) -> None:
        b["nombre"] += 1
        if centimes is None:
            b["sans_estimation"] += 1
        else:
            b["centimes"] += centimes

    def sortie(b: dict) -> dict:
        return {"nombre": b["nombre"], "montant": _euros(b["centimes"]), "sans_estimation": b["sans_estimation"]}

    total, retard = bloc(), bloc()
    par_mois = {}
    mois = debut.replace(day=1)
    while mois <= fin:
        par_mois[mois.strftime("%Y-%m")] = bloc()
        mois = _ajouter_mois(mois, 1)
    par_annee, par_type, par_entite = defaultdict(bloc), defaultdict(bloc), defaultdict(bloc)
    items = []
    for a in sorted(actifs, key=lambda x: (x.echeance_renouvellement, x.id)):
        centimes, source = _cout_asset(index, a)
        if a.echeance_renouvellement < debut:
            cumuler(retard, centimes)
            continue
        if a.echeance_renouvellement > fin:
            continue
        cumuler(total, centimes)
        cumuler(par_mois[a.echeance_renouvellement.strftime("%Y-%m")], centimes)
        cumuler(par_annee[a.echeance_renouvellement.year], centimes)
        cumuler(par_type[a.type or "(sans type)"], centimes)
        cumuler(par_entite[entites.get(a.entite_id, "(non rattache)")], centimes)
        items.append({
            "id": a.id, "identifiant_interne": a.identifiant_interne, "type": a.type, "marque": a.marque,
            "modele": a.modele, "entite": entites.get(a.entite_id, "(non rattache)"),
            "echeance": a.echeance_renouvellement.isoformat(),
            "cout": None if centimes is None else _euros(centimes), "source_cout": source,
        })
    def classe(d: dict, cle: str, tri=None) -> list[dict]:
        lignes = [{cle: k, **sortie(b)} for k, b in d.items()]
        return sorted(lignes, key=tri or (lambda l: -l["montant"]))

    return {
        "filtres": {"entite_id": entite.id if entite else None, "entite": entite.nom if entite else None},
        "periode": {"du": debut.isoformat(), "au": fin.isoformat()},
        "devise": "EUR",
        "total": sortie(total),
        "en_retard": sortie(retard),
        "par_mois": [{"mois": m, **sortie(b)} for m, b in par_mois.items()],
        "par_annee": classe(par_annee, "annee", lambda l: l["annee"]),
        "par_type": classe(par_type, "type"),
        "par_entite": classe(par_entite, "entite"),
        "items": items,
        "couts_renseignes": len(index),
    }


COLONNES = ["Mois", "Echeance", "Entite", "Type", "Marque", "Modele", "Id interne", "Cout estime (EUR)", "Source du cout"]
SOURCES = {"modele": "modele", "type": "type", None: "non renseigne"}


def _lignes(p: dict) -> list[list]:
    return [[i["echeance"][:7], i["echeance"], i["entite"], i["type"] or "", i["marque"] or "", i["modele"] or "",
             i["identifiant_interne"] or "", i["cout"], SOURCES[i["source_cout"]]] for i in p["items"]]


def _safe_cell(value) -> str:
    """Neutralise l'injection de formules : un tableur interprete =, +, -, @ en debut de cellule."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _csv(p: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(COLONNES)
    for ligne in _lignes(p):
        cout = ligne[7]
        writer.writerow([_safe_cell(v) for v in ligne[:7]] + ["" if cout is None else f"{cout:.2f}".replace(".", ","), ligne[8]])
    # BOM UTF-8 pour une ouverture correcte dans Excel FR.
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _xlsx(p: dict) -> bytes:
    return xlsx_io.build_table("Previsions", COLONNES, _lignes(p), date_columns={1}, amount_columns={7})


def _montant(m: float) -> str:
    return f"{m:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def _libelle(p: dict) -> str:
    return f"Entite : {p['filtres']['entite'] or 'toutes'} - Periode : du {p['periode']['du']} au {p['periode']['au']}"


def _pdf(p: dict, jour: str, template: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title="Previsions de renouvellement")
    styles = getSampleStyleSheet()
    t = p["total"]
    story = [
        *header_flowables(template, styles),
        Paragraph("Previsions de renouvellement", styles["Title"]),
        Paragraph(escape(f"Edite le {jour} - {_libelle(p)}"), styles["Normal"]),
        Paragraph(escape(f"{t['nombre']} materiel(s) a renouveler - budget estime : {_montant(t['montant'])}"
                         + (f" ({t['sans_estimation']} sans estimation de cout)" if t["sans_estimation"] else "")), styles["Normal"]),
        Spacer(1, 4 * mm),
    ]

    def tableau(titre: str, entetes: list[str], lignes: list[list]) -> None:
        story.append(Paragraph(escape(titre), styles["Heading3"]))
        if not lignes:
            story.extend([Paragraph("Aucune donnee.", styles["Italic"]), Spacer(1, 3 * mm)])
            return
        table = Table([entetes] + [[str(c) for c in l] for l in lignes], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b4c7e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
        ]))
        story.extend([table, Spacer(1, 4 * mm)])

    def ligne(cle: str, d: dict) -> list:
        return [d[cle], d["nombre"], _montant(d["montant"]), d["sans_estimation"]]

    tableau("Par mois", ["Mois", "Nombre", "Budget estime", "Sans estimation"], [ligne("mois", d) for d in p["par_mois"]])
    tableau("Par annee", ["Annee", "Nombre", "Budget estime", "Sans estimation"], [ligne("annee", d) for d in p["par_annee"]])
    tableau("Par type", ["Type", "Nombre", "Budget estime", "Sans estimation"], [ligne("type", d) for d in p["par_type"]])
    tableau("Par entite", ["Entite", "Nombre", "Budget estime", "Sans estimation"], [ligne("entite", d) for d in p["par_entite"]])
    r = p["en_retard"]
    if r["nombre"]:
        story.append(Paragraph(escape(f"Echeances anterieures a la periode, non renouvelees : {r['nombre']} materiel(s), "
                                      f"{_montant(r['montant'])} estime(s)."), styles["Normal"]))
        story.append(Spacer(1, 3 * mm))
    tableau("Detail", ["Echeance", "Entite", "Type", "Marque", "Modele", "Id interne", "Cout estime"],
            [[i["echeance"], i["entite"], i["type"] or "", i["marque"] or "", i["modele"] or "", i["identifiant_interne"] or "",
              "-" if i["cout"] is None else _montant(i["cout"])] for i in p["items"]])
    story.extend(mentions_flowables(template, styles))
    footer = footer_callback(template, landscape(A4))
    if footer:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    else:
        doc.build(story)
    return buf.getvalue()


@router.get("")
def previsions(
    format: str = Query("json", pattern="^(json|csv|pdf|xlsx)$"),
    entite_id: int | None = None,
    du: date | None = None,
    au: date | None = None,
    session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep),
):
    resultat = calculer(session, scope, entite_id, du, au)
    jour = date.today().isoformat()
    if format == "json":
        return resultat
    if format == "csv":
        contenu, mime = _csv(resultat), "text/csv; charset=utf-8"
    elif format == "xlsx":
        contenu, mime = _xlsx(resultat), xlsx_io.XLSX_MIME
    else:
        contenu, mime = _pdf(resultat, jour, load_template(session)), "application/pdf"
    return Response(content=contenu, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="kikan-previsions-{jour}.{format}"'})
