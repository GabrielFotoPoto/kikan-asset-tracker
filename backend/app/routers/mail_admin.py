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

"""Parametrage des e-mails (serveur SMTP, rappels, rapport mensuel) : informatique uniquement."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from .. import appsettings, mailer, reminders
from ..audit import audit
from ..auth import require_roles
from ..db import get_session
from ..mailer import MailError
from ..models import Account

router = APIRouter(prefix="/mail", tags=["mail"], dependencies=[Depends(require_roles("informatique"))])


class MailConfigIn(BaseModel):
    actif: bool = False
    hote: str = Field(default="", max_length=253)
    port: int = Field(default=25, ge=1, le=65535)
    securite: Literal["aucune", "starttls", "ssl"] = "aucune"
    utilisateur: str = Field(default="", max_length=200)
    expediteur: str = Field(default="", max_length=254)
    verifier_cert: bool = True
    liste: str = Field(default="", max_length=254)
    heure: int = Field(default=7, ge=0, le=23)
    renouv: bool = False
    renouv_jours: int = Field(default=90, ge=1, le=730)
    depart: bool = False
    depart_jours: int = Field(default=14, ge=1, le=90)
    nonrestit: bool = False
    nonrestit_sem: int = Field(default=2, ge=1, le=12)
    besoins: bool = False
    besoins_jours: int = Field(default=14, ge=1, le=90)
    rapport: bool = False
    rapport_jour: int = Field(default=1, ge=1, le=28)
    rapport_pj: Literal["aucune", "xlsx", "pdf"] = "aucune"

    @field_validator("hote", "utilisateur", "expediteur", "liste")
    @classmethod
    def strip(cls, v: str) -> str:
        v = (v or "").strip()
        if any(c in v for c in "\r\n\x00"):
            raise ValueError("caractere interdit")
        return v


KEYS = {  # champ de l'API -> cle de reglage
    "actif": "mail_actif", "hote": "mail_hote", "port": "mail_port", "securite": "mail_securite",
    "utilisateur": "mail_utilisateur", "expediteur": "mail_expediteur", "verifier_cert": "mail_verifier_cert",
    "liste": "mail_liste", "heure": "mail_heure", "renouv": "rappel_renouv", "renouv_jours": "rappel_renouv_jours",
    "depart": "rappel_depart", "depart_jours": "rappel_depart_jours", "nonrestit": "rappel_nonrestit",
    "nonrestit_sem": "rappel_nonrestit_sem", "besoins": "rappel_besoins", "besoins_jours": "rappel_besoins_jours", "rapport": "rapport_actif", "rapport_jour": "rapport_jour",
    "rapport_pj": "rapport_pj",
}


def _view(session: Session) -> dict:
    cfg = mailer.load_config(session)
    return {
        "config": {f: getattr(cfg, f) for f in KEYS},
        "mot_de_passe_defini": bool(mailer.password()),
        "lien_defini": bool(mailer.public_url()),
        "pret": cfg.pret,
        "derniere_execution": appsettings.get(session, "mail_derniere_execution"),
        "dernier_resultat": appsettings.get(session, "mail_dernier_resultat"),
        "derniere_erreur": appsettings.get(session, "mail_derniere_erreur"),
    }


@router.get("/config")
def get_config(session: Session = Depends(get_session)):
    return _view(session)


@router.put("/config")
def put_config(data: MailConfigIn, session: Session = Depends(get_session),
               admin: Account = Depends(require_roles("informatique"))):
    if data.hote and not mailer.HOST_RE.match(data.hote):
        raise HTTPException(400, "Nom de serveur invalide")
    if data.expediteur and not mailer.valid_address(data.expediteur):
        raise HTTPException(400, "Adresse d'expediteur invalide")
    if data.liste and not mailer.valid_address(data.liste):
        raise HTTPException(400, "Adresse de liste invalide")
    if data.actif and (not data.hote or not data.expediteur):
        raise HTTPException(400, "Le serveur et l'expediteur sont requis pour activer les e-mails")
    before = mailer.load_config(session)
    changed = []
    for field, key in KEYS.items():
        new = getattr(data, field)
        if getattr(before, field) != new:
            changed.append(field)
        appsettings.put(session, key, ("1" if new else "0") if isinstance(new, bool) else str(new))
    session.commit()
    audit(admin.username, "mail_reglages", detail="champs : " + (", ".join(changed) or "aucun changement"))
    return _view(session)


def _fail(exc: MailError) -> HTTPException:
    return HTTPException(502, str(exc))


@router.post("/test")
def send_test(session: Session = Depends(get_session), admin: Account = Depends(require_roles("informatique"))):
    """Message de test vers l'adresse du compte connecte (a defaut, l'adresse de liste)."""
    cfg = mailer.load_config(session)
    to = (admin.email or "").strip() or cfg.liste
    if not mailer.valid_address(to):
        raise HTTPException(400, "Renseignez l'e-mail de votre compte (page Comptes) ou l'adresse de liste")
    try:
        mailer.send(cfg, [to], "[Kikan] Message de test",
                    "Bonjour,\n\nCe message confirme que Kikan peut envoyer des e-mails via %s:%d.\n" % (cfg.hote, cfg.port))
    except MailError as exc:
        audit(admin.username, "mail_test", status=502, detail="echec")
        raise _fail(exc) from exc
    audit(admin.username, "mail_test", status=200)
    return {"ok": True, "destinataire": to}


@router.get("/apercu")
def preview(session: Session = Depends(get_session)):
    """Ce qui serait envoye maintenant (sans envoyer)."""
    cfg = mailer.load_config(session)
    return {"rappels": reminders.run_reminders(session, cfg, datetime.now(), dry_run=True)["destinataires"],
            "rapport": reminders.report_recipients(session, cfg)}


class RunIn(BaseModel):
    rappels: bool = True
    rapport: bool = False


@router.post("/executer")
def run_now(data: RunIn, session: Session = Depends(get_session),
            admin: Account = Depends(require_roles("informatique"))):
    cfg = mailer.load_config(session)
    if not cfg.actif or not cfg.pret:
        raise HTTPException(409, "Activez et configurez les e-mails d'abord")
    result = reminders.tick(force_rappels=data.rappels, force_rapport=data.rapport, manual=True)
    if result is None:
        raise HTTPException(409, "Un autre cycle est en cours")
    audit(admin.username, "mail_execution_manuelle", detail=", ".join(result) or "rien a envoyer")
    session.expire_all()
    return {"resultat": result, **_view(session)}
