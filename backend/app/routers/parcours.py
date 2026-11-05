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

"""Parcours guides en etapes (lecture seule, tous roles authentifies dans leur portee).

Parcours de depart d'un salarie (GET /parcours/depart/{user_id}).
L'avancement est calcule a la lecture a partir des donnees existantes, sans aucune ecriture en base.
Hors portee ou inexistant : 404 identique. L'etape 6 (purge RGPD possible) et les motifs de non-restitution
ne sont renvoyes qu'a l'informatique. Ni le matricule ni l'e-mail ne sont renvoyes ; le journal ne contient
ni nom de compte, ni temoin, ni numero de serie, ni motif.
"""
from datetime import date
from typing import NamedTuple

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import get_current_account
from ..db import get_session
from ..models import Account, Asset, AssetStatus, Assignment, AssignmentAsset, EmployeeStatus, Role, Signature, User, UserApplication
from ..parcours import _etape, _iso
from ..purge import add_months, retention_mois
from ..scope import Scope, scope_dep, visible_user

router = APIRouter(prefix="/parcours", tags=["parcours"], dependencies=[Depends(get_current_account)])

FAIT, COURANTE, A_VENIR, SANS_OBJET = "fait", "courante", "a_venir", "sans_objet"
DETAIL_ATTENTE_CLOTURE = "En attente de cloture"


def _charger_donnees_depart(session: Session, user_id: int):
    """Charge en un nombre fixe de requetes les affectations, actifs, signatures et acces du salarie."""
    assignments = session.exec(select(Assignment).where(Assignment.user_id == user_id).order_by(Assignment.id)).all()
    rows: list[tuple[AssignmentAsset, Asset]] = []
    sigs: list[Signature] = []
    if assignments:
        aids = [a.id for a in assignments]
        rows = session.exec(
            select(AssignmentAsset, Asset)
            .join(Asset, Asset.id == AssignmentAsset.asset_id)
            .where(AssignmentAsset.assignment_id.in_(aids))
            .order_by(Asset.id)
        ).all()
        sigs = session.exec(select(Signature).where(Signature.assignment_id.in_(aids)).order_by(Signature.id)).all()
    user_apps = session.exec(select(UserApplication).where(UserApplication.user_id == user_id).order_by(UserApplication.id)).all()

    seen_assets: set[int] = set()
    actifs_detenus: list[Asset] = []
    for link, asset in rows:
        if (asset.statut == AssetStatus.affecte and link.date_retour is None
                and link.non_restitue_le is None and asset.id not in seen_assets):
            seen_assets.add(asset.id)
            actifs_detenus.append(asset)

    retours = [(link, asset) for link, asset in rows if link.date_retour is not None]
    non_restitues_uniques: list[tuple[AssignmentAsset, Asset]] = []
    seen_nr: set[int] = set()
    for link, asset in rows:
        if link.non_restitue_le is not None and asset.id not in seen_nr:
            seen_nr.add(asset.id)
            non_restitues_uniques.append((link, asset))

    sigs_restit = [s for s in sigs if (s.audit_json or {}).get("type") == "restitution" and s.horodatage]
    sigs_echange = [s for s in sigs if (s.audit_json or {}).get("type") == "echange" and s.horodatage]
    nb_acces = sum(1 for r in user_apps if r.acces)
    return actifs_detenus, retours, non_restitues_uniques, sigs_restit, sigs_echange, nb_acces


class EtatDepart(NamedTuple):
    statut_val: str
    depart_declare: bool
    est_sorti: bool
    nb_restants: int
    a_eu_restitution: bool
    a_eu_non_restitue: bool
    nb_acces: int
    today: date


def _construire_etat_depart(
    user: User, nb_restants: int, a_eu_restitution: bool, a_eu_non_restitue: bool, nb_acces: int
) -> EtatDepart:
    statut_val = user.statut.value if hasattr(user.statut, "value") else str(user.statut)
    est_sorti = statut_val == EmployeeStatus.sorti.value
    depart_declare = statut_val in (EmployeeStatus.en_depart.value, EmployeeStatus.sorti.value) and (
        user.date_sortie is not None or est_sorti
    )
    return EtatDepart(
        statut_val=statut_val,
        depart_declare=depart_declare,
        est_sorti=est_sorti,
        nb_restants=nb_restants,
        a_eu_restitution=a_eu_restitution,
        a_eu_non_restitue=a_eu_non_restitue,
        nb_acces=nb_acces,
        today=date.today(),
    )


DETAILS_RESTITUTION = {
    (False, False): "Aucun materiel",
    (True, False): "Restitue (signe)",
    (False, True): "Non restitue (constat)",
    (True, True): "Restitue (signe) et non restitue (constat)",
}


