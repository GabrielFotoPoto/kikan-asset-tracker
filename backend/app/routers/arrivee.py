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

"""Parcours d'arrivee d'un salarie (lecture, tous roles authentifies) : fiche, besoins, preparation, remise, acces.

Une seule vue pour les RH (qui ne peuvent pas lire le suivi des besoins) et pour l'informatique : l'avancement est
calcule ici a partir des donnees existantes, sans rien ecrire. La portee par entite s'applique (hors portee : 404).
Sont renvoyes l'etat de chaque etape, les besoins (type, gamme, quantite, statut) et un journal sans nom de compte ni
numero de serie ; jamais le materiel precis choisi par l'informatique.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import get_current_account
from ..db import get_session
from ..models import Application, Assignment, Besoin, Signature, UserApplication
from ..scope import Scope, scope_dep, visible_user

router = APIRouter(prefix="/arrivee", tags=["arrivee"], dependencies=[Depends(get_current_account)])

FAIT, EN_COURS, A_FAIRE = "fait", "en_cours", "a_faire"


def _etape(cle: str, titre: str, qui: str, etat: str, detail: str) -> dict:
    return {"cle": cle, "titre": titre, "qui": qui, "etat": etat, "detail": detail}


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


@router.get("/{user_id}")
def parcours(user_id: int, session: Session = Depends(get_session), scope: Scope = Depends(scope_dep)):
    user = visible_user(session, scope, user_id)
    besoins = session.exec(select(Besoin).where(Besoin.user_id == user_id).order_by(Besoin.id)).all()
    suivis = [b for b in besoins if b.statut != "annule"]
    remises = [a for a in session.exec(select(Assignment).where(Assignment.user_id == user_id)).all()
               if (a.type or "remise") == "remise"]
    signatures: dict[int, datetime] = {}
    if remises:
        for sig in session.exec(select(Signature).where(Signature.assignment_id.in_([a.id for a in remises]))):
            if (sig.audit_json or {}).get("type") != "restitution" and sig.horodatage:
                signatures[sig.assignment_id] = min(sig.horodatage, signatures.get(sig.assignment_id, sig.horodatage))
    apps = {a.id: a.nom for a in session.exec(select(Application)).all()}
    acces = [r for r in session.exec(select(UserApplication).where(UserApplication.user_id == user_id)).all() if r.acces]

    prets = sum(1 for b in suivis if b.statut == "satisfait")
    en_prep = sum(1 for b in suivis if b.statut == "en_preparation")
    signees = [a for a in remises if a.id in signatures]
    non_signees = [a for a in remises if a.id not in signatures]

    if not suivis:
        # Remise creee directement par l'informatique, sans besoin saisi : les deux premieres etapes sont sans objet.
        if remises:
            besoins_e = _etape("besoins", "Besoins saisis", "RH", FAIT, "Remise directe, sans besoin saisi")
            prep_e = _etape("preparation", "Preparation", "Informatique", FAIT, "Materiel remis")
        else:
            besoins_e = _etape("besoins", "Besoins saisis", "RH", A_FAIRE, "Aucun besoin saisi")
            prep_e = _etape("preparation", "Preparation", "Informatique", A_FAIRE, "En attente des besoins")
    else:
        besoins_e = _etape("besoins", "Besoins saisis", "RH", FAIT, f"{len(suivis)} besoin(s)")
        if prets == len(suivis):
            prep_e = _etape("preparation", "Preparation", "Informatique", FAIT, f"{prets} sur {len(suivis)} pret(s)")
        elif prets or en_prep:
            prep_e = _etape("preparation", "Preparation", "Informatique", EN_COURS, f"{prets} sur {len(suivis)} pret(s)")
        else:
            prep_e = _etape("preparation", "Preparation", "Informatique", A_FAIRE, f"{len(suivis)} en attente")
    if signees:
        remise_e = _etape("remise", "Remise signee", "Informatique", FAIT, f"{len(signees)} remise(s) signee(s)")
    elif non_signees:
        remise_e = _etape("remise", "Remise signee", "Informatique", EN_COURS, "Remise creee, a faire signer")
    else:
        remise_e = _etape("remise", "Remise signee", "Informatique", A_FAIRE, "Pas encore de remise")
    acces_e = _etape("acces", "Acces accordes", "RH ou Informatique", FAIT if acces else A_FAIRE,
                     f"{len(acces)} acces" if acces else "Aucun acces accorde")
    etapes = [_etape("fiche", "Fiche creee", "RH", FAIT, user.statut.value if hasattr(user.statut, "value") else str(user.statut)),
              besoins_e, prep_e, remise_e, acces_e]

    courante = next((e for e in etapes if e["etat"] != FAIT), None)
    prochaine = None
    if courante:
        cle = courante["cle"]
        if cle == "besoins":
            prochaine = {"etape": cle, "qui": "rh", "texte": "Saisir les besoins de materiel du salarie.", "vers": "/utilisateurs"}
        elif cle == "preparation":
            prochaine = {"etape": cle, "qui": "informatique", "texte": "Preparer le materiel demande.", "vers": f"/besoins?user={user_id}"}
        elif cle == "remise" and non_signees:
            prochaine = {"etape": cle, "qui": "informatique", "texte": "Faire signer la remise.",
                         "vers": f"/signer/remise/{non_signees[0].id}"}
        elif cle == "remise":
            prochaine = {"etape": cle, "qui": "informatique", "texte": "Creer la remise du materiel.", "vers": "/remises"}
        else:
            prochaine = {"etape": cle, "qui": "rh_ou_informatique", "texte": "Accorder les acces applicatifs.", "vers": "/acces"}

    journal = []
    for b in besoins:
        journal.append({"quand": _iso(b.cree_le), "texte": f"Besoin saisi : {b.type}"})
        if b.statut != "demande" and b.maj_le and b.maj_le != b.cree_le:
            libelle = {"en_preparation": "en preparation", "satisfait": "satisfait", "annule": "annule"}.get(b.statut, b.statut)
            journal.append({"quand": _iso(b.maj_le), "texte": f"Besoin {libelle} : {b.type}"})
    for a in remises:
        journal.append({"quand": _iso(a.date_remise), "texte": "Remise creee"})
        if a.id in signatures:
            journal.append({"quand": _iso(signatures[a.id]), "texte": "Remise signee et scellee"})
    for r in acces:
        journal.append({"quand": _iso(r.date_maj), "texte": f"Acces accorde : {apps.get(r.application_id, '?')}"})
    journal = sorted((j for j in journal if j["quand"]), key=lambda j: j["quand"], reverse=True)[:12]

    return {
        "salarie": {"id": user.id, "nom": user.nom, "prenom": user.prenom, "matricule": user.matricule, "service": user.service,
                    "entite_id": user.entite_id, "statut": user.statut, "date_arrivee": user.date_arrivee},
        "etapes": etapes,
        "etape_courante": courante["cle"] if courante else None,
        "prochaine_action": prochaine,
        "besoins": [{"id": b.id, "type": b.type, "gamme": b.gamme, "quantite": b.quantite, "statut": b.statut} for b in besoins],
        "journal": journal,
    }
