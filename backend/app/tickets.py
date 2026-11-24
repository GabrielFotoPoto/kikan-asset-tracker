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

"""Service partage du module de tickets natif (lot G1).

Toute la logique metier vit ici (numerotation atomique, validations, transitions sous verrou
PostgreSQL, calcul MTTA/MTTR, notifications e-mail sans texte libre, cloture automatique et
anonymisation RGPD). Les routeurs de session et la future API /v1 ne sont que des couches fines.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from . import appsettings, mailer
from .audit import audit
from .db import engine
from .models import Account, Asset, Assignment, Role, Ticket, TicketComment, TicketCompteur, TicketNature, User, utcnow

log = logging.getLogger("kikan.tickets")

STATUTS = ("nouveau", "en_cours", "en_attente", "resolu", "ferme", "annule")
STATUTS_FINAUX = ("ferme", "annule")
CRITICITES = ("faible", "moyenne", "haute", "critique")
CANAUX = ("portail", "it", "api", "email")
NIVEAUX_SECURITE = ("aucun", "signale", "incident", "sans_suite")

CLOTURE_AUTO_KEY = "tickets_cloture_auto_jours"
CLOTURE_AUTO_DEFAUT = 7
CLOTURE_AUTO_MAX = 90

RETENTION_TICKETS_CLOS_KEY = "retention_tickets_clos_mois"
RETENTION_TICKETS_CLOS_DEFAUT = 24
RETENTION_TICKETS_CLOS_MAX = 120

DELAIS_CIBLES_DEFAUT = {
    "critique": 4,
    "haute": 24,
    "moyenne": 72,
    "faible": 120,
}

# Transitions autorisees pour le role informatique (G1).
TRANSITIONS_IT: dict[str, set[str]] = {
    "nouveau": {"en_cours", "annule"},
    "en_cours": {"en_attente", "resolu"},
    "en_attente": {"en_cours"},
    "resolu": {"en_cours", "ferme"},
    "ferme": set(),
    "annule": set(),
}

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CODE_NATURE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

# Anti-rafale e-mail en memoire (thread-safe) :
# - 1 e-mail max par (ticket_id, destinataire) toutes les 10 minutes
# - plafond horaire global vers la liste IT (30/h)
_MAIL_LOCK = threading.Lock()
_LAST_SENT: dict[tuple[int, str], float] = {}
_IT_HOURLY: list[float] = []
MAIL_COOLDOWN_SEC = 600
MAIL_IT_HOURLY_MAX = 30


def reset_mail_limits() -> None:
    """Reinitialise les compteurs anti-rafale (utile pour les tests)."""
    with _MAIL_LOCK:
        _LAST_SENT.clear()
        _IT_HOURLY.clear()


def nettoyer_texte(val: str | None, max_len: int, *, requis: bool = False, champ: str = "champ") -> str | None:
    if val is None:
        if requis:
            raise HTTPException(422, f"{champ} obligatoire")
        return None
    clean = _CTRL_RE.sub("", val).strip()
    if requis and not clean:
        raise HTTPException(422, f"{champ} obligatoire")
    if len(clean) > max_len:
        raise HTTPException(422, f"{champ} trop long (max {max_len} caracteres)")
    return clean


def valider_code_nature(code: str) -> str:
    c = (code or "").strip().lower()
    if not _CODE_NATURE_RE.match(c):
        raise HTTPException(422, "Code nature invalide (snake_case, 2 a 40 caracteres)")
    return c


def _int_setting(session: Session, key: str, default: int, lo: int, hi: int) -> int:
    raw = appsettings.get(session, key)
    if raw is not None and raw.isdigit():
        return max(lo, min(hi, int(raw)))
    return default


def cloture_auto_jours(session: Session) -> int:
    return _int_setting(session, CLOTURE_AUTO_KEY, CLOTURE_AUTO_DEFAUT, 0, CLOTURE_AUTO_MAX)


def retention_tickets_clos_mois(session: Session) -> int:
    return _int_setting(session, RETENTION_TICKETS_CLOS_KEY, RETENTION_TICKETS_CLOS_DEFAUT, 0, RETENTION_TICKETS_CLOS_MAX)


def delais_cibles(session: Session) -> dict[str, int]:
    return {
        crit: _int_setting(session, f"tickets_delai_{crit}_h", default, 1, 720)
        for crit, default in DELAIS_CIBLES_DEFAUT.items()
    }


def charger_parametres(session: Session) -> dict:
    from . import attachments as att_svc
    return {
        "cloture_auto_jours": cloture_auto_jours(session),
        "delais_cibles_heures": delais_cibles(session),
        "pj_taille_max_mio": att_svc.taille_max_mio(session),
        "pj_plafond_global_mio": att_svc.plafond_global_mio(session),
    }


def sauver_parametres(
    session: Session,
    actor: str,
    cloture_jours: int,
    delais: dict[str, int],
    *,
    pj_taille_max_mio: int | None = None,
    pj_plafond_global_mio: int | None = None,
) -> dict:
    from . import attachments as att_svc
    if not (0 <= cloture_jours <= CLOTURE_AUTO_MAX):
        raise HTTPException(422, f"Delai de cloture auto hors bornes (0 a {CLOTURE_AUTO_MAX} jours)")
    valides: dict[str, int] = {}
    for crit in CRITICITES:
        if crit in delais:
            h = int(delais[crit])
            if not (1 <= h <= 720):
                raise HTTPException(422, f"Delai cible '{crit}' hors bornes (1 a 720 h)")
            valides[crit] = h
    if pj_taille_max_mio is not None and not (att_svc.TAILLE_MAX_MIN_MIO <= pj_taille_max_mio <= att_svc.TAILLE_MAX_MAX_MIO):
        raise HTTPException(422, f"Taille max PJ hors bornes ({att_svc.TAILLE_MAX_MIN_MIO} a {att_svc.TAILLE_MAX_MAX_MIO} Mio)")
    if pj_plafond_global_mio is not None and not (att_svc.PLAFOND_GLOBAL_MIN_MIO <= pj_plafond_global_mio <= att_svc.PLAFOND_GLOBAL_MAX_MIO):
        raise HTTPException(422, f"Plafond global PJ hors bornes ({att_svc.PLAFOND_GLOBAL_MIN_MIO} a {att_svc.PLAFOND_GLOBAL_MAX_MIO} Mio)")

    appsettings.put(session, CLOTURE_AUTO_KEY, str(cloture_jours))
    for crit, h in valides.items():
        appsettings.put(session, f"tickets_delai_{crit}_h", str(h))
    if pj_taille_max_mio is not None:
        appsettings.put(session, att_svc.TAILLE_MAX_KEY, str(pj_taille_max_mio))
    if pj_plafond_global_mio is not None:
        appsettings.put(session, att_svc.PLAFOND_GLOBAL_KEY, str(pj_plafond_global_mio))
    session.commit()
    audit(actor, "tickets_parametres_maj")
    return charger_parametres(session)


def est_hors_delai(ticket: Ticket, delais: dict[str, int], now: datetime | None = None) -> bool:
    if ticket.statut not in ("nouveau", "en_cours"):
        return False
    now = now or utcnow()
    heures = delais.get(ticket.criticite, 72)
    ecoule = (now - ticket.cree_le).total_seconds() - (ticket.duree_attente_sec or 0)
    return ecoule > heures * 3600


def creer_nature(
    session: Session, actor: str, *, code: str, libelle: str,
    signale_securite: bool = False, actif: bool = True, ordre: int = 100,
) -> TicketNature:
    c = valider_code_nature(code)
    if session.exec(select(TicketNature).where(TicketNature.code == c)).first():
        raise HTTPException(409, "Ce code nature existe deja")
    lib = nettoyer_texte(libelle, 100, requis=True, champ="libelle")
    nature = TicketNature(code=c, libelle=lib, signale_securite=signale_securite, actif=actif, ordre=ordre)
    session.add(nature)
    session.commit()
    session.refresh(nature)
    audit(actor, "ticket_nature_creation", target=nature.code)
    return nature


def modifier_nature(
    session: Session, actor: str, nature_id: int, *,
    libelle: str | None = None, signale_securite: bool | None = None,
    actif: bool | None = None, ordre: int | None = None,
) -> TicketNature:
    nature = session.get(TicketNature, nature_id)
    if not nature:
        raise HTTPException(404, "Nature introuvable")
    if libelle is not None:
        nature.libelle = nettoyer_texte(libelle, 100, requis=True, champ="libelle")
    if signale_securite is not None:
        nature.signale_securite = signale_securite
    if actif is not None:
        nature.actif = actif
    if ordre is not None:
        nature.ordre = ordre
    session.add(nature)
    session.commit()
    session.refresh(nature)
    audit(actor, "ticket_nature_maj", target=nature.code)
    return nature


def prochaine_reference(session: Session, annee: int) -> str:
    """Genere TKT-AAAA-NNNN de facon atomique via verrou de ligne sur ticket_compteurs."""
    stmt_ins = (
        pg_insert(TicketCompteur)
        .values(annee=annee, dernier_numero=0)
        .on_conflict_do_nothing(index_elements=["annee"])
    )
    session.exec(stmt_ins)
    cpt = session.exec(
        select(TicketCompteur).where(TicketCompteur.annee == annee).with_for_update()
    ).one()
    cpt.dernier_numero += 1
    session.add(cpt)
    session.flush()
    return f"TKT-{annee}-{cpt.dernier_numero:04d}"


def _copier_materiel(ticket: Ticket, asset: Asset | None) -> None:
    if asset:
        ticket.materiel_type = (asset.type or "")[:100] or None
        ticket.materiel_marque = (asset.marque or "")[:100] or None
        ticket.materiel_modele = (asset.modele or "")[:100] or None
    else:
        ticket.materiel_type = None
        ticket.materiel_marque = None
        ticket.materiel_modele = None


def _valider_assigne(session: Session, account_id: int | None) -> Account | None:
    if account_id is None:
        return None
    acc = session.get(Account, account_id)
    if not acc or not acc.actif or acc.role != Role.informatique:
        raise HTTPException(422, "Le compte assigne doit etre un compte informatique actif")
    return acc


def creer_ticket(
    session: Session,
    actor_account: Account,
    *,
    nature_code: str,
    titre: str,
    description: str | None = None,
    criticite: str = "moyenne",
    user_id: int | None = None,
    asset_id: int | None = None,
    assignment_id: int | None = None,
    assigne_a_account_id: int | None = None,
    canal: str = "it",
    demandeur_verifie: bool = True,
    signaler_securite: bool = False,
) -> Ticket:
    nature = session.exec(select(TicketNature).where(TicketNature.code == nature_code)).first()
    if not nature or not nature.actif:
        raise HTTPException(422, "Nature de ticket inconnue ou inactive")
    if criticite not in CRITICITES:
        raise HTTPException(422, "Criticite invalide")
    if canal not in CANAUX:
        raise HTTPException(422, "Canal invalide")

    clean_titre = nettoyer_texte(titre, 200, requis=True, champ="titre")
    clean_desc = nettoyer_texte(description, 5000, requis=False, champ="description")

    user = session.get(User, user_id) if user_id is not None else None
    if user_id is not None and not user:
        raise HTTPException(404, "Salarie introuvable")

    asset = session.get(Asset, asset_id) if asset_id is not None else None
    if asset_id is not None and not asset:
        raise HTTPException(404, "Materiel introuvable")

    if assignment_id is not None and not session.get(Assignment, assignment_id):
        raise HTTPException(404, "Remise introuvable")

    _valider_assigne(session, assigne_a_account_id)

    # Entite figee a la creation : salarie, sinon materiel, sinon None (ticket interne IT)
    entite_id = (user.entite_id if user and user.entite_id is not None else None)
    if entite_id is None and asset is not None:
        entite_id = asset.entite_id

    now = utcnow()
    ref = prochaine_reference(session, now.year)
    niveau = "signale" if (signaler_securite or nature.signale_securite) else "aucun"

    ticket = Ticket(
        reference=ref,
        entite_id=entite_id,
        user_id=user.id if user else None,
        cree_par_account_id=actor_account.id,
        assigne_a_account_id=assigne_a_account_id,
        asset_id=asset.id if asset else None,
        assignment_id=assignment_id,
        nature_code=nature.code,
        criticite_demandeur=criticite,
        criticite=criticite,
        statut="nouveau",
        titre=clean_titre,
        description=clean_desc,
        canal=canal,
        demandeur_verifie=demandeur_verifie,
        niveau_securite=niveau,
        cree_le=now,
        maj_le=now,
        maj_publique_le=now,
    )
    _copier_materiel(ticket, asset)
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    audit(actor_account.username, "ticket_creation", target=ticket.reference, detail=f"nature={ticket.nature_code} criticite={ticket.criticite}")
    return ticket


def modifier_ticket(
    session: Session,
    actor_account: Account,
    ticket_id: int,
    *,
    nature_code: str | None = None,
    criticite: str | None = None,
    assigne_a_account_id: int | None = None,
    assigne_fourni: bool = False,
    asset_id: int | None = None,
    asset_fourni: bool = False,
    assignment_id: int | None = None,
    assignment_fourni: bool = False,
    demandeur_verifie: bool | None = None,
) -> Ticket:
    ticket = session.exec(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).first()
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in STATUTS_FINAUX:
        raise HTTPException(409, "Un ticket ferme ou annule ne peut plus etre modifie")

    if nature_code is not None:
        nature = session.exec(select(TicketNature).where(TicketNature.code == nature_code)).first()
        if not nature or (not nature.actif and nature.code != ticket.nature_code):
            raise HTTPException(422, "Nature de ticket inconnue ou inactive")
        ticket.nature_code = nature.code
        if nature.signale_securite and ticket.niveau_securite == "aucun":
            ticket.niveau_securite = "signale"

    if criticite is not None:
        if criticite not in CRITICITES:
            raise HTTPException(422, "Criticite invalide")
        ticket.criticite = criticite

    if assigne_fourni:
        _valider_assigne(session, assigne_a_account_id)
        ticket.assigne_a_account_id = assigne_a_account_id

    if asset_fourni:
        if asset_id is None:
            ticket.asset_id = None
            _copier_materiel(ticket, None)
        else:
            asset = session.get(Asset, asset_id)
            if not asset:
                raise HTTPException(404, "Materiel introuvable")
            ticket.asset_id = asset.id
            _copier_materiel(ticket, asset)

    if assignment_fourni:
        if assignment_id is not None and not session.get(Assignment, assignment_id):
            raise HTTPException(404, "Remise introuvable")
        ticket.assignment_id = assignment_id

    if demandeur_verifie is not None:
        ticket.demandeur_verifie = demandeur_verifie

    now = utcnow()
    ticket.maj_le = now
    ticket.maj_publique_le = now
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    audit(actor_account.username, "ticket_maj", target=ticket.reference)
    return ticket


def changer_statut(session: Session, actor_account: Account, ticket_id: int, nouveau_statut: str) -> Ticket:
    if nouveau_statut not in STATUTS:
        raise HTTPException(422, "Statut invalide")
    ticket = session.exec(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).first()
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")

    ancien = ticket.statut
    if nouveau_statut not in TRANSITIONS_IT.get(ancien, set()):
        raise HTTPException(409, f"Transition interdite : {ancien} -> {nouveau_statut}")

    if nouveau_statut == "ferme" and ticket.niveau_securite == "signale":
        raise HTTPException(409, "Cloture refusee : le signalement de securite doit etre qualifie avant cloture")

    now = utcnow()
    if ancien == "nouveau" and nouveau_statut == "en_cours":
        if ticket.premiere_reponse_le is None:
            ticket.premiere_reponse_le = now
        if ticket.assigne_a_account_id is None and actor_account.role == Role.informatique:
            ticket.assigne_a_account_id = actor_account.id
    elif ancien == "nouveau" and nouveau_statut == "annule":
        ticket.ferme_le = now
    elif ancien == "en_cours" and nouveau_statut == "en_attente":
        ticket.en_attente_depuis = now
    elif ancien == "en_attente" and nouveau_statut == "en_cours":
        if ticket.en_attente_depuis is not None:
            delta = max(0, int((now - ticket.en_attente_depuis).total_seconds()))
            ticket.duree_attente_sec += delta
            ticket.en_attente_depuis = None
    elif ancien == "en_cours" and nouveau_statut == "resolu":
        ticket.resolu_le = now
    elif ancien == "resolu" and nouveau_statut == "en_cours":
        ticket.nb_reouvertures += 1
        ticket.resolu_le = None
    elif ancien == "resolu" and nouveau_statut == "ferme":
        ticket.ferme_le = now

    ticket.statut = nouveau_statut
    ticket.maj_le = now
    ticket.maj_publique_le = now
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    audit(actor_account.username, "ticket_statut", target=ticket.reference, detail=f"{ancien}->{nouveau_statut}")
    return ticket


def ajouter_commentaire(
    session: Session,
    actor_account: Account,
    ticket_id: int,
    *,
    contenu: str,
    interne: bool = False,
) -> tuple[Ticket, TicketComment]:
    ticket = session.exec(select(Ticket).where(Ticket.id == ticket_id).with_for_update()).first()
    if not ticket or ticket.anonymise_le is not None:
        raise HTTPException(404, "Ticket introuvable")
    if ticket.statut in STATUTS_FINAUX:
        raise HTTPException(409, "Impossible de commenter un ticket ferme ou annule")

    clean = nettoyer_texte(contenu, 4000, requis=True, champ="contenu")
    now = utcnow()
    comment = TicketComment(
        ticket_id=ticket.id,
        auteur_account_id=actor_account.id,
        interne=bool(interne),
        contenu=clean,
        cree_le=now,
    )
    ticket.maj_le = now
    if not interne:
        ticket.maj_publique_le = now
        if ticket.premiere_reponse_le is None and actor_account.role == Role.informatique:
            ticket.premiere_reponse_le = now

    session.add(comment)
    session.add(ticket)
    session.commit()
    session.refresh(comment)
    session.refresh(ticket)
    audit(actor_account.username, "ticket_commentaire", target=ticket.reference, detail="interne" if interne else "public")
    return ticket, comment


def calculer_mtta_sec(ticket: Ticket) -> int | None:
    if ticket.mtta_sec is not None:
        return ticket.mtta_sec
    if ticket.premiere_reponse_le and ticket.cree_le:
        return max(0, int((ticket.premiere_reponse_le - ticket.cree_le).total_seconds()))
    return None


def calculer_mttr_sec(ticket: Ticket) -> int | None:
    if ticket.mttr_sec is not None:
        return ticket.mttr_sec
    if ticket.resolu_le and ticket.cree_le:
        brut = int((ticket.resolu_le - ticket.cree_le).total_seconds())
        return max(0, brut - (ticket.duree_attente_sec or 0))
    return None


def cloturer_tickets_resolus_echus(session: Session, now: datetime | None = None) -> int:
    """Cloture automatiquement les tickets resolus depuis plus longtemps que le delai configure.

    Exception securite : aucun ticket de niveau 'signale' ou 'incident' n'est clos automatiquement.
    """
    delai = cloture_auto_jours(session)
    if delai <= 0:
        return 0
    now = now or utcnow()
    limite = now - timedelta(days=delai)
    rows = session.exec(
        select(Ticket).where(
            Ticket.statut == "resolu",
            Ticket.anonymise_le == None,  # noqa: E711
            Ticket.resolu_le != None,  # noqa: E711
            Ticket.resolu_le <= limite,
            Ticket.niveau_securite.notin_(("signale", "incident")),
        ).order_by(Ticket.id).with_for_update()
    ).all()
    count = 0
    for ticket in rows:
        ticket.statut = "ferme"
        ticket.ferme_le = now
        ticket.maj_le = now
        ticket.maj_publique_le = now
        session.add(ticket)
        count += 1
    if count:
        session.commit()
        audit("systeme", "tickets_cloture_auto", detail=f"{count} ticket(s)")
    return count


# --- Notifications e-mail immediates (sans texte libre, anti-rafale) ---

def _base_url() -> str:
    return (mailer.public_url() or "").strip().rstrip("/")


def _autoriser_envoi(ticket_id: int, destinataire: str, *, est_it: bool = False) -> bool:
    now_mono = time.monotonic()
    key = (ticket_id, destinataire.strip().lower())
    with _MAIL_LOCK:
        # Purge des entrees expirees pour borner l'empreinte memoire
        expired = [k for k, ts in _LAST_SENT.items() if (now_mono - ts) >= MAIL_COOLDOWN_SEC]
        for k in expired:
            del _LAST_SENT[k]
        if key in _LAST_SENT:
            return False
        if est_it:
            cutoff = now_mono - 3600
            _IT_HOURLY[:] = [t for t in _IT_HOURLY if t > cutoff]
            if len(_IT_HOURLY) >= MAIL_IT_HOURLY_MAX:
                return False
            _IT_HOURLY.append(now_mono)
        _LAST_SENT[key] = now_mono
        return True


def envoyer_notification_ticket(
    ticket_id: int,
    reference: str,
    criticite: str,
    evenement: str,
    destinataire: str,
    *,
    est_it: bool = False,
    cloture_jours: int | None = None,
) -> bool:
    """Envoie un e-mail sobre (reference, evenement, criticite, lien) sans aucun texte libre."""
    dest = (destinataire or "").strip()
    if not dest or "@" not in dest:
        return False

    try:
        with Session(engine) as session:
            cfg = mailer.load_config(session)
            if not cfg.actif or not cfg.pret:
                return False
            if not _autoriser_envoi(ticket_id, dest, est_it=est_it):
                return False

            base = _base_url()
            lien = f"{base}/tickets/{ticket_id}" if base else f"/tickets/{ticket_id}"
            subject = f"[Kikan] Ticket {reference} - {evenement}"
            lignes = [
                f"Reference : {reference}",
                f"Evenement : {evenement}",
                f"Criticite : {criticite}",
                f"Consulter dans Kikan : {lien}",
            ]
            if cloture_jours and cloture_jours > 0:
                lignes.append(
                    f"Sans reponse de votre part sous {cloture_jours} jour(s), ce ticket sera clos automatiquement."
                )
            lignes.append("")
            lignes.append("Pour votre confidentialite, cet e-mail ne contient aucun detail de la demande.")
            body = "\n".join(lignes)
            mailer.send(cfg, [dest], subject, body)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Notification ticket %s non envoyee : %s", reference, type(exc).__name__)
        audit("systeme", "ticket_mail_echec", target=reference, detail=type(exc).__name__)
        return False


# --- Purge RGPD (livree des G1) ---

def _debut_mois(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def anonymiser_ticket(session: Session, ticket: Ticket, now: datetime | None = None) -> bool:
    """Anonymise un ticket, supprime ses commentaires et planifie la quarantaine de ses pieces jointes.

    Idempotent : renvoie False si le ticket est deja anonymise.
    """
    if ticket.anonymise_le is not None:
        return False
    from . import attachments as att_svc, purge as purge_svc

    now = now or utcnow()
    echeance = date.today() + timedelta(days=purge_svc.delai_grace(session))
    att_svc.planifier_purge_attachments(session, "ticket", ticket.id, echeance)

    for comment in session.exec(select(TicketComment).where(TicketComment.ticket_id == ticket.id)).all():
        session.delete(comment)

    if ticket.statut not in STATUTS_FINAUX:
        if ticket.en_attente_depuis is not None:
            ticket.duree_attente_sec += max(0, int((now - ticket.en_attente_depuis).total_seconds()))
            ticket.en_attente_depuis = None
        ticket.statut = "ferme"
        ticket.ferme_le = now

    ticket.mtta_sec = calculer_mtta_sec(ticket)
    ticket.mttr_sec = calculer_mttr_sec(ticket)

    ticket.user_id = None
    ticket.cree_par_account_id = None
    ticket.assigne_a_account_id = None
    ticket.asset_id = None
    ticket.assignment_id = None
    ticket.titre = None
    ticket.description = None
    ticket.reference = f"ANON-{ticket.id}"

    ticket.cree_le = _debut_mois(ticket.cree_le)
    ticket.premiere_reponse_le = _debut_mois(ticket.premiere_reponse_le)
    ticket.en_attente_depuis = None
    ticket.resolu_le = _debut_mois(ticket.resolu_le)
    ticket.ferme_le = _debut_mois(ticket.ferme_le)
    ticket.maj_le = _debut_mois(now)
    ticket.maj_publique_le = _debut_mois(now)
    ticket.anonymise_le = now
    session.add(ticket)
    return True


def purger_tickets_salarie(session: Session, user_id: int, now: datetime | None = None) -> int:
    """Anonymise tous les tickets (ouverts ou clos) d'un salarie avant sa suppression."""
    now = now or utcnow()
    rows = session.exec(
        select(Ticket).where(
            Ticket.user_id == user_id,
            Ticket.anonymise_le == None,  # noqa: E711
        ).order_by(Ticket.id).with_for_update()
    ).all()
    count = 0
    for ticket in rows:
        if anonymiser_ticket(session, ticket, now):
            count += 1
    return count


