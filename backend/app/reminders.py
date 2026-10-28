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

"""Rappels par e-mail (renouvellements, departs a venir, materiel non restitue) et rapport mensuel.

Un seul recapitulatif par destinataire et par cycle. Les comptes RH ne recoivent que les salaries de leur perimetre
(cloisonnement B2) ; l'informatique et l'adresse de liste recoivent tout. Un rappel deja envoye n'est renvoye qu'a
l'echeance de relance (table reminder_sent). Le planificateur est un fil de l'API ; un verrou consultatif PostgreSQL
garantit qu'un seul processus execute un cycle a la fois.
"""
import logging
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlmodel import Session, select

from . import appsettings, mailer
from .audit import audit
from .db import engine
from .mailer import MailConfig, MailError
from .models import (Account, Asset, AssetStatus, Assignment, AssignmentAsset, Besoin, EmployeeStatus, Entite,
                     ReminderSent, Role, User)
from .scope import GLOBAL, Scope, compute_scope

log = logging.getLogger("kikan.reminders")

LOCK_KEY = 7352001
MAX_MAILS_PER_CYCLE = 100
MAX_LINES = 50
RELANCE_RENOUV_J = 30
RELANCE_DEPART_J = 7


def clean(value) -> str:
    """Texte sur une seule ligne, sans caracteres de controle (donnees saisies par des tiers)."""
    return re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(value if value is not None else "")).strip()


@dataclass
class Recipient:
    email: str
    scope: Scope
    admin: bool          # informatique ou adresse de liste : recoit aussi les renouvellements


@dataclass
class Digest:
    email: str
    subject: str
    body: str
    items: list = field(default_factory=list)   # (kind, cle) a marquer comme envoyes
    counts: dict = field(default_factory=dict)


def recipients(session: Session, cfg: MailConfig) -> list[Recipient]:
    found: dict[str, Recipient] = {}
    accounts = session.exec(select(Account).where(Account.actif == True)).all()  # noqa: E712
    for a in accounts:  # noqa: E712
        mail = (a.email or "").strip().lower()
        if a.role not in (Role.informatique, Role.rh) or not mailer.valid_address(mail):
            continue
        scope = compute_scope(session, a)
        if mail in found:  # meme adresse sur deux comptes : on garde le droit le plus large
            old = found[mail]
            old.admin = old.admin or a.role == Role.informatique
            if scope.globale or (not old.scope.globale and scope.ids > old.scope.ids):
                old.scope = scope
            continue
        found[mail] = Recipient(mail, scope, a.role == Role.informatique)
    liste = (cfg.liste or "").strip().lower()
    if mailer.valid_address(liste):
        found[liste] = Recipient(liste, GLOBAL, True)
    return list(found.values())


def _holdings(session: Session) -> dict[int, list[Asset]]:
    rows = session.exec(
        select(Assignment.user_id, Asset)
        .join(AssignmentAsset, AssignmentAsset.assignment_id == Assignment.id)
        .join(Asset, Asset.id == AssignmentAsset.asset_id)
        .where(Asset.statut == AssetStatus.affecte)
    ).all()
    held: dict[int, dict[int, Asset]] = {}
    for user_id, asset in rows:
        held.setdefault(user_id, {})[asset.id] = asset
    return {uid: list(assets.values()) for uid, assets in held.items()}


def _asset_label(a: Asset) -> str:
    name = clean(a.identifiant_interne or a.numero_serie or ("#%s" % a.id))
    kind = clean(" ".join(x for x in (a.type, a.marque, a.modele) if x))
    return "%s (%s)" % (name, kind) if kind else name