def _detail_restitution(restitue: bool, non_restitue: bool) -> str:
    return DETAILS_RESTITUTION[(bool(restitue), bool(non_restitue))]


def _etapes_materiel_et_sortie(user: User, etat: EtatDepart) -> tuple[dict, dict, dict]:
    """Construit les etapes 2 (materiel), 3 (restitution) et 5 (sorti) lorsque le depart est declare."""
    if etat.nb_restants > 0:
        mat_e = _etape("materiel", "Materiel a recuperer", "Automatique", FAIT, f"{etat.nb_restants} materiel(s) a recuperer")
        retard_jours = (
            (etat.today - user.date_sortie).days
            if (etat.statut_val == EmployeeStatus.en_depart.value and user.date_sortie and user.date_sortie < etat.today)
            else None
        )
        detail_r = f"{etat.nb_restants} materiel(s) restant(s)"
        if retard_jours:
            detail_r += f" - en retard de {retard_jours} jour(s)"
        restit_e = _etape("restitution", "Materiel recupere", "RH ou informatique", COURANTE, detail_r, retard_jours=retard_jours)
        sorti_e = _etape(
            "sorti", "Salarie sorti", "Automatique",
            FAIT if etat.est_sorti else A_VENIR,
            "Sorti" if etat.est_sorti else "En attente de restitution",
        )
        return mat_e, restit_e, sorti_e

    mat_e = (
        _etape("materiel", "Materiel a recuperer", "Automatique", FAIT, "Liste etablie")
        if (etat.a_eu_restitution or etat.a_eu_non_restitue)
        else _etape("materiel", "Materiel a recuperer", "Automatique", SANS_OBJET, "Aucun materiel detenu")
    )
    detail_restit = _detail_restitution(etat.a_eu_restitution, etat.a_eu_non_restitue)
    restit_e = _etape("restitution", "Materiel recupere", "RH ou informatique", FAIT, detail_restit)
    sorti_e = (
        _etape("sorti", "Salarie sorti", "Automatique", FAIT, "Sorti")
        if etat.est_sorti
        else _etape("sorti", "Salarie sorti", "Automatique", A_VENIR, DETAIL_ATTENTE_CLOTURE)
    )
    return mat_e, restit_e, sorti_e


def _etapes_depart(user: User, etat: EtatDepart) -> list[dict]:
    """Construit les 5 etapes communes (1 a 5) du parcours de depart."""
    if not etat.depart_declare:
        return [
            _etape("depart", "Depart declare", "RH ou informatique", COURANTE, "Aucun depart declare"),
            _etape("materiel", "Materiel a recuperer", "Automatique", A_VENIR,
                   f"{etat.nb_restants} materiel(s) detenu(s)" if etat.nb_restants else "Aucun materiel detenu"),
            _etape("restitution", "Materiel recupere", "RH ou informatique", A_VENIR, "En attente du depart"),
            _etape("acces", "Acces applicatifs retires", "RH ou informatique", A_VENIR,
                   f"{etat.nb_acces} acces a retirer" if etat.nb_acces else "Aucun acces actif"),
            _etape("sorti", "Salarie sorti", "Automatique", A_VENIR, "En attente du depart"),
        ]

    depart_e = _etape(
        "depart", "Depart declare", "RH ou informatique", FAIT,
        f"Sortie le {user.date_sortie.isoformat()}" if user.date_sortie else "Depart declare",
    )
    mat_e, restit_e, sorti_e = _etapes_materiel_et_sortie(user, etat)
    acces_e = _etape(
        "acces", "Acces applicatifs retires", "RH ou informatique",
        FAIT if etat.nb_acces == 0 else A_VENIR,
        "Aucun acces actif" if etat.nb_acces == 0 else f"{etat.nb_acces} acces a retirer",
    )
    return [depart_e, mat_e, restit_e, acces_e, sorti_e]


def _etape_purge(session: Session, user: User, today: date) -> dict:
    """Construit l'etape 6 (informative, toujours a_venir), reservee au role informatique."""
    if not user.date_sortie:
        return _etape("purge", "Purge RGPD possible", "Informatique", A_VENIR, "Apres la date de sortie et la duree de retention")
    date_purge = add_months(user.date_sortie, retention_mois(session))
    prep = "depuis le" if date_purge <= today else "a partir du"
    return _etape(
        "purge", "Purge RGPD possible", "Informatique", A_VENIR,
        f"Purge possible {prep} {date_purge.isoformat()}",
        date_purge_possible=date_purge.isoformat(),
    )


