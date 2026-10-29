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

"""Nom des PDF scelles : AAAA_MM_JJ_NOM_PRENOM_ACR_NNN.pdf, range dans le dossier de l'annee (AAAA/).

- AAAA_MM_JJ : date de signature ;
- NOM_PRENOM : en majuscules, sans accents (espaces et apostrophes deviennent des tirets) ;
- ACR : acronyme du salarie (3 lettres, fiche salarie) ;
- NNN : compteur propre au salarie (un par document signe, remise ou restitution, jamais reutilise).
Deux homonymes ont chacun leur compteur : si le nom est tout de meme deja pris, on ajoute -2, -3... (filet de securite).
"""
import re
import unicodedata
from datetime import datetime

from sqlalchemy import update
from sqlmodel import Session, select

from .models import Signature, User


def ascii_maj(value: str | None) -> str:
    """Majuscules sans accents ; tout ce qui n'est pas une lettre ou un chiffre devient un tiret (sans doublon ni tiret aux bouts)."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", "-", text).strip("-")


def acronyme_defaut(prenom: str | None, nom: str | None) -> str:
    """Initiale du prenom + 2 premieres lettres du nom (complete par X) : Gabriel Chollet -> GCH."""
    p = re.sub(r"[^A-Z]", "", ascii_maj(prenom))
    n = re.sub(r"[^A-Z]", "", ascii_maj(nom))
    return ((p[:1] + n[:2]).ljust(3, "X"))[:3] if (p or n) else "XXX"


def normaliser_acronyme(value: str | None) -> str | None:
    """3 lettres majuscules sans accent, ou None si vide ; ValueError sinon."""
    v = ascii_maj(value).replace("-", "")
    if not v:
        return None
    if not re.fullmatch(r"[A-Z]{3}", v):
        raise ValueError("L'acronyme doit comporter exactement 3 lettres")
    return v


_CLE_RE = re.compile(r"^(\d{4}/\d{4}_\d{2}_\d{2})_.+?(_[A-Z]{3}_\d{3}(?:-\d+)?\.pdf)$")


def cle_sans_nom(key: str) -> str:
    """Cle sans NOM_PRENOM (2026/2026_11_02_GCH_003.pdf) : valeur du champ d'index "cle" des moteurs qui indexent."""
    m = _CLE_RE.match(key or "")
    return m.group(1) + m.group(2) if m else key


def assurer_acronyme(user: User) -> str:
    if not user.acronyme:
        user.acronyme = acronyme_defaut(user.prenom, user.nom)
    return user.acronyme


def prochain_numero(session: Session, user: User) -> int:
    """Incremente le compteur du salarie (verrou de ligne : deux signatures simultanees ne partagent pas un numero)."""
    res = session.execute(update(User).where(User.id == user.id)
                          .values(compteur_documents=User.compteur_documents + 1).returning(User.compteur_documents))
    numero = res.scalar_one()
    user.compteur_documents = numero
    return numero


def nom_document(session: Session, user: User, when: datetime) -> str:
    """Cle de stockage du prochain document scelle du salarie (alloue son numero)."""
    acr = assurer_acronyme(user)
    numero = prochain_numero(session, user)
    base = f"{when:%Y_%m_%d}_{ascii_maj(user.nom) or 'X'}_{ascii_maj(user.prenom) or 'X'}_{acr}_{numero:03d}"
    key, n = f"{when.year}/{base}.pdf", 1
    while session.exec(select(Signature.id).where(Signature.ged_reference.like(f"%:{key}"))).first() is not None:
        n += 1
        key = f"{when.year}/{base}-{n}.pdf"
    return key
