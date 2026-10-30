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

"""Revue periodique des droits d'acces (ISO 27001, A.5.18).

- Rapport "qui a acces a quoi" et anomalies (acces actif d'un salarie sorti, d'une application desactivee) : toujours dans le perimetre du compte.
- Campagne a la demande (informatique) : une ligne par acces actif ; les comptes RH (dans leur perimetre) et informatique decident
  "maintenu" ou "a retirer" ; la campagne ne se cloture que lorsque tout est traite.
- A la cloture : les acces "a retirer" passent a "non" (l'historique est conserve), un rapport PDF scelle (PAdES) est depose dans le stockage,
  et les retraits deviennent une liste de taches : Kikan est un registre, il ne coupe pas le droit dans l'application concernee ; l'informatique
  confirme "retire dans le systeme" une fois l'action faite.
- Le rapport scelle ne contient que le matricule (jamais le nom) ; la purge RGPD supprime les lignes d'un salarie purge.
"""
import io
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session, select

from .audit import audit
from .filestore import meta_for, sha256_hex, store_document
from .models import (
    Account, Application, Entite, EmployeeStatus, RevueAcces, RevueLigne, User, UserApplication,
)
from .pdf_template import footer_callback, header_flowables, load_template, mentions_flowables
from .scope import GLOBAL, Scope, expand_scope
from .theme import BLEU_MARQUE
from .signing import seal_pdf

DECISIONS = ("a_traiter", "maintenu", "a_retirer")
RELANCE_ANNUELLE_JOURS = 365
ECHEANCE_PREAVIS_JOURS = 7
RETRAIT_DELAI_JOURS = 7


def _libelle(u: User) -> str:
    return f"{u.prenom} {u.nom}".strip()


def _anomalie(u: User, a: Application, today: date) -> str | None:
    """Raison pour laquelle un acces actif pose probleme (None si rien a signaler)."""
    raisons = []
    if u.statut == EmployeeStatus.sorti:
        raisons.append("salarie sorti")
    elif u.statut == EmployeeStatus.en_depart and u.date_sortie and u.date_sortie < today:
        raisons.append("date de sortie depassee")
    if not a.actif:
        raisons.append("application desactivee")
    return ", ".join(raisons) or None


def _acces_actifs(session: Session, scope: Scope):
    stmt = (select(UserApplication, User, Application)
            .join(User, User.id == UserApplication.user_id)
            .join(Application, Application.id == UserApplication.application_id)
            .where(UserApplication.acces == True))  # noqa: E712
    return scope.where(stmt, User.entite_id)


def anomalies(session: Session, scope: Scope, today: date | None = None) -> list[dict]:
    today = today or date.today()
    noms = {e.id: e.nom for e in session.exec(select(Entite)).all()}
    out = []
    for ua, u, a in session.exec(_acces_actifs(session, scope).order_by(User.nom, User.prenom, Application.nom)).all():
        raison = _anomalie(u, a, today)
        if raison:
            out.append({"user_id": u.id, "matricule": u.matricule, "salarie": _libelle(u), "entite": noms.get(u.entite_id),
                        "application": a.nom, "anomalie": raison, "acces_id": ua.id})
    return out


def acces(session: Session, scope: Scope, entite_id: int | None = None, application_id: int | None = None) -> list[dict]:
    """Rapport "qui a acces a quoi" : une ligne par acces (actif ou non), dans le perimetre."""
    noms = {e.id: e.nom for e in session.exec(select(Entite)).all()}
    stmt = (select(UserApplication, User, Application)
            .join(User, User.id == UserApplication.user_id)
            .join(Application, Application.id == UserApplication.application_id))
    stmt = scope.where(stmt, User.entite_id)
    if entite_id is not None:
        stmt = stmt.where(User.entite_id == entite_id)
    if application_id is not None:
        stmt = stmt.where(UserApplication.application_id == application_id)
    today = date.today()
    rows = []
    for ua, u, a in session.exec(stmt.order_by(Application.nom, User.nom, User.prenom)).all():
        rows.append({"matricule": u.matricule or "", "salarie": _libelle(u), "entite": noms.get(u.entite_id) or "", "service": u.service or "",
                     "statut_salarie": u.statut.value, "application": a.nom, "acces": "oui" if ua.acces else "non", "note": ua.note or "",
                     "attribue_par": ua.attribue_par or "", "date_maj": str(ua.date_maj)[:10],
                     "anomalie": (_anomalie(u, a, today) or "") if ua.acces else ""})
    return rows


# --- Campagnes ---

