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

"""Statistiques de parc (lecture, tous roles authentifies) : filtres par entite et periode, export CSV, Excel et PDF (C1).

Le filtre d'entite inclut les sous-entites et ne sort jamais de la portee du compte (B2) ; une entite hors portee est
"introuvable". Les repartitions (statut, entite, service, modeles, age, taux d'equipement) decrivent le parc a
l'instant de la requete, restreint a l'entite choisie. La periode (du, au) pilote les mouvements (remises,
restitutions, achats, par mois) et la fenetre des renouvellements ; sans periode, la fenetre va d'aujourd'hui a 12 mois.
"""
import csv
import io
from collections import Counter
from datetime import date, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func
from sqlmodel import Session, select

from .. import xlsx_io
from ..auth import get_current_account
from ..docname import heure_locale
from ..scope import Scope, restreindre_entite, scope_dep
from ..db import get_session
from ..theme import BLEU_MARQUE
from ..pdf_template import footer_callback, header_flowables, load_template, mentions_flowables
from ..models import (
    Asset,
    AssetStatus,
    Besoin,
    Assignment,
    AssignmentAsset,
    Account,
    EmployeeStatus,
    Entite,
    Role,
    User,
)

router = APIRouter(
    prefix="/stats", tags=["stats"],
    dependencies=[Depends(get_current_account)],
)


def calculer(session: Session, scope: Scope, entite_id: int | None = None,
             du: date | None = None, au: date | None = None) -> dict:
    if du and au and du > au:
        raise HTTPException(422, "La date de debut est posterieure a la date de fin")
    scope, entite = restreindre_entite(session, scope, entite_id)
    assets = session.exec(scope.where(select(Asset), Asset.entite_id)).all()
    entites = {e.id: e.nom for e in session.exec(select(Entite)).all()}

    # Actif -> salarie detenteur (affectation en cours).
    encours = {a.id: a for a in session.exec(
        select(Assignment).where(Assignment.statut == "en_cours")).all()}
    asset_user = {}
    for link in session.exec(select(AssignmentAsset)).all():
        if link.assignment_id in encours:
            asset_user[link.asset_id] = encours[link.assignment_id].user_id
    users = {u.id: u for u in session.exec(scope.users(select(User))).all()}

    affecte = [a for a in assets if a.statut == AssetStatus.affecte]

    par_statut = Counter(a.statut.value for a in assets)

    top = Counter((a.type or "?", a.marque or "?", a.modele or "?") for a in affecte)
    top_modeles = [
        {"type": t, "marque": m, "modele": mo, "count": n}
        for (t, m, mo), n in top.most_common(10)
    ]

    par_entite = Counter(entites.get(a.entite_id, "(non rattache)") for a in affecte)
    services = Counter()
    for a in affecte:
        uid = asset_user.get(a.id)
        svc = (users[uid].service if uid in users else None) or "(non renseigne)"
        services[svc] += 1

    today = date.today()

    def echeances(debut: date, fin: date) -> list[dict]:
        items = [{
            "id": a.id, "identifiant_interne": a.identifiant_interne,
            "type": a.type, "marque": a.marque, "modele": a.modele,
            "echeance": str(a.echeance_renouvellement),
        } for a in assets if a.echeance_renouvellement and debut <= a.echeance_renouvellement <= fin]
        return sorted(items, key=lambda r: r["echeance"])

    renouv = echeances(today, today + timedelta(days=365))
    debut = du or today
    fenetre = echeances(debut, au or debut + timedelta(days=365))

    ages = [(today - a.date_achat).days / 365.25 for a in assets if a.date_achat]
    age_moyen = round(sum(ages) / len(ages), 1) if ages else None

    actifs_users = [u for u in users.values() if u.statut == EmployeeStatus.actif]
    equipes = {asset_user[a.id] for a in affecte if a.id in asset_user}
    nb_equipes = sum(1 for u in actifs_users if u.id in equipes)
    taux = round(100 * nb_equipes / len(actifs_users), 1) if actifs_users else 0

    besoins = session.exec(
        scope.users(select(func.count()).select_from(Besoin).join(User, User.id == Besoin.user_id)
                    .where(Besoin.statut.in_(("demande", "en_preparation"))))).one()

    resultat = {
        "filtres": {"entite_id": entite.id if entite else None, "entite": entite.nom if entite else None,
                    "du": du.isoformat() if du else None, "au": au.isoformat() if au else None},
        "besoins_a_traiter": besoins,
        "actifs_total": len(assets),
        "actifs_par_statut": dict(par_statut),
        "top_modeles": top_modeles,
        "par_entite": [{"entite": k, "count": v} for k, v in par_entite.most_common()],
        "par_service": [{"service": k, "count": v} for k, v in services.most_common()],
        "renouvellements_12m": {"count": len(renouv), "items": renouv},
        "renouvellements": {"du": debut.isoformat(), "au": (au or debut + timedelta(days=365)).isoformat(),
                            "count": len(fenetre), "items": fenetre},
        "age_moyen_annees": age_moyen,
        "taux_equipement": {
            "salaries_actifs": len(actifs_users),
            "equipes": nb_equipes,
            "pourcentage": taux,
        },
    }
    if du or au:
        resultat["mouvements"] = _mouvements(session, scope, assets, du, au)
    return resultat


