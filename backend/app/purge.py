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

"""Purge RGPD : salaries sortis depuis plus longtemps que la duree de conservation.

Deroulement (bouton reserve a l'informatique, rappel par e-mail si la purge n'est pas faite) :
1. la base est purgee (salarie, remises, signatures, besoins) ; les PDF scelles du salarie sont suivis dans `purge_documents` ;
2. partage SMB, WebDAV ou volume local : le PDF est deplace dans le dossier A_PURGER du meme moteur (quarantaine), puis supprime
   definitivement par Kikan une fois le delai de grace ecoule ;
3. SharePoint et DocuWare : Kikan ne supprime rien, il liste les documents que l'equipe de la GED doit supprimer ; l'informatique confirme ensuite.
Duree de conservation et delai de grace sont des reglages (jamais codes en dur). Le journal ne contient jamais de nom ni de matricule :
seulement des nombres et l'empreinte SHA-256 des PDF supprimes.
"""
import calendar
import logging
from datetime import date, timedelta

from sqlmodel import Session, select

from . import appsettings
from .audit import audit
from .filestore import (
    DOCUMENT_ONLY, StorageError, delete_document, mettre_en_quarantaine, parse_reference, sortir_de_quarantaine,
)
from .models import (
    Assignment, AssignmentAsset, Besoin, EmployeeStatus, PurgeDocument, Signature, User, UserApplication,
)

log = logging.getLogger("kikan.purge")

RETENTION_KEY = "retention_apres_sortie_mois"
GRACE_KEY = "purge_delai_grace_jours"
RETENTION_DEFAUT = 12      # valeurs proposees a l'installation ; modifiables dans la page RGPD
GRACE_DEFAUT = 30
RETENTION_MAX = 240
GRACE_MAX = 365


def _int(session: Session, key: str, default: int) -> int:
    value = appsettings.get(session, key)
    return int(value) if value and value.isdigit() else default


def retention_mois(session: Session) -> int:
    return _int(session, RETENTION_KEY, RETENTION_DEFAUT)


def delai_grace(session: Session) -> int:
    return _int(session, GRACE_KEY, GRACE_DEFAUT)


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def candidats(session: Session, today: date | None = None) -> list[User]:
    """Salaries sortis dont la date de sortie + duree de conservation est atteinte."""
    retention, today = retention_mois(session), today or date.today()
    users = session.exec(select(User).where(User.statut == EmployeeStatus.sorti)).all()
    return [u for u in users if u.date_sortie and add_months(u.date_sortie, retention) <= today]


def _moteur(reference: str) -> str:
    try:
        return parse_reference(reference)[0]
    except StorageError:
        return "inconnu"


def purger(session: Session, actor: str, ids: list[int] | None = None, today: date | None = None) -> dict:
    """Purge la base (ids=None : tous les salaries eligibles ; ids=[] : aucun) puis range les PDF en quarantaine."""
    today = today or date.today()
    selection = candidats(session, today)
    if ids is not None:
        wanted = set(ids)
        selection = [u for u in selection if u.id in wanted]
    echeance = today + timedelta(days=delai_grace(session))
    nb_documents = 0
    for user in selection:
        for besoin in session.exec(select(Besoin).where(Besoin.user_id == user.id)).all():
            session.delete(besoin)  # references une remise : supprimes avant elles
        session.flush()
        for assignment in session.exec(select(Assignment).where(Assignment.user_id == user.id)).all():
            for sig in session.exec(select(Signature).where(Signature.assignment_id == assignment.id)).all():
                if sig.ged_reference:  # suivi dans la meme transaction : jamais de PDF orphelin sans trace
                    moteur = _moteur(sig.ged_reference)
                    session.add(PurgeDocument(reference=sig.ged_reference, moteur=moteur, empreinte=sig.empreinte_doc, echeance=echeance,
                                              statut="ged_a_supprimer" if moteur in DOCUMENT_ONLY else "a_deplacer"))
                    nb_documents += 1
                session.delete(sig)
            for link in session.exec(select(AssignmentAsset).where(AssignmentAsset.assignment_id == assignment.id)).all():
                session.delete(link)
            # Sans relation declaree entre les modeles, l'ordre des suppressions n'est pas garanti : enfants d'abord.
            session.flush()
            session.delete(assignment)
        session.flush()
        for ua in session.exec(select(UserApplication).where(UserApplication.user_id == user.id)).all():
            session.delete(ua)
        session.flush()
        session.delete(user)
    session.commit()
    audit(actor, "rgpd_purge", detail=f"{len(selection)} salarie(s), {nb_documents} document(s) suivis")
    moved = deplacer_en_attente(session, actor)
    return {"count": len(selection), "documents": nb_documents, "deplaces": moved["deplaces"], "en_attente": moved["en_attente"]}


