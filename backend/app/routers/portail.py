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

"""Routes du portail salarie (/mon-espace/materiel) et provisionnement des comptes demandeurs (lot G4a)."""
from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .. import appsettings, mailer, sso_policy
from ..audit import audit
from ..detentions import actifs_detenus_salarie
from ..auth import (
    audit_actor,
    demandeur_dep,
    generate_temp_password,
    hash_password,
    require_roles,
)
from ..db import engine, get_session
from ..models import Account, Asset, AssetStatus, Assignment, AssignmentAsset, EmployeeStatus, PasswordResetToken, Role, User

router = APIRouter(tags=["portail"])

ACTIVATION_HEURES_KEY = "portail_activation_heures"
ACTIVATION_HEURES_DEFAUT = 72
ACTIVATION_HEURES_MIN = 24
ACTIVATION_HEURES_MAX = 168


def _activation_heures(session: Session) -> int:
    raw = appsettings.get(session, ACTIVATION_HEURES_KEY)
    if raw and raw.isdigit():
        return max(ACTIVATION_HEURES_MIN, min(ACTIVATION_HEURES_MAX, int(raw)))
    return ACTIVATION_HEURES_DEFAUT


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _envoyer_mail_activation(destinataire: str, lien: str, heures: int) -> None:
    subject = "[Kikan] Activation de votre espace salarie"
    body = (
        "Bonjour,\n\n"
        "Un compte d'acces a votre espace salarie Kikan (Mes tickets et Mon materiel) vient d'etre cree.\n"
        f"Definissez votre mot de passe via ce lien (valable {heures} heures) :\n{lien}\n\n"
        "Si vous n'attendiez pas ce message, ignorez-le."
    )
    try:
        with Session(engine) as session:
            cfg = mailer.load_config(session)
            if cfg.actif and cfg.pret:
                mailer.send(cfg, [destinataire], subject, body)
    except Exception as exc:  # noqa: BLE001
        audit("systeme", "portail_mail_activation_echec", detail=type(exc).__name__)


class ProvisionOneRequest(BaseModel):
    mode: str = Field(default="mot_de_passe")  # "mot_de_passe" | "lien"


class ProvisionBatchRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    mode: str = Field(default="mot_de_passe")


def _verifier_creation_locale_autorisee(session: Session) -> None:
    if sso_policy.is_active(session) and sso_policy.read(session).get("mode_local") == "secours":
        raise HTTPException(
            409,
            "Creation de compte demandeur local desactivee : le SSO est actif en mode secours",
        )


def _creer_compte_demandeur(
    session: Session,
    admin: Account,
    user: User,
    mode: str,
    background: BackgroundTasks,
) -> dict:
    if user.statut != EmployeeStatus.actif:
        raise HTTPException(409, "Le salarie n'est pas actif")
    existant = session.exec(select(Account).where(Account.user_id == user.id)).first()
    if existant:
        raise HTTPException(409, "Ce salarie possede deja un compte")

    username = (user.email or "").strip().lower()
    if not username and user.matricule:
        username = f"sal-{user.matricule.strip().lower()}"
    if not username:
        raise HTTPException(422, "Le salarie doit avoir une adresse e-mail ou un matricule")

    if session.exec(select(Account).where(func.lower(Account.username) == username)).first():
        raise HTTPException(409, "Cet identifiant de connexion est deja utilise par un autre compte")

    if mode not in ("mot_de_passe", "lien"):
        raise HTTPException(422, "Mode de provisionnement invalide (mot_de_passe ou lien)")

    if mode == "lien":
        cfg = mailer.load_config(session)
        if not (user.email and cfg.actif and cfg.pret and mailer.public_url()):
            raise HTTPException(422, "Envoi du lien impossible : verifiez l'e-mail du salarie, le SMTP et KIKAN_PUBLIC_URL")

    temp_pw = generate_temp_password()
    acc = Account(
        username=username,
        role=Role.demandeur,
        actif=True,
        hashed_password=hash_password(temp_pw),
        nom_affiche=f"{user.prenom} {user.nom}".strip(),
        email=user.email,
        must_change_password=True,
        source_auth="local",
        secours=False,
        portee_globale=False,
        user_id=user.id,
    )
    session.add(acc)
    session.flush()

    lien_envoye = False
    heures = _activation_heures(session)
    if mode == "lien":
        token = secrets.token_urlsafe(32)
        session.add(PasswordResetToken(
            account_id=acc.id,
            token_hash=_hash_token(token),
            expire_le=datetime.utcnow() + timedelta(hours=heures),
        ))
        lien = f"{mailer.public_url()}/reinitialisation?token={token}"
        background.add_task(_envoyer_mail_activation, user.email, lien, heures)
        lien_envoye = True

    session.commit()
    session.refresh(acc)
    # Audit sans identifiant ni e-mail du salarie : cible pseudonyme dem-<id>
    audit(audit_actor(admin), "portail_compte_cree", target=audit_actor(acc), detail=f"mode={mode}")

    res = {
        "account_id": acc.id,
        "user_id": user.id,
        "role": acc.role.value,
        "mode": mode,
        "lien_envoye": lien_envoye,
    }
    if mode == "mot_de_passe":
        res["username"] = acc.username
        res["mot_de_passe_provisoire"] = temp_pw
    return res


@router.get("/mon-espace/materiel", dependencies=[Depends(require_roles("demandeur"))])
def mon_materiel(
    ctx=Depends(demandeur_dep),
    session: Session = Depends(get_session),
):
    """Lecture seule du materiel actuellement affecte au salarie connecte."""
    _, dem_user = ctx
    return [
        {
            "id": asset.id,
            "identifiant_interne": asset.identifiant_interne,
            "type": asset.type,
            "marque": asset.marque,
            "modele": asset.modele,
            "numero_serie": asset.numero_serie,
            "date_remise": str(assign.date_remise) if assign.date_remise else None,
            "assignment_id": assign.id,
        }
        for asset, assign in actifs_detenus_salarie(session, dem_user.id)
    ]


@router.post("/users/{user_id}/compte-demandeur", status_code=201)
def provision_one_demandeur(
    user_id: int,
    data: ProvisionOneRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    _verifier_creation_locale_autorisee(session)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "Salarie introuvable")
    return _creer_compte_demandeur(session, admin, user, data.mode, background)


@router.post("/users/comptes-demandeurs-lot", status_code=201)
def provision_batch_demandeurs(
    data: ProvisionBatchRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    admin: Account = Depends(require_roles("informatique")),
):
    _verifier_creation_locale_autorisee(session)
    crees = []
    ignores = []
    for uid in dict.fromkeys(data.ids):
        user = session.get(User, uid)
        if not user:
            ignores.append({"user_id": uid, "raison": "Salarie introuvable"})
            continue
        try:
            crees.append(_creer_compte_demandeur(session, admin, user, data.mode, background))
        except HTTPException as exc:
            session.rollback()
            ignores.append({"user_id": uid, "raison": exc.detail})
    return {"crees": crees, "ignores": ignores}
