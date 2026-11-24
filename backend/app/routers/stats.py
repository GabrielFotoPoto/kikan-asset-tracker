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
import statistics
from collections import Counter
from datetime import date, datetime, timedelta
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

from .. import tickets as tickets_svc, xlsx_io
from ..auth import get_current_account, require_roles
from ..docname import heure_locale, jour_local
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
    Ticket,
    TicketNature,
    TicketSecurityDetail,
    User,
    utcnow,
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

    today = jour_local()

    def echeances(debut: date, fin: date) -> list[dict]:
        items = [{
            "id": a.id, "identifiant_interne": a.identifiant_interne,
            "type": a.type, "marque": a.marque, "modele": a.modele,
            "echeance": str(a.echeance_renouvellement),
        } for a in assets if a.echeance_renouvellement and debut <= a.echeance_renouvellement <= fin
            and a.statut in (AssetStatus.stock, AssetStatus.affecte)]   # le materiel rendu ou reforme n'est plus a renouveler
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

    liens: dict[int, list[AssignmentAsset]] = {}
    for l in session.exec(select(AssignmentAsset)).all():
        liens.setdefault(l.assignment_id, []).append(l)
    par_mois: dict[str, Counter] = {}
    totaux = Counter()

    def compter(cle: str, jour: date, n: int) -> None:
        totaux[cle] += n
        par_mois.setdefault(jour.strftime("%Y-%m"), Counter())[cle] += n

    for a in session.exec(scope.assignments(select(Assignment))).all():
        remise = heure_locale(a.date_remise).date() if a.date_remise else None
        if dans(remise):
            compter("remis", remise, len(liens.get(a.id, [])))
        # Restitutions : date de retour de chaque actif (un echange ou une restitution partielle ne clot pas l'affectation).
        for l in liens.get(a.id, []):
            retour = heure_locale(l.date_retour).date() if l.date_retour else None
            if dans(retour):
                compter("restitues", retour, 1)
    for a in assets:
        if dans(a.date_achat):
            compter("achetes", a.date_achat, 1)
    return {
        "remis": totaux["remis"], "restitues": totaux["restitues"], "achetes": totaux["achetes"],
        "par_mois": [{"mois": m, "remis": c["remis"], "restitues": c["restitues"], "achetes": c["achetes"]}
                     for m, c in sorted(par_mois.items())],
    }


STATUTS = {"stock": "En stock", "affecte": "Affecte", "reforme": "Reforme", "rendu": "Rendu", "non_restitue": "Non restitue"}


def _sections(s: dict) -> list[tuple[str, list[str], list[list]]]:
    """Le meme contenu pour les trois formats : (titre, en-tetes, lignes)."""
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
    jour = jour_local().isoformat()
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


# --- Statistiques et KPI tickets (lot G6, reserve au role informatique, strictement sans PII) ---

def _moy_med_heures(secondes: list[int]) -> dict:
    if not secondes:
        return {"mediane": None, "moyenne": None, "echantillon": 0}
    heures = [s / 3600.0 for s in secondes]
    return {
        "mediane": round(statistics.median(heures), 2),
        "moyenne": round(sum(heures) / len(heures), 2),
        "echantillon": len(heures),
    }