def _mouvements(session: Session, scope: Scope, assets: list[Asset], du: date | None, au: date | None) -> dict:
    """Materiels remis, restitues et achetes pendant la periode (dates locales de l'organisation), au total et par mois."""
    def dans(jour: date | None) -> bool:
        return jour is not None and (du is None or jour >= du) and (au is None or jour <= au)

    nb_actifs = Counter(l.assignment_id for l in session.exec(select(AssignmentAsset)).all())
    par_mois: dict[str, Counter] = {}
    totaux = Counter()

    def compter(cle: str, jour: date, n: int) -> None:
        totaux[cle] += n
        par_mois.setdefault(jour.strftime("%Y-%m"), Counter())[cle] += n

    for a in session.exec(scope.assignments(select(Assignment))).all():
        remise = heure_locale(a.date_remise).date() if a.date_remise else None
        if dans(remise):
            compter("remis", remise, nb_actifs.get(a.id, 0))
        retour = heure_locale(a.date_restitution).date() if a.date_restitution else None
        if dans(retour):
            compter("restitues", retour, nb_actifs.get(a.id, 0))
    for a in assets:
        if dans(a.date_achat):
            compter("achetes", a.date_achat, 1)
    return {
        "remis": totaux["remis"], "restitues": totaux["restitues"], "achetes": totaux["achetes"],
        "par_mois": [{"mois": m, "remis": c["remis"], "restitues": c["restitues"], "achetes": c["achetes"]}
                     for m, c in sorted(par_mois.items())],
    }


STATUTS = {"stock": "En stock", "affecte": "Affecte", "reforme": "Reforme"}