def candidats_tickets_clos(session: Session, today: date | None = None) -> list[Ticket]:
    """Tickets clos/annules non anonymises dont ferme_le + retention_tickets_clos_mois <= today."""
    from .purge import add_months

    today = today or date.today()
    retention = retention_tickets_clos_mois(session)
    rows = session.exec(
        select(Ticket).where(
            Ticket.statut.in_(STATUTS_FINAUX),
            Ticket.anonymise_le == None,  # noqa: E711
            Ticket.ferme_le != None,  # noqa: E711
        ).order_by(Ticket.ferme_le, Ticket.id)
    ).all()
    return [t for t in rows if t.ferme_le and add_months(t.ferme_le.date(), retention) <= today]


def purger_tickets_clos(
    session: Session,
    actor: str,
    ids: list[int] | None = None,
    today: date | None = None,
) -> int:
    """Anonymise les tickets clos eligibles (ids=None : tous les eligibles ; ids=[] : aucun)."""
    selection = candidats_tickets_clos(session, today)
    if ids is not None:
        wanted = set(ids)
        selection = [t for t in selection if t.id in wanted]
    if not selection:
        return 0
    now = utcnow()
    locked_ids = [t.id for t in selection]
    locked = session.exec(select(Ticket).where(Ticket.id.in_(locked_ids)).order_by(Ticket.id).with_for_update()).all()
    count = 0
    for ticket in locked:
        if anonymiser_ticket(session, ticket, now):
            count += 1
    session.commit()
    if count:
        from . import purge as purge_svc
        audit(actor, "rgpd_purge_tickets", detail=f"{count} ticket(s) anonymise(s)")
        purge_svc.deplacer_en_attente(session, actor)
    return count
