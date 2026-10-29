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

"""Envoi d'e-mails par un serveur SMTP externe (typiquement interne a l'entreprise) : configuration et transport.

Les reglages sont en base (Parametrage) ; le mot de passe SMTP, s'il en faut un, vient de la variable d'environnement
KIKAN_SMTP_PASSWORD (jamais en base, jamais affiche). Aucun serveur de messagerie n'est embarque.
"""
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from sqlmodel import Session

from . import appsettings

SECURITES = ("aucune", "starttls", "ssl")
PIECES_JOINTES = ("aucune", "xlsx", "pdf")
TIMEOUT_S = 15

HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
ADDR_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")

DEFAULTS = {
    "mail_actif": "0", "mail_hote": "", "mail_port": "25", "mail_securite": "aucune", "mail_utilisateur": "",
    "mail_expediteur": "", "mail_verifier_cert": "1", "mail_liste": "", "mail_heure": "7",
    "rappel_renouv": "0", "rappel_renouv_jours": "90", "rappel_depart": "0", "rappel_depart_jours": "14",
    "rappel_nonrestit": "0", "rappel_nonrestit_sem": "2", "rappel_purge": "1", "rappel_purge_sem": "1", "rappel_besoins": "0", "rappel_besoins_jours": "14",
    "rapport_actif": "0", "rapport_jour": "1", "rapport_pj": "aucune",
}


class MailError(Exception):
    """Echec d'envoi, avec un message sans donnee sensible (ni mot de passe ni contenu)."""


def valid_address(value: str | None) -> bool:
    return bool(value) and len(value) <= 254 and ADDR_RE.match(value) is not None


@dataclass
class MailConfig:
    actif: bool
    hote: str
    port: int
    securite: str
    utilisateur: str
    expediteur: str
    verifier_cert: bool
    liste: str
    heure: int
    renouv: bool
    renouv_jours: int
    depart: bool
    depart_jours: int
    nonrestit: bool
    nonrestit_sem: int
    purge: bool
    purge_sem: int
    besoins: bool
    besoins_jours: int
    rapport: bool
    rapport_jour: int
    rapport_pj: str

    @property
    def pret(self) -> bool:
        return bool(self.hote) and valid_address(self.expediteur)


def password() -> str:
    return os.environ.get("KIKAN_SMTP_PASSWORD", "")


def public_url() -> str:
    return os.environ.get("KIKAN_PUBLIC_URL", "").strip().rstrip("/")


def load_config(session: Session) -> MailConfig:
    def g(key: str) -> str:
        return appsettings.get(session, key, DEFAULTS[key]) or DEFAULTS[key]

    def i(key: str) -> int:
        try:
            return int(g(key))
        except ValueError:
            return int(DEFAULTS[key])

    return MailConfig(
        actif=g("mail_actif") == "1", hote=appsettings.get(session, "mail_hote", "") or "", port=i("mail_port"),
        securite=g("mail_securite") if g("mail_securite") in SECURITES else "aucune",
        utilisateur=appsettings.get(session, "mail_utilisateur", "") or "",
        expediteur=appsettings.get(session, "mail_expediteur", "") or "", verifier_cert=g("mail_verifier_cert") == "1",
        liste=appsettings.get(session, "mail_liste", "") or "", heure=i("mail_heure"),
        renouv=g("rappel_renouv") == "1", renouv_jours=i("rappel_renouv_jours"),
        depart=g("rappel_depart") == "1", depart_jours=i("rappel_depart_jours"),
        nonrestit=g("rappel_nonrestit") == "1", nonrestit_sem=i("rappel_nonrestit_sem"),
        purge=g("rappel_purge") == "1", purge_sem=i("rappel_purge_sem"),
        besoins=g("rappel_besoins") == "1", besoins_jours=i("rappel_besoins_jours"),
        rapport=g("rapport_actif") == "1", rapport_jour=i("rapport_jour"),
        rapport_pj=g("rapport_pj") if g("rapport_pj") in PIECES_JOINTES else "aucune",
    )


def send(cfg: MailConfig, to: list[str], subject: str, body: str,
         attachments: list[tuple[str, str, bytes]] | None = None) -> None:
    """Envoie un message texte. `attachments` : (nom de fichier, type MIME "x/y", contenu)."""
    if not cfg.pret:
        raise MailError("Serveur ou expediteur non configure")
    recipients = [a.strip() for a in to]
    if not recipients or not all(valid_address(a) for a in recipients):
        raise MailError("Adresse de destination invalide")
    msg = EmailMessage()
    try:
        msg["From"] = cfg.expediteur
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
    except ValueError as exc:  # saut de ligne dans un en-tete : jamais accepte
        raise MailError("En-tete invalide") from exc
    msg.set_content(body)
    for name, mime, data in attachments or []:
        main, _, sub = mime.partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=name)

    context = ssl.create_default_context()
    if not cfg.verifier_cert:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        if cfg.securite == "ssl":
            server = smtplib.SMTP_SSL(cfg.hote, cfg.port, timeout=TIMEOUT_S, context=context, local_hostname="kikan")
        else:
            server = smtplib.SMTP(cfg.hote, cfg.port, timeout=TIMEOUT_S, local_hostname="kikan")
        with server:
            if cfg.securite == "starttls":
                server.starttls(context=context)
            if cfg.utilisateur and password():
                server.login(cfg.utilisateur, password())
            server.send_message(msg, from_addr=cfg.expediteur, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError("Authentification SMTP refusee") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError("Destinataire refuse par le serveur") from exc
    except smtplib.SMTPSenderRefused as exc:
        raise MailError("Expediteur refuse par le serveur") from exc
    except ssl.SSLError as exc:
        raise MailError("Echec TLS (certificat ou protocole)") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError("Serveur SMTP injoignable ou erreur de protocole (%s)" % type(exc).__name__) from exc
