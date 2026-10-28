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

"""Moteur d'integration : creation, liaison et mise a jour du materiel et des salaries venus d'un systeme externe.

Partage par l'API d'import par jetons (/v1) et par le connecteur GLPI. Regles communes :
- jamais de suppression, jamais de changement de statut d'un materiel ni de statut d'un salarie ;
- un element deja connu (meme numero de serie, meme matricule ou meme e-mail) est LIE, pas duplique, et n'est pas modifie ;
- un element lie n'est mis a jour que s'il n'a pas ete modifie a la main depuis la derniere synchronisation (empreinte) ;
- une fiche salarie n'est jamais ecrasee : seuls ses champs vides sont completes ;
- le perimetre (entites) de l'appelant est respecte : hors perimetre, l'element est refuse sans rien reveler.
"""
import hashlib
import json
import re
from datetime import date, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from .asset_catalog import AssetCatalog
from .catalogs import canonical_service, canonical_type
from .models import Asset, AssetStatus, EmployeeStatus, Entite, ExternalLink, User
from .scope import Scope

ASSET_FIELDS = ("type", "marque", "modele", "numero_serie", "identifiant_interne", "date_achat", "fin_garantie",
                "echeance_renouvellement", "notes")
USER_FIELDS = ("matricule", "nom", "prenom", "email", "service", "date_arrivee")


def clean(value, limit: int = 200) -> str | None:
    text = re.sub(r"[\x00-\x1f\x7f\s]+", " ", str(value) if value is not None else "").strip()[:limit]
    return text or None