def overdue(u: User, today: date) -> bool:
    """Salarie dont la sortie est passee (ou deja enregistree) et qui detient encore du materiel."""
    if u.statut == EmployeeStatus.sorti:
        return True
    return u.statut != EmployeeStatus.prevu and u.date_sortie is not None and u.date_sortie < today


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def collect(session: Session, cfg: MailConfig, today: date) -> dict[str, list[dict]]:
    """Elements a signaler, par type : {cle, entite_id, ligne}."""
    out: dict[str, list[dict]] = {"renouv": [], "depart": [], "nonrestit": [], "besoins": []}
    if cfg.besoins:
        horizon = today + timedelta(days=cfg.besoins_jours)
        rows = session.exec(select(Besoin, User).join(User, User.id == Besoin.user_id)
                            .where(Besoin.statut.in_(("demande", "en_preparation")))).all()
        for b, u in rows:
            due = b.date_souhaitee or u.date_arrivee
            if due is None or due > horizon:
                continue
            late = due < today
            out["besoins"].append({"cle": "besoin:%d" % b.id, "entite_id": u.entite_id, "ligne":
                                   "- %s %s (%s) : %d x %s, souhaite le %s%s [%s]" % (
                                       clean(u.prenom), clean(u.nom), clean(u.matricule) or "sans matricule", b.quantite,
                                       clean(b.type), _fmt(due), " (date depassee)" if late else "",
                                       "en preparation" if b.statut == "en_preparation" else "a traiter")})
    if cfg.renouv:
        horizon = today + timedelta(days=cfg.renouv_jours)
        for a in session.exec(select(Asset).where(Asset.echeance_renouvellement.is_not(None),
                                                  Asset.echeance_renouvellement <= horizon,
                                                  Asset.statut != AssetStatus.reforme)).all():
            late = a.echeance_renouvellement < today
            out["renouv"].append({"cle": "asset:%d" % a.id, "entite_id": a.entite_id, "ligne": "- %s : echeance %s%s" % (
                _asset_label(a), _fmt(a.echeance_renouvellement), " (depassee)" if late else "")})
    if cfg.depart or cfg.nonrestit:
        held = _holdings(session)
        users = session.exec(select(User).where(User.id.in_(list(held)))).all() if held else []
        for u in users:
            kinds = ", ".join(sorted({clean(a.type) or "materiel" for a in held[u.id]}))
            who = "%s %s (%s)" % (clean(u.prenom), clean(u.nom), clean(u.matricule) or "sans matricule")
            n = len(held[u.id])
            if (cfg.depart and u.statut in (EmployeeStatus.actif, EmployeeStatus.en_depart) and u.date_sortie
                    and today <= u.date_sortie <= today + timedelta(days=cfg.depart_jours)):
                out["depart"].append({"cle": "user:%d" % u.id, "entite_id": u.entite_id, "ligne":
                                      "- %s : sortie le %s, %d materiel(s) a recuperer : %s" % (who, _fmt(u.date_sortie), n, kinds)})
            if cfg.nonrestit and overdue(u, today):
                since = _fmt(u.date_sortie) if u.date_sortie else "date inconnue"
                out["nonrestit"].append({"cle": "user:%d" % u.id, "entite_id": u.entite_id, "ligne":
                                         "- %s : sortie le %s, %d materiel(s) non restitue(s) : %s" % (who, since, n, kinds)})
    return out


TITRES = {
    "renouv": "Materiel dont le renouvellement approche",
    "depart": "Departs a venir avec du materiel a recuperer",
    "nonrestit": "Materiel non restitue apres la date de sortie",
    "besoins": "Besoins de materiel pour des arrivees proches",
}


def digests(session: Session, cfg: MailConfig, now: datetime) -> list[Digest]:
    items = collect(session, cfg, now.date())
    if not any(items.values()):
        return []
    sent: dict[tuple, datetime] = {}
    for r in session.exec(select(ReminderSent).where(ReminderSent.kind.in_(list(TITRES)))).all():
        key = (r.kind, r.cle, r.destinataire)
        if key not in sent or r.envoye_le > sent[key]:
            sent[key] = r.envoye_le
    period = {"renouv": timedelta(days=RELANCE_RENOUV_J), "depart": timedelta(days=RELANCE_DEPART_J),
              "nonrestit": timedelta(weeks=max(1, cfg.nonrestit_sem)), "besoins": timedelta(days=RELANCE_DEPART_J)}
    link = mailer.public_url()
    result = []
    for rcp in recipients(session, cfg):
        sections, marks, counts = [], [], {}
        for kind in ("besoins", "renouv", "depart", "nonrestit"):
            if kind in ("renouv", "besoins") and not rcp.admin:
                continue
            lines = []
            for it in items[kind]:
                if kind != "renouv" and not rcp.scope.allows(it["entite_id"]):
                    continue
                last = sent.get((kind, it["cle"], rcp.email))
                if last is not None and now - last < period[kind]:
                    continue
                lines.append(it["ligne"])
                marks.append((kind, it["cle"]))
            if lines:
                counts[kind] = len(lines)
                extra = ["- ... et %d autre(s) : voir Kikan" % (len(lines) - MAX_LINES)] if len(lines) > MAX_LINES else []
                sections.append("%s (%d)\n%s" % (TITRES[kind], len(lines), "\n".join(lines[:MAX_LINES] + extra)))
        if not sections:
            continue
        body = "Bonjour,\n\nRecapitulatif automatique de Kikan :\n\n" + "\n\n".join(sections)
        if link:
            body += "\n\nAcces a Kikan : %s" % link
        body += "\n\nCe message est genere automatiquement.\n"
        result.append(Digest(rcp.email, "[Kikan] Rappels : %d element(s) a traiter" % len(marks), body, marks, counts))
    return result