def calculer_tickets(
    session: Session,
    scope: Scope,
    entite_id: int | None = None,
    du: date | None = None,
    au: date | None = None,
    nature: str | None = None,
    criticite: str | None = None,
) -> dict:
    if du and au and du > au:
        raise HTTPException(422, "La date de debut est posterieure a la date de fin")
    crit_clean = criticite.strip().lower() if criticite else None
    if crit_clean and crit_clean not in tickets_svc.CRITICITES:
        raise HTTPException(422, "Criticite invalide")
    nature_clean = nature.strip().lower() if nature else None

    scope, entite = restreindre_entite(session, scope, entite_id)

    stmt = scope.where(select(Ticket), Ticket.entite_id)
    if nature_clean:
        stmt = stmt.where(Ticket.nature_code == nature_clean)
    if crit_clean:
        stmt = stmt.where(Ticket.criticite == crit_clean)
    rows = session.exec(stmt).all()

    natures = {n.code: n.libelle for n in session.exec(select(TicketNature)).all()}
    ids = [t.id for t in rows if t.id is not None]
    secs = (
        {
            s.ticket_id: s
            for s in session.exec(
                select(TicketSecurityDetail).where(TicketSecurityDetail.ticket_id.in_(ids))
            ).all()
        }
        if ids
        else {}
    )

    def dans(dt: datetime | None) -> bool:
        if dt is None:
            return False
        jour = heure_locale(dt).date()
        return (du is None or jour >= du) and (au is None or jour <= au)

    now = utcnow()
    crees_rows: list[Ticket] = []
    resolus_rows: list[Ticket] = []
    fermes_count = 0
    annules_count = 0
    evo: dict[str, Counter] = {}
    par_canal = Counter()
    par_nature = Counter()
    pannes_mat = Counter()

    stock_par_crit = {c: 0 for c in tickets_svc.CRITICITES}
    stock_par_anc = {"moins_24h": 0, "1_7j": 0, "plus_7j": 0}
    stock_total = 0

    for t in rows:
        if t.statut in ("nouveau", "en_cours", "en_attente") and t.anonymise_le is None:
            stock_total += 1
            if t.criticite in stock_par_crit:
                stock_par_crit[t.criticite] += 1
            age_h = max(0.0, (now - t.cree_le).total_seconds() / 3600.0) if t.cree_le else 0.0
            if age_h < 24.0:
                stock_par_anc["moins_24h"] += 1
            elif age_h <= 168.0:
                stock_par_anc["1_7j"] += 1
            else:
                stock_par_anc["plus_7j"] += 1

        if dans(t.cree_le):
            crees_rows.append(t)
            mois_c = heure_locale(t.cree_le).strftime("%Y-%m")
            evo.setdefault(mois_c, Counter())["crees"] += 1
            par_canal[t.canal or "it"] += 1
            par_nature[t.nature_code or "autre"] += 1
            if t.nature_code == "panne_materiel" and (t.materiel_type or t.materiel_marque or t.materiel_modele):
                pannes_mat[(t.materiel_type or "?", t.materiel_marque or "?", t.materiel_modele or "?")] += 1

        if dans(t.resolu_le):
            resolus_rows.append(t)
            mois_r = heure_locale(t.resolu_le).strftime("%Y-%m")
            evo.setdefault(mois_r, Counter())["resolus"] += 1

        if t.statut == "ferme" and dans(t.ferme_le):
            fermes_count += 1
        elif t.statut == "annule" and dans(t.ferme_le):
            annules_count += 1

    mtta_secs = [s for t in crees_rows if (s := tickets_svc.calculer_mtta_sec(t)) is not None]
    mttr_secs = [s for t in resolus_rows if (s := tickets_svc.calculer_mttr_sec(t)) is not None]

    reouverts_ids = {
        t.id for t in rows
        if (t.nb_reouvertures or 0) > 0 and (dans(t.resolu_le) or dans(t.cree_le))
    }
    nb_resolus = len(resolus_rows)
    denom_reouv = max(nb_resolus, len(reouverts_ids))
    taux_reouverture = round(100.0 * len(reouverts_ids) / denom_reouv, 1) if denom_reouv else 0.0

    # Fiabilite parc materiel : rapport au parc actif (stock + affecte) dans le perimetre d'entite
    assets = session.exec(
        scope.where(select(Asset), Asset.entite_id).where(Asset.statut.in_((AssetStatus.stock, AssetStatus.affecte)))
    ).all()
    parc_counts = Counter((a.type or "?", a.marque or "?", a.modele or "?") for a in assets)
    top_materiels = []
    for (m_type, m_marque, m_modele), inc in pannes_mat.most_common(10):
        parc_n = parc_counts.get((m_type, m_marque, m_modele), 0)
        top_materiels.append({
            "type": m_type,
            "marque": m_marque,
            "modele": m_modele,
            "incidents": inc,
            "parc": parc_n,
            "taux_pourcent": round(100.0 * inc / parc_n, 1) if parc_n > 0 else None,
        })

    # Pilotage securite (strictement agregats, aucune PII ni texte libre)
    sec_rows = [(t, secs[t.id]) for t in rows if t.id in secs and dans(secs[t.id].signale_le)]
    par_origine = {"demandeur": 0, "informatique": 0}
    par_sous_cat = Counter()
    escalades = 0
    sans_suite = 0
    retrogradations = 0
    violations = 0
    qualif_secs: list[int] = []
    for t, sec in sec_rows:
        if sec.signale_par in par_origine:
            par_origine[sec.signale_par] += 1
        if t.niveau_securite == "incident" or sec.escalade_le is not None:
            escalades += 1
        if t.niveau_securite == "sans_suite":
            sans_suite += 1
        retrogradations += sec.nb_retrogradations or 0
        if sec.sous_categorie:
            par_sous_cat[sec.sous_categorie] += 1
        if sec.violation_donnees_potentielle:
            violations += 1
        if sec.qualification_sec is not None:
            qualif_secs.append(sec.qualification_sec)
        elif sec.qualifie_le and sec.signale_le:
            qualif_secs.append(max(0, int((sec.qualifie_le - sec.signale_le).total_seconds())))

    signales_total = len(sec_rows)
    taux_sans_suite = round(100.0 * sans_suite / signales_total, 1) if signales_total else 0.0
    qualif_moy_h = round((sum(qualif_secs) / len(qualif_secs)) / 3600.0, 2) if qualif_secs else None

    return {
        "filtres": {
            "entite_id": entite.id if entite else None,
            "entite": entite.nom if entite else None,
            "du": du.isoformat() if du else None,
            "au": au.isoformat() if au else None,
            "nature": nature_clean,
            "criticite": crit_clean,
        },
        "activite": {
            "crees": len(crees_rows),
            "resolus": nb_resolus,
            "fermes": fermes_count,
            "annules": annules_count,
            "stock_ouvert": {
                "total": stock_total,
                "par_criticite": stock_par_crit,
                "par_anciennete": stock_par_anc,
            },
            "evolution_mensuelle": [
                {"mois": m, "crees": c["crees"], "resolus": c["resolus"]}
                for m, c in sorted(evo.items())
            ],
            "par_canal": [
                {"canal": c, "count": par_canal.get(c, 0)}
                for c in tickets_svc.CANAUX
                if par_canal.get(c, 0) > 0
            ],
        },
        "reactivite": {
            "mtta_heures": _moy_med_heures(mtta_secs),
            "mttr_heures": _moy_med_heures(mttr_secs),
            "reouvertures": {
                "tickets_reouverts": len(reouverts_ids),
                "tickets_resolus": nb_resolus,
                "taux_pourcent": taux_reouverture,
            },
        },
        "fiabilite_parc": {
            "par_nature": [
                {"code": code, "libelle": natures.get(code, code), "count": count}
                for code, count in par_nature.most_common()
            ],
            "top_materiels": top_materiels,
        },
        "securite": {
            "signales_total": signales_total,
            "par_origine": par_origine,
            "escalades_incident": escalades,
            "classes_sans_suite": sans_suite,
            "taux_sans_suite_pourcent": taux_sans_suite,
            "retrogradations": retrogradations,
            "par_sous_categorie": [
                {"sous_categorie": k, "count": v}
                for k, v in par_sous_cat.most_common()
            ],
            "qualification_moyenne_heures": qualif_moy_h,
            "violations_potentielles": violations,
        },
    }