def _fp(values: dict) -> str:
    payload = json.dumps({k: (str(v) if v is not None else None) for k, v in sorted(values.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def asset_fp(a: Asset) -> str:
    return _fp({**{f: getattr(a, f) for f in ASSET_FIELDS}, "entite_id": a.entite_id})


def get_link(session: Session, systeme: str, objet: str, externe_id: str) -> ExternalLink | None:
    return session.exec(select(ExternalLink).where(ExternalLink.systeme == systeme, ExternalLink.objet == objet,
                                                   ExternalLink.externe_id == externe_id)).first()


def link_of(session: Session, systeme: str, objet: str, kikan_id: int) -> ExternalLink | None:
    return session.exec(select(ExternalLink).where(ExternalLink.systeme == systeme, ExternalLink.objet == objet,
                                                   ExternalLink.kikan_id == kikan_id)).first()


def resolve_entite(session: Session, scope: Scope, item: dict) -> tuple[int | None, str | None]:
    """(id d'entite, motif de refus). Un jeton limite a des entites doit toujours en preciser une."""
    entite = None
    if item.get("entite_id") is not None:
        entite = session.get(Entite, item["entite_id"])
    elif item.get("entite_code"):
        entite = session.exec(select(Entite).where(Entite.code == item["entite_code"])).first()
    if (item.get("entite_id") is not None or item.get("entite_code")) and entite is None:
        return None, "Entite inconnue"
    if entite is not None:
        if not scope.allows(entite.id):
            return None, "Entite hors perimetre"
        return entite.id, None
    if not scope.globale:
        return None, "Une entite est requise"
    return None, None


def _result(externe_id, resultat, kikan_id=None, message=None, ignores=None) -> dict:
    out = {"id_externe": externe_id, "resultat": resultat, "id": kikan_id}
    if message:
        out["message"] = message
    if ignores:
        out["champs_ignores"] = ignores
    return out


def _canon_asset_values(session: Session, item: dict) -> dict:
    values = {f: item.get(f) for f in ASSET_FIELDS}
    for f in ("type", "marque", "modele", "numero_serie", "identifiant_interne", "notes"):
        values[f] = clean(values[f], 500 if f == "notes" else 100)
    if values["type"]:
        values["type"] = canonical_type(session, values["type"])
    catalog = AssetCatalog(session)
    values["marque"] = catalog.canon_marque(values["marque"])
    values["modele"] = catalog.canon_modele(values["marque"], values["modele"])
    for f in ("date_achat", "fin_garantie", "echeance_renouvellement"):
        v = values[f]
        values[f] = v if isinstance(v, date) and not isinstance(v, datetime) else None
    return values


def upsert_asset(session: Session, systeme: str, scope: Scope, item: dict, *, allow_update: bool = True) -> dict:
    """Cree, lie ou met a jour un materiel. Retourne le resultat de l'element (cree, lie, modifie, inchange, conflit, refuse)."""
    ext = clean(item.get("id_externe"), 100)
    if not ext:
        return _result(None, "refuse", message="id_externe requis")
    if not clean(item.get("type"), 100):
        return _result(ext, "refuse", message="Type requis")
    entite_id, err = resolve_entite(session, scope, item)
    if err:
        return _result(ext, "refuse", message=err)
    values = _canon_asset_values(session, item)
    link = get_link(session, systeme, "asset", ext)

    if link is not None:
        asset = session.get(Asset, link.kikan_id)
        if asset is None or not scope.allows(asset.entite_id):
            return _result(ext, "refuse", message="Element hors perimetre")
        if not allow_update:
            return _result(ext, "inchange", asset.id)
        if link.empreinte and link.empreinte != asset_fp(asset):
            return _result(ext, "conflit", asset.id, "Modifie dans Kikan depuis la derniere synchronisation : non ecrase")
        changes = {f: v for f, v in values.items() if v is not None and getattr(asset, f) != v}
        if entite_id is not None and asset.entite_id != entite_id:
            changes["entite_id"] = entite_id
        serial = changes.get("numero_serie")
        if serial and session.exec(select(Asset).where(func.lower(Asset.numero_serie) == serial.lower(), Asset.id != asset.id)).first():
            return _result(ext, "refuse", asset.id, "Numero de serie deja utilise par un autre materiel")
        interne = changes.get("identifiant_interne")
        if interne and session.exec(select(Asset).where(Asset.identifiant_interne == interne, Asset.id != asset.id)).first():
            return _result(ext, "refuse", asset.id, "Identifiant interne deja utilise par un autre materiel")
        if not changes:
            return _result(ext, "inchange", asset.id)
        for f, v in changes.items():
            setattr(asset, f, v)
        asset.maj_le = datetime.utcnow()
        session.add(asset)
        session.flush()
        link.empreinte, link.synchro_le = asset_fp(asset), datetime.utcnow()
        session.add(link)
        return _result(ext, "modifie", asset.id, "champs : " + ", ".join(sorted(changes)))

    serial = values["numero_serie"]
    found = session.exec(select(Asset).where(func.lower(Asset.numero_serie) == serial.lower())).first() if serial else None
    if found is not None:
        if not scope.allows(found.entite_id):
            return _result(ext, "refuse", message="Correspondance hors perimetre")
        other = link_of(session, systeme, "asset", found.id)
        if other is not None:
            return _result(ext, "conflit", found.id, f"Ce numero de serie est deja lie a l'identifiant externe {other.externe_id}")
        session.add(ExternalLink(systeme=systeme, objet="asset", kikan_id=found.id, externe_id=ext, empreinte=asset_fp(found)))
        session.flush()
        return _result(ext, "lie", found.id, "Materiel existant (meme numero de serie) : lie sans modification")
    interne = values["identifiant_interne"]
    if interne and session.exec(select(Asset).where(Asset.identifiant_interne == interne)).first():
        return _result(ext, "refuse", message="Identifiant interne deja utilise")

    asset = Asset(**values, statut=AssetStatus.stock, source=systeme, id_externe=ext, entite_id=entite_id)
    session.add(asset)
    session.flush()
    session.add(ExternalLink(systeme=systeme, objet="asset", kikan_id=asset.id, externe_id=ext, empreinte=asset_fp(asset)))
    session.flush()
    return _result(ext, "cree", asset.id)


def _same_person(session: Session, nom: str, prenom: str) -> User | None:
    return session.exec(select(User).where(func.lower(User.nom) == nom.lower(), func.lower(User.prenom) == prenom.lower())).first()


def match_user(session: Session, item: dict) -> tuple[User | None, str | None]:
    """Salarie deja connu : (fiche, critere). Matricule, puis e-mail ; le meme nom et prenom n'est qu'un doublon possible."""
    matricule = clean(item.get("matricule"), 50)
    if matricule:
        u = session.exec(select(User).where(User.matricule == matricule)).first()
        if u:
            return u, "matricule"
    email = clean(item.get("email"), 200)
    if email:
        u = session.exec(select(User).where(func.lower(User.email) == email.lower())).first()
        if u:
            return u, "email"
    nom, prenom = clean(item.get("nom")), clean(item.get("prenom"))
    if nom and prenom:
        u = _same_person(session, nom, prenom)
        if u:
            return u, "nom"
    return None, None


def _fill_user(session: Session, user: User, item: dict, entite_id: int | None) -> tuple[list[str], list[str]]:
    """Complete les champs vides de la fiche. Retourne (champs completes, champs differents laisses tels quels)."""
    filled, ignored = [], []
    incoming = {f: clean(item.get(f), 200) for f in ("matricule", "nom", "prenom", "email", "service")}
    if incoming["service"]:
        incoming["service"] = canonical_service(session, incoming["service"])
    arrivee = item.get("date_arrivee")
    incoming["date_arrivee"] = arrivee if isinstance(arrivee, date) and not isinstance(arrivee, datetime) else None
    for f, v in incoming.items():
        if v is None:
            continue
        current = getattr(user, f)
        if current in (None, ""):
            setattr(user, f, v)
            filled.append(f)
        elif str(current).lower() != str(v).lower():
            ignored.append(f)
    if entite_id is not None and user.entite_id is None:
        user.entite_id = entite_id
        filled.append("entite")
    elif entite_id is not None and user.entite_id != entite_id:
        ignored.append("entite")
    if filled:
        user.maj_le = datetime.utcnow()
        session.add(user)
        session.flush()
    return filled, ignored


def upsert_user(session: Session, systeme: str, scope: Scope, item: dict, *, create: bool = True, link_by_name: bool = False) -> dict:
    """Cree ou lie un salarie ; ne complete que les champs vides d'une fiche existante (jamais d'ecrasement)."""
    ext = clean(item.get("id_externe"), 100)
    if not ext:
        return _result(None, "refuse", message="id_externe requis")
    entite_id, err = resolve_entite(session, scope, item)
    if err:
        return _result(ext, "refuse", message=err)
    link = get_link(session, systeme, "user", ext)
    user, how = (session.get(User, link.kikan_id), "lien") if link else match_user(session, item)
    if user is not None and how == "nom":
        choix = item.get("homonyme")  # decision explicite de l'appelant : "lier" a la fiche existante ou "creer" un homonyme
        if choix == "creer":
            user = None
        elif choix != "lier" and not link_by_name:
            return _result(ext, "conflit", user.id, "Un salarie porte deja ce nom et ce prenom : choisissez homonyme = lier ou creer")
    if user is not None:
        if not scope.allows(user.entite_id):
            return _result(ext, "refuse", message="Correspondance hors perimetre")
        if link is None:
            other = link_of(session, systeme, "user", user.id)
            if other is not None:
                return _result(ext, "conflit", user.id, f"Ce salarie est deja lie a l'identifiant externe {other.externe_id}")
            session.add(ExternalLink(systeme=systeme, objet="user", kikan_id=user.id, externe_id=ext))
        filled, ignored = _fill_user(session, user, item, entite_id)
        status = "lie" if link is None else ("modifie" if filled else "inchange")
        if link is None and filled:
            status = "lie"
        session.flush()
        msg = ("Salarie existant (" + (how or "") + ") lie ; champs completes : " + ", ".join(filled)) if link is None and filled else None
        return _result(ext, status, user.id, msg, ignored)
    if not create:
        return _result(ext, "refuse", message="Creation non autorisee")
    nom, prenom = clean(item.get("nom")), clean(item.get("prenom"))
    if not nom or not prenom:
        return _result(ext, "refuse", message="Nom et prenom requis")
    arrivee = item.get("date_arrivee") if isinstance(item.get("date_arrivee"), date) else None
    service = canonical_service(session, clean(item.get("service"), 100))
    user = User(matricule=clean(item.get("matricule"), 50), nom=nom, prenom=prenom, email=clean(item.get("email")), service=service,
                entite_id=entite_id, date_arrivee=arrivee,
                statut=EmployeeStatus.prevu if arrivee and arrivee > date.today() else EmployeeStatus.actif)
    session.add(user)
    session.flush()
    session.add(ExternalLink(systeme=systeme, objet="user", kikan_id=user.id, externe_id=ext))
    session.flush()
    return _result(ext, "cree", user.id)