def _sections(s: dict) -> list[tuple[str, list[str], list[list]]]:
    """Le meme contenu pour les trois formats : (titre, en-tetes, lignes)."""
    f = s["filtres"]
    sections = [("Synthese", ["Indicateur", "Valeur"], [
        ["Actifs au total", s["actifs_total"]],
        ["Salaries actifs", s["taux_equipement"]["salaries_actifs"]],
        ["Salaries actifs equipes", s["taux_equipement"]["equipes"]],
        ["Taux d'equipement (%)", s["taux_equipement"]["pourcentage"]],
        ["Age moyen du parc (ans)", "" if s["age_moyen_annees"] is None else s["age_moyen_annees"]],
        ["Besoins a traiter", s["besoins_a_traiter"]],
    ])]
    if "mouvements" in s:
        m = s["mouvements"]
        sections.append(("Mouvements de la periode", ["Mois", "Remis", "Restitues", "Achetes"],
                         [["Total", m["remis"], m["restitues"], m["achetes"]]]
                         + [[x["mois"], x["remis"], x["restitues"], x["achetes"]] for x in m["par_mois"]]))
    sections += [
        ("Actifs par statut", ["Statut", "Nombre"],
         [[STATUTS.get(k, k), v] for k, v in sorted(s["actifs_par_statut"].items())]),
        ("Modeles les plus distribues", ["Type", "Marque", "Modele", "Nombre"],
         [[i["type"], i["marque"], i["modele"], i["count"]] for i in s["top_modeles"]]),
        ("Materiel affecte par entite", ["Entite", "Nombre"], [[i["entite"], i["count"]] for i in s["par_entite"]]),
        ("Materiel affecte par service", ["Service", "Nombre"], [[i["service"], i["count"]] for i in s["par_service"]]),
    ]
    r = s["renouvellements"]
    sections.append((f"Renouvellements du {r['du']} au {r['au']} ({r['count']})",
                     ["Id interne", "Type", "Marque", "Modele", "Echeance"],
                     [[i["identifiant_interne"] or "", i["type"] or "", i["marque"] or "", i["modele"] or "", i["echeance"]]
                      for i in r["items"]]))
    return sections


def _safe_cell(value) -> str:
    """Neutralise l'injection de formules : un tableur interprete =, +, -, @ en debut de cellule."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _libelle_filtres(f: dict) -> str:
    periode = "toute la periode" if not (f["du"] or f["au"]) else f"du {f['du'] or '...'} au {f['au'] or '...'}"
    return f"Entite : {f['entite'] or 'toutes'} - Periode : {periode}"


def _csv(s: dict) -> bytes:
    """Format long : une ligne par valeur (Rubrique ; Libelle ; Valeur), simple a filtrer dans un tableur."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Rubrique", "Libelle", "Valeur"])
    for titre, entetes, lignes in _sections(s):
        for ligne in lignes:
            writer.writerow([_safe_cell(titre), _safe_cell(" / ".join(str(c) for c in ligne[:-1])), _safe_cell(ligne[-1])])
    # BOM UTF-8 pour une ouverture correcte dans Excel FR.
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _xlsx(s: dict) -> bytes:
    lignes = [[titre, " / ".join(str(c) for c in ligne[:-1]), ligne[-1]]
              for titre, _, bloc in _sections(s) for ligne in bloc]
    return xlsx_io.build_table("Statistiques", ["Rubrique", "Libelle", "Valeur"], lignes)


def _pdf(s: dict, jour: str, template: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Statistiques du parc")
    styles = getSampleStyleSheet()
    story = [
        *header_flowables(template, styles),
        Paragraph("Statistiques du parc", styles["Title"]),
        Paragraph(escape(f"Edite le {jour} - {_libelle_filtres(s['filtres'])}"), styles["Normal"]),
        Spacer(1, 4 * mm),
    ]
    for titre, entetes, lignes in _sections(s):
        story.append(Paragraph(titre, styles["Heading3"]))
        if not lignes:
            story += [Paragraph("Aucune donnee.", styles["Italic"]), Spacer(1, 3 * mm)]
            continue
        table = Table([entetes] + [[str(c) for c in l] for l in lignes], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLEU_MARQUE)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
        ]))
        story += [table, Spacer(1, 4 * mm)]
    story.extend(mentions_flowables(template, styles))
    footer = footer_callback(template, A4)
    if footer:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    else:
        doc.build(story)
    return buf.getvalue()


@router.get("")
def stats(
    format: str = Query("json", pattern="^(json|csv|pdf|xlsx)$"),
    entite_id: int | None = None,
    du: date | None = None,
    au: date | None = None,
    session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep),
    account: Account = Depends(get_current_account),
):
    resultat = calculer(session, scope, entite_id, du, au)
    if account.role == Role.rh:  # le suivi des besoins de materiel n'est pas visible des RH
        resultat["besoins_a_traiter"] = None
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
        "Content-Disposition": f'attachment; filename="kikan-statistiques-{jour}.{format}"'})