def _prochaine_action(
    courante: dict | None,
    etat: EtatDepart,
    user_id: int,
    role: Role,
) -> dict | None:
    """Determine la prochaine action a proposer selon l'etape courante et le role."""
    autorise = role in (Role.rh, Role.informatique)
    if courante:
        cle = courante["cle"]
        if cle == "depart":
            return {
                "etape": cle,
                "qui": "rh_ou_informatique",
                "texte": "Declarer le depart du salarie.",
                "vers": f"/sorties?user={user_id}",
                "autorise": autorise,
            }
        if cle == "restitution":
            return {
                "etape": cle,
                "qui": "rh_ou_informatique",
                "texte": "Recuperer le materiel et faire signer la restitution.",
                "vers": f"/signer/restitution/{user_id}",
                "autorise": autorise,
            }
    if etat.depart_declare and not etat.est_sorti and etat.nb_restants == 0:
        return {
            "etape": "sorti",
            "qui": "rh_ou_informatique",
            "texte": "Cloturer le depart du salarie.",
            "vers": None,
            "action_id": "cloturer_depart",
            "autorise": autorise,
        }
    return None


def _journal_depart(
    sigs_restit: list[Signature],
    sigs_echange: list[Signature],
    retours: list[tuple[AssignmentAsset, Asset]],
    non_restitues: list[tuple[AssignmentAsset, Asset]],
) -> list[dict]:
    """Construit le journal des faits dont la date est reellement stockee (jamais deduite de maj_le ou date_maj)."""
    journal = []
    for sig in sigs_restit:
        journal.append({"quand": _iso(sig.horodatage), "texte": "Restitution signee et scellee"})
    for sig in sigs_echange:
        journal.append({"quand": _iso(sig.horodatage), "texte": "Echange signe et scelle"})
    for link, asset in retours:
        journal.append({"quand": _iso(link.date_retour), "texte": f"Materiel restitue : {asset.type or 'materiel'}"})
    for link, asset in non_restitues:
        journal.append({"quand": _iso(link.non_restitue_le), "texte": f"Constat de non-restitution : {asset.type or 'materiel'}"})
    return sorted((j for j in journal if j["quand"]), key=lambda j: j["quand"], reverse=True)[:12]


def _serialiser_actif(a: Asset) -> dict:
    return {
        "id": a.id,
        "identifiant_interne": a.identifiant_interne,
        "type": a.type,
        "marque": a.marque,
        "modele": a.modele,
        "numero_serie": a.numero_serie,
    }


def _reserves_depart(etat: EtatDepart, nb_non_restitues: int) -> list[str]:
    if not etat.est_sorti:
        return []
    reserves = []
    if etat.nb_acces > 0:
        reserves.append(f"{etat.nb_acces} acces a retirer")
    if etat.a_eu_non_restitue:
        reserves.append(f"{nb_non_restitues} materiel(s) non restitue(s)")
    return reserves


@router.get("/depart/{user_id}")
def parcours_depart(
    user_id: int,
    session: Session = Depends(get_session),
    account: Account = Depends(get_current_account),
    scope: Scope = Depends(scope_dep),
):
    user = visible_user(session, scope, user_id)
    actifs_detenus, retours, non_restitues, sigs_restit, sigs_echange, nb_acces = _charger_donnees_depart(session, user_id)
    etat = _construire_etat_depart(
        user, len(actifs_detenus), bool(sigs_restit or retours), bool(non_restitues), nb_acces
    )
    etapes = _etapes_depart(user, etat)
    if account.role == Role.informatique:
        etapes.append(_etape_purge(session, user, etat.today))

    courante = next((e for e in etapes if e["etat"] == COURANTE), None)
    resultat = {
        "salarie": {
            "id": user.id,
            "nom": user.nom,
            "prenom": user.prenom,
            "service": user.service,
            "entite_id": user.entite_id,
            "statut": etat.statut_val,
            "date_sortie": user.date_sortie.isoformat() if user.date_sortie else None,
        },
        "etapes": etapes,
        "etape_courante": courante["cle"] if courante else None,
        "prochaine_action": _prochaine_action(courante, etat, user_id, account.role),
        "materiel_a_recuperer": [_serialiser_actif(a) for a in actifs_detenus],
        "acces_restants": nb_acces,
        "reserves": _reserves_depart(etat, len(non_restitues)),
        "journal": _journal_depart(sigs_restit, sigs_echange, retours, non_restitues),
    }
    if account.role == Role.informatique:
        resultat["materiels_non_restitues"] = [
            {**_serialiser_actif(a), "motif": link.motif_non_restitution, "constate_le": _iso(link.non_restitue_le)}
            for link, a in non_restitues
        ]
    return resultat