def _sections_tickets(s: dict) -> list[tuple[str, list[list]]]:
    a = s["activite"]
    r = s["reactivite"]
    f = s["fiabilite_parc"]
    sec = s["securite"]
    sections = [
        ("Activite", [
            ["Tickets crees", a["crees"]],
            ["Tickets resolus", a["resolus"]],
            ["Tickets fermes", a["fermes"]],
            ["Tickets annules", a["annules"]],
            ["Stock ouvert actuel", a["stock_ouvert"]["total"]],
            ["Stock ouvert - critique", a["stock_ouvert"]["par_criticite"]["critique"]],
            ["Stock ouvert - haute", a["stock_ouvert"]["par_criticite"]["haute"]],
            ["Stock ouvert - moyenne", a["stock_ouvert"]["par_criticite"]["moyenne"]],
            ["Stock ouvert - faible", a["stock_ouvert"]["par_criticite"]["faible"]],
            ["Stock ouvert - moins de 24h", a["stock_ouvert"]["par_anciennete"]["moins_24h"]],
            ["Stock ouvert - 1 a 7 jours", a["stock_ouvert"]["par_anciennete"]["1_7j"]],
            ["Stock ouvert - plus de 7 jours", a["stock_ouvert"]["par_anciennete"]["plus_7j"]],
        ]),
        ("Reactivite et qualite", [
            ["MTTA mediane (h)", "" if r["mtta_heures"]["mediane"] is None else r["mtta_heures"]["mediane"]],
            ["MTTA moyenne (h)", "" if r["mtta_heures"]["moyenne"] is None else r["mtta_heures"]["moyenne"]],
            ["MTTR net mediane (h)", "" if r["mttr_heures"]["mediane"] is None else r["mttr_heures"]["mediane"]],
            ["MTTR net moyenne (h)", "" if r["mttr_heures"]["moyenne"] is None else r["mttr_heures"]["moyenne"]],
            ["Tickets reouverts", r["reouvertures"]["tickets_reouverts"]],
            ["Taux de reouverture (%)", r["reouvertures"]["taux_pourcent"]],
        ]),
        ("Evolution mensuelle", [
            [f"{m['mois']} - crees / resolus", f"{m['crees']} / {m['resolus']}"]
            for m in a["evolution_mensuelle"]
        ]),
        ("Repartition par canal", [[c["canal"], c["count"]] for c in a["par_canal"]]),
        ("Repartition par nature", [[n["libelle"], n["count"]] for n in f["par_nature"]]),
        ("Fiabilite materiel (pannes)", [
            [f"{m['type']} {m['marque']} {m['modele']} (parc : {m['parc']})",
             f"{m['incidents']}" + (f" ({m['taux_pourcent']}%)" if m["taux_pourcent"] is not None else "")]
            for m in f["top_materiels"]
        ]),
        ("Pilotage securite", [
            ["Evenements signales", sec["signales_total"]],
            ["Origine demandeur", sec["par_origine"]["demandeur"]],
            ["Origine informatique", sec["par_origine"]["informatique"]],
            ["Escalades en incident", sec["escalades_incident"]],
            ["Classes sans suite", sec["classes_sans_suite"]],
            ["Taux sans suite (%)", sec["taux_sans_suite_pourcent"]],
            ["Retrogradations", sec["retrogradations"]],
            ["Delai moyen de qualification (h)", "" if sec["qualification_moyenne_heures"] is None else sec["qualification_moyenne_heures"]],
            ["Incidents avec violation potentielle", sec["violations_potentielles"]],
            *[[f"Sous-categorie : {c['sous_categorie']}", c["count"]] for c in sec["par_sous_categorie"]],
        ]),
    ]
    return sections