def build_report(session: Session, cfg: MailConfig, now: datetime) -> tuple[str, str, list]:
    from .routers import reports  # import tardif : evite une dependance circulaire au demarrage

    assets = session.exec(select(Asset)).all()
    by_status: dict[str, int] = {}
    for a in assets:
        by_status[a.statut.value] = by_status.get(a.statut.value, 0) + 1
    month_start = datetime(now.year, now.month, 1)
    remises = len(session.exec(select(Assignment).where(Assignment.date_remise >= month_start)).all())
    restitutions = len(session.exec(select(Assignment).where(Assignment.date_restitution >= month_start)).all())
    held = _holdings(session)
    holders = session.exec(select(User).where(User.id.in_(list(held)))).all() if held else []
    non_restitues = sum(len(held[u.id]) for u in holders if overdue(u, now.date()))
    horizon = now.date() + timedelta(days=365)
    renouv = len([a for a in assets if a.echeance_renouvellement and now.date() <= a.echeance_renouvellement <= horizon])
    mois = "%02d/%d" % (now.month, now.year)
    body = ("Bonjour,\n\nRapport mensuel Kikan (%s) :\n\n"
            "- Parc : %d materiel(s) (en stock : %d, affectes : %d, rendus : %d, reformes : %d)\n"
            "- Remises ce mois : %d\n- Restitutions ce mois : %d\n"
            "- Materiel non restitue apres la date de sortie : %d\n"
            "- Renouvellements dans les 12 prochains mois : %d\n") % (
        mois, len(assets), by_status.get("stock", 0), by_status.get("affecte", 0), by_status.get("rendu", 0),
        by_status.get("reforme", 0), remises, restitutions, non_restitues, renouv)
    link = mailer.public_url()
    if link:
        body += "\nRapports detailles et exports : %s/rapports\n" % link
    body += "\nCe message est genere automatiquement.\n"
    attachments = []
    if cfg.rapport_pj != "aucune":
        rows = reports._rows(session, None, None, GLOBAL)
        jour = now.date().isoformat()
        if cfg.rapport_pj == "xlsx":
            from . import xlsx_io
            cols = reports.COLUMNS
            data = xlsx_io.build_table("Detentions", [label for _, label in cols],
                                       [[r[key] for key, _ in cols] for r in rows],
                                       date_columns={[k for k, _ in cols].index("date_remise")})
            attachments.append(("kikan-detentions-%s.xlsx" % jour, xlsx_io.XLSX_MIME, data))
        else:
            from .pdf_template import load_template
            attachments.append(("kikan-detentions-%s.pdf" % jour, "application/pdf",
                                reports._pdf(rows, jour, load_template(session))))
    return "[Kikan] Rapport mensuel %s" % mois, body, attachments


def report_recipients(session: Session, cfg: MailConfig) -> list[str]:
    return sorted({r.email for r in recipients(session, cfg) if r.admin})