def deplacer_en_attente(session: Session, actor: str) -> dict:
    """Range en quarantaine les PDF de la purge (reessaye a chaque purge tant que le partage est indisponible)."""
    deplaces = en_attente = 0
    for doc in session.exec(select(PurgeDocument).where(PurgeDocument.statut == "a_deplacer").order_by(PurgeDocument.id)).all():
        try:
            doc.reference_quarantaine, digest = mettre_en_quarantaine(doc.reference)
            doc.empreinte = doc.empreinte or digest
            doc.statut = "quarantaine"
            session.add(doc)
            deplaces += 1
        except StorageError as exc:
            if "introuvable" in str(exc).lower():  # deja absent : rien a purger
                audit(actor, "rgpd_document_absent", target=doc.empreinte)
                session.delete(doc)
            else:
                en_attente += 1
                audit(actor, "rgpd_document_non_deplace", detail=type(exc).__name__)
        session.commit()
    return {"deplaces": deplaces, "en_attente": en_attente}


def supprimer_echus(session: Session, actor: str, ids: list[int] | None = None, today: date | None = None) -> dict:
    """Suppression definitive des PDF en quarantaine dont l'echeance est atteinte."""
    today = today or date.today()
    wanted = set(ids) if ids is not None else None
    supprimes = echecs = non_echus = 0
    for doc in session.exec(select(PurgeDocument).where(PurgeDocument.statut == "quarantaine").order_by(PurgeDocument.id)).all():
        if wanted is not None and doc.id not in wanted:
            continue
        if doc.echeance > today:
            non_echus += 1
            continue
        if delete_document(doc.reference_quarantaine):
            audit(actor, "rgpd_document_supprime", target=doc.empreinte, detail=doc.moteur)
            session.delete(doc)
            supprimes += 1
        else:
            echecs += 1
            audit(actor, "rgpd_document_non_supprime", detail=doc.moteur)
        session.commit()
    return {"supprimes": supprimes, "echecs": echecs, "non_echus": non_echus}


def restaurer(session: Session, actor: str, ids: list[int]) -> dict:
    """Remet des PDF de la quarantaine a leur emplacement d'origine (erreur de date de sortie, par exemple)."""
    restaures = echecs = 0
    for doc in session.exec(select(PurgeDocument).where(PurgeDocument.statut == "quarantaine", PurgeDocument.id.in_(ids or [0]))).all():
        try:
            sortir_de_quarantaine(doc.reference_quarantaine)
        except StorageError as exc:
            echecs += 1
            audit(actor, "rgpd_document_non_restaure", detail=type(exc).__name__)
            continue
        audit(actor, "rgpd_document_restaure", target=doc.empreinte, detail=doc.moteur)
        session.delete(doc)
        restaures += 1
        session.commit()
    return {"restaures": restaures, "echecs": echecs}


def confirmer_ged(session: Session, actor: str, ids: list[int]) -> dict:
    """L'equipe de la GED a supprime les documents : Kikan n'en garde que l'empreinte, dans le journal."""
    n = 0
    for doc in session.exec(select(PurgeDocument).where(PurgeDocument.statut == "ged_a_supprimer", PurgeDocument.id.in_(ids or [0]))).all():
        audit(actor, "rgpd_ged_confirme", target=doc.empreinte, detail=doc.moteur)
        session.delete(doc)
        n += 1
    session.commit()
    return {"confirmes": n}


def etat(session: Session, today: date | None = None) -> dict:
    """Compteurs de la purge (page RGPD et rappels par e-mail)."""
    today = today or date.today()
    docs = session.exec(select(PurgeDocument)).all()

    def n(statut, echus=False):
        return sum(1 for d in docs if d.statut == statut and (not echus or d.echeance <= today))

    return {"candidats": len(candidats(session, today)), "a_deplacer": n("a_deplacer"), "quarantaine": n("quarantaine"),
            "quarantaine_echus": n("quarantaine", True), "ged": n("ged_a_supprimer"), "ged_echus": n("ged_a_supprimer", True)}
