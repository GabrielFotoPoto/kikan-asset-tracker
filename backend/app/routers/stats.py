"""Statistiques de parc (lecture, tous roles authentifies)."""
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import get_current_account
from ..db import get_session
from ..models import (
    Asset,
    AssetStatus,
    Assignment,
    AssignmentAsset,
    EmployeeStatus,
    Entite,
    User,
)

router = APIRouter(
    prefix="/stats", tags=["stats"],
    dependencies=[Depends(get_current_account)],
)


@router.get("")
def stats(session: Session = Depends(get_session)):
    assets = session.exec(select(Asset)).all()
    entites = {e.id: e.nom for e in session.exec(select(Entite)).all()}

    # Actif -> salarie detenteur (affectation en cours).
    encours = {a.id: a for a in session.exec(
        select(Assignment).where(Assignment.statut == "en_cours")).all()}
    asset_user = {}
    for link in session.exec(select(AssignmentAsset)).all():
        if link.assignment_id in encours:
            asset_user[link.asset_id] = encours[link.assignment_id].user_id
    users = {u.id: u for u in session.exec(select(User)).all()}

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
    horizon = today + timedelta(days=365)
    renouv = []
    for a in assets:
        if a.echeance_renouvellement and today <= a.echeance_renouvellement <= horizon:
            renouv.append({
                "id": a.id, "identifiant_interne": a.identifiant_interne,
                "type": a.type, "marque": a.marque, "modele": a.modele,
                "echeance": str(a.echeance_renouvellement),
            })
    renouv.sort(key=lambda r: r["echeance"])

    ages = [(today - a.date_achat).days / 365.25 for a in assets if a.date_achat]
    age_moyen = round(sum(ages) / len(ages), 1) if ages else None

    actifs_users = [u for u in users.values() if u.statut == EmployeeStatus.actif]
    equipes = {asset_user[a.id] for a in affecte if a.id in asset_user}
    nb_equipes = sum(1 for u in actifs_users if u.id in equipes)
    taux = round(100 * nb_equipes / len(actifs_users), 1) if actifs_users else 0

    return {
        "actifs_total": len(assets),
        "actifs_par_statut": dict(par_statut),
        "top_modeles": top_modeles,
        "par_entite": [{"entite": k, "count": v} for k, v in par_entite.most_common()],
        "par_service": [{"service": k, "count": v} for k, v in services.most_common()],
        "renouvellements_12m": {"count": len(renouv), "items": renouv},
        "age_moyen_annees": age_moyen,
        "taux_equipement": {
            "salaries_actifs": len(actifs_users),
            "equipes": nb_equipes,
            "pourcentage": taux,
        },
    }