@contextmanager
def single_runner():
    """Verrou consultatif PostgreSQL : un seul processus execute un cycle a la fois."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        got = bool(conn.execute(text("select pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar())
        try:
            yield got
        finally:
            if got:
                conn.execute(text("select pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def _record(session: Session, ok_msg: str | None, error: str | None) -> None:
    appsettings.put(session, "mail_derniere_execution", datetime.utcnow().isoformat(timespec="seconds"))
    appsettings.put(session, "mail_dernier_resultat", ok_msg)
    appsettings.put(session, "mail_derniere_erreur", error)
    session.commit()


def run_reminders(session: Session, cfg: MailConfig, now: datetime, *, dry_run: bool = False) -> dict:
    """Envoie les rappels dus. Retourne le resume (jamais le contenu des messages)."""
    summary = {"envoyes": 0, "erreurs": [], "destinataires": []}
    for d in digests(session, cfg, now):
        entry = {"destinataire": d.email, "elements": d.counts}
        summary["destinataires"].append(entry)
        if dry_run:
            continue
        if summary["envoyes"] >= MAX_MAILS_PER_CYCLE:
            summary["erreurs"].append("Limite d'envois par cycle atteinte")
            break
        try:
            mailer.send(cfg, [d.email], d.subject, d.body)
        except MailError as exc:
            summary["erreurs"].append("%s : %s" % (d.email, exc))
            continue
        for kind, cle in d.items:
            session.add(ReminderSent(kind=kind, cle=cle, destinataire=d.email, envoye_le=now))
        session.commit()
        summary["envoyes"] += 1
    return summary


def run_report(session: Session, cfg: MailConfig, now: datetime) -> dict:
    to = report_recipients(session, cfg)
    summary = {"envoyes": 0, "erreurs": [], "destinataires": []}
    if not to:
        summary["erreurs"].append("Aucun destinataire (e-mail de compte informatique ou adresse de liste)")
        return summary
    subject, body, attachments = build_report(session, cfg, now)
    for addr in to:
        try:
            mailer.send(cfg, [addr], subject, body, attachments)
            summary["envoyes"] += 1
            summary["destinataires"].append({"destinataire": addr})
        except MailError as exc:
            summary["erreurs"].append("%s : %s" % (addr, exc))
    return summary


def tick(now: datetime | None = None, *, force_rappels: bool = False, force_rapport: bool = False,
         manual: bool = False) -> dict | None:
    """Un passage du planificateur : rappels (une fois par jour apres l'heure choisie) et rapport mensuel.

    `manual` : execution demandee par un administrateur, qui ne fait que ce qui est force (pas le reste du calendrier)."""
    now = now or datetime.now()
    with single_runner() as got:
        if not got:
            return None
        with Session(engine) as session:
            cfg = mailer.load_config(session)
            if not cfg.actif or not cfg.pret:
                return None
            result: dict = {}
            errors: list[str] = []
            today = now.date().isoformat()
            due_time = now.hour >= cfg.heure
            if (cfg.renouv or cfg.depart or cfg.nonrestit or cfg.besoins) and (
                    force_rappels or (not manual and due_time and appsettings.get(session, "mail_dernier_cycle") != today)):
                result["rappels"] = run_reminders(session, cfg, now)
                errors += result["rappels"]["erreurs"]
                if not result["rappels"]["erreurs"] or result["rappels"]["envoyes"]:
                    appsettings.put(session, "mail_dernier_cycle", today)
                if result["rappels"]["envoyes"]:
                    audit("systeme", "rappels_envoyes", detail="%d message(s)" % result["rappels"]["envoyes"])
            month = "%d-%02d" % (now.year, now.month)
            if cfg.rapport and (force_rapport or (not manual and due_time and now.day >= cfg.rapport_jour
                                                  and appsettings.get(session, "mail_dernier_rapport") != month)):
                result["rapport"] = run_report(session, cfg, now)
                errors += result["rapport"]["erreurs"]
                if result["rapport"]["envoyes"]:
                    appsettings.put(session, "mail_dernier_rapport", month)
                    audit("systeme", "rapport_mensuel_envoye", detail="%d message(s)" % result["rapport"]["envoyes"])
            if result:
                sent = sum(r["envoyes"] for r in result.values())
                _record(session, "%d message(s) envoye(s)" % sent, "; ".join(errors)[:500] or None)
            session.commit()
            return result


_stop = threading.Event()


def _loop() -> None:
    while not _stop.wait(300):
        try:
            tick()
        except Exception:  # noqa: BLE001  (le planificateur ne doit jamais s'arreter)
            log.exception("Echec du cycle de rappels")


def start_scheduler() -> None:
    threading.Thread(target=_loop, name="kikan-rappels", daemon=True).start()