def _csv_tickets(s: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Rubrique", "Indicateur", "Valeur"])
    for titre, lignes in _sections_tickets(s):
        for libelle, valeur in lignes:
            writer.writerow([_safe_cell(titre), _safe_cell(libelle), _safe_cell(valeur)])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _xlsx_tickets(s: dict) -> bytes:
    lignes = [
        [titre, libelle, valeur]
        for titre, bloc in _sections_tickets(s)
        for libelle, valeur in bloc
    ]
    return xlsx_io.build_table("Statistiques tickets", ["Rubrique", "Indicateur", "Valeur"], lignes)


@router.get("/tickets", dependencies=[Depends(require_roles("informatique"))])
def stats_tickets(
    format: str = Query("json", pattern="^(json|csv|xlsx)$"),
    entite_id: int | None = None,
    du: date | None = None,
    au: date | None = None,
    nature: str | None = None,
    criticite: str | None = None,
    session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep),
):
    resultat = calculer_tickets(session, scope, entite_id, du, au, nature, criticite)
    if format == "json":
        return resultat
    jour = jour_local().isoformat()
    if format == "csv":
        contenu, mime = _csv_tickets(resultat), "text/csv; charset=utf-8"
    else:
        contenu, mime = _xlsx_tickets(resultat), xlsx_io.XLSX_MIME
    return Response(content=contenu, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="kikan-statistiques-tickets-{jour}.{format}"'})