def creer(session: Session, account: Account, titre: str, echeance: date | None, entite_ids: list[int], application_ids: list[int]) -> RevueAcces:
    if session.exec(select(RevueAcces).where(RevueAcces.statut == "en_cours")).first():
        raise HTTPException(409, "Une revue est deja en cours : cloturez-la avant d'en lancer une autre.")
    perimetre: Scope = expand_scope(session, set(entite_ids)) if entite_ids else GLOBAL
    stmt = _acces_actifs(session, perimetre)
    if application_ids:
        stmt = stmt.where(UserApplication.application_id.in_(application_ids))
    rows = session.exec(stmt.order_by(User.nom, User.prenom, Application.nom)).all()
    if not rows:
        raise HTTPException(400, "Aucun acces actif a revoir pour ce perimetre.")
    revue = RevueAcces(titre=titre, echeance=echeance, cree_par=account.username,
                       perimetre={"entites": sorted(set(entite_ids)), "applications": sorted(set(application_ids))})
    session.add(revue)
    session.flush()
    today = date.today()
    for ua, u, a in rows:
        session.add(RevueLigne(revue_id=revue.id, user_id=u.id, user_application_id=ua.id, entite_id=u.entite_id,
                               matricule=u.matricule, application=a.nom, note=ua.note, anomalie=_anomalie(u, a, today)))
    session.commit()
    session.refresh(revue)
    audit(account.username, "revue_lancee", target=f"revue/{revue.id}", detail=f"{len(rows)} acces a revoir")
    return revue


def compteurs(session: Session, revue_id: int, scope: Scope) -> dict:
    lignes = session.exec(scope.where(select(RevueLigne).where(RevueLigne.revue_id == revue_id), RevueLigne.entite_id)).all()
    c = {"total": len(lignes), "a_traiter": 0, "maintenu": 0, "a_retirer": 0, "anomalies": 0}
    for l in lignes:
        c[l.decision] += 1
        c["anomalies"] += 1 if l.anomalie else 0
    return c


def decider(session: Session, account: Account, scope: Scope, revue: RevueAcces, ids: list[int], decision: str, commentaire: str | None) -> int:
    if revue.statut != "en_cours":
        raise HTTPException(409, "Cette revue est cloturee : les decisions ne se modifient plus.")
    if decision not in DECISIONS:
        raise HTTPException(400, "Decision inconnue")
    wanted = set(ids)
    lignes = [l for l in session.exec(select(RevueLigne).where(RevueLigne.revue_id == revue.id, RevueLigne.id.in_(wanted))).all()
              if scope.allows(l.entite_id)]
    if not wanted or len(lignes) != len(wanted):
        raise HTTPException(404, "Ligne de revue introuvable")
    now = datetime.utcnow()
    for l in lignes:
        l.decision = decision
        l.commentaire = (commentaire or "").strip() or None
        l.decide_par = account.username if decision != "a_traiter" else None
        l.decide_le = now if decision != "a_traiter" else None
        session.add(l)
    session.commit()
    audit(account.username, "revue_decision", target=f"revue/{revue.id}", detail=f"{len(lignes)} ligne(s) : {decision}")
    return len(lignes)


def _rapport_pdf(session: Session, revue: RevueAcces, lignes: list[RevueLigne], noms: dict) -> bytes:
    styles = getSampleStyleSheet()
    petit = ParagraphStyle("petit", parent=styles["Normal"], fontSize=7, leading=8.5)
    template = load_template(session)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Revue des droits d'acces n{revue.id}", leftMargin=12 * mm, rightMargin=12 * mm)
    c = {"maintenu": 0, "a_retirer": 0}
    for l in lignes:
        c[l.decision] = c.get(l.decision, 0) + 1
    perimetre = revue.perimetre or {}
    entites = ", ".join(noms.get(i, str(i)) for i in perimetre.get("entites", [])) or "toutes les entites"
    story = [
        *header_flowables(template, styles),
        Paragraph(f"Revue des droits d'acces n{revue.id} : {revue.titre}", styles["Title"]),
        Paragraph(f"Perimetre : {entites}. Lancee le {revue.cree_le:%d/%m/%Y} par {revue.cree_par}, cloturee le {datetime.utcnow():%d/%m/%Y}.", styles["Normal"]),
        Paragraph(f"{len(lignes)} acces revus : {c['maintenu']} maintenu(s), {c['a_retirer']} a retirer, "
                  f"{sum(1 for l in lignes if l.anomalie)} anomalie(s) signalee(s) au lancement.", styles["Normal"]),
        Paragraph("Les personnes sont designees par leur matricule. Les acces a retirer passent a \"non\" dans Kikan a la cloture ; le retrait dans "
                  "l'application concernee est suivi et confirme separement.", petit),
        Spacer(1, 5 * mm),
    ]
    data = [["Matricule", "Application", "Entite", "Anomalie", "Decision", "Relu par", "Le", "Commentaire"]]
    for l in lignes:
        data.append([l.matricule or f"id-{l.user_id}", Paragraph(l.application, petit), Paragraph(noms.get(l.entite_id, "-"), petit),
                     Paragraph(l.anomalie or "-", petit), "maintenu" if l.decision == "maintenu" else "A RETIRER",
                     l.decide_par or "-", f"{l.decide_le:%d/%m/%Y}" if l.decide_le else "-", Paragraph((l.commentaire or "-")[:120], petit)])
    table = Table(data, repeatRows=1, colWidths=[24 * mm, 38 * mm, 32 * mm, 36 * mm, 22 * mm, 24 * mm, 20 * mm, 70 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLEU_MARQUE)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP"),
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


def cloturer(session: Session, account: Account, revue: RevueAcces) -> dict:
    if revue.statut != "en_cours":
        raise HTTPException(409, "Cette revue est deja cloturee.")
    lignes = session.exec(select(RevueLigne).where(RevueLigne.revue_id == revue.id).order_by(RevueLigne.id)).all()
    restant = sum(1 for l in lignes if l.decision == "a_traiter")
    if restant:
        raise HTTPException(409, f"{restant} acces restent a traiter : toutes les lignes doivent etre decidees avant la cloture.")
    noms = {e.id: e.nom for e in session.exec(select(Entite)).all()}
    now = datetime.utcnow()
    # Le PDF est scelle et depose AVANT toute ecriture en base : si le stockage echoue, rien n'a change.
    sealed = seal_pdf(_rapport_pdf(session, revue, lignes, noms), reason=f"Revue des droits d'acces n{revue.id}")
    key = f"{now.year}/{now:%Y_%m_%d}_REVUE-ACCES_{revue.id:03d}.pdf"
    ref = store_document(key, sealed, meta_for("Revue des acces", now.year, numero=revue.id, when=now))
    retires = 0
    for l in lignes:
        if l.decision != "a_retirer":
            continue
        l.retrait = "a_faire"
        session.add(l)
        ua = session.get(UserApplication, l.user_application_id) if l.user_application_id else None
        if ua is not None and ua.acces:
            ua.acces = False
            ua.date_maj = now
            session.add(ua)
            retires += 1
    revue.statut = "cloturee"
    revue.cloture_le, revue.cloture_par = now, account.username
    revue.rapport_ref, revue.rapport_empreinte = ref, sha256_hex(sealed)
    session.add(revue)
    session.commit()
    audit(account.username, "revue_cloturee", target=f"revue/{revue.id}", detail=f"{len(lignes)} acces revus, {retires} passe(s) a non, empreinte {revue.rapport_empreinte[:12]}")
    return {"acces_retires": retires, "lignes": len(lignes), "empreinte": revue.rapport_empreinte}


def retraits(session: Session) -> list[dict]:
    rows = session.exec(select(RevueLigne, RevueAcces).join(RevueAcces, RevueAcces.id == RevueLigne.revue_id)
                        .where(RevueLigne.retrait == "a_faire").order_by(RevueAcces.cloture_le, RevueLigne.id)).all()
    noms = {u.id: _libelle(u) for u in session.exec(select(User).where(User.id.in_({l.user_id for l, _ in rows}))).all()} if rows else {}
    return [{"id": l.id, "revue_id": r.id, "revue": r.titre, "cloture_le": r.cloture_le, "matricule": l.matricule, "salarie": noms.get(l.user_id),
             "application": l.application, "commentaire": l.commentaire} for l, r in rows]


def confirmer_retraits(session: Session, account: Account, ids: list[int]) -> int:
    n, now = 0, datetime.utcnow()
    for l in session.exec(select(RevueLigne).where(RevueLigne.id.in_(ids or [0]), RevueLigne.retrait == "a_faire")).all():
        l.retrait, l.retrait_par, l.retrait_le = "fait", account.username, now
        session.add(l)
        n += 1
    session.commit()
    if n:
        audit(account.username, "revue_retrait_confirme", detail=f"{n} retrait(s) confirme(s) dans les systemes")
    return n


def etat_rappels(session: Session, today: date | None = None) -> dict:
    """Compteurs pour les rappels e-mail et le tableau de bord (nombres seulement)."""
    today = today or date.today()
    ouverte = session.exec(select(RevueAcces).where(RevueAcces.statut == "en_cours")).first()
    a_traiter = len(session.exec(select(RevueLigne).where(RevueLigne.revue_id == ouverte.id, RevueLigne.decision == "a_traiter")).all()) if ouverte else 0
    echeance_proche = bool(ouverte and ouverte.echeance and a_traiter and today >= ouverte.echeance - timedelta(days=ECHEANCE_PREAVIS_JOURS))
    derniere = session.exec(select(RevueAcces).where(RevueAcces.statut == "cloturee").order_by(RevueAcces.cloture_le.desc())).first()
    a_des_acces = session.exec(select(UserApplication.id).where(UserApplication.acces == True).limit(1)).first() is not None  # noqa: E712
    annuelle = bool(not ouverte and a_des_acces and (derniere is None or derniere.cloture_le < datetime.combine(today, datetime.min.time()) - timedelta(days=RELANCE_ANNUELLE_JOURS)))
    limite = datetime.combine(today, datetime.min.time()) - timedelta(days=RETRAIT_DELAI_JOURS)
    retraits_attente = sum(1 for l, r in session.exec(select(RevueLigne, RevueAcces).join(RevueAcces, RevueAcces.id == RevueLigne.revue_id)
                                                       .where(RevueLigne.retrait == "a_faire")).all() if r.cloture_le and r.cloture_le < limite)
    return {"revue_ouverte": bool(ouverte), "a_traiter": a_traiter, "echeance_proche": echeance_proche, "annuelle": annuelle,
            "retraits_en_attente": retraits_attente}
