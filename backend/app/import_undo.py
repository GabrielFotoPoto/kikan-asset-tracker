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

"""Annulation d'un import (page Import).

L'import ne fait que CREER des lignes : annuler revient a supprimer ce que le lot a cree, tant que rien ne s'en sert.
Chaque import reel enregistre un lot (identifiants des lignes creees, via l'evenement after_flush de la session : seules les lignes
inserees par l'import sont rattachees au lot, meme si d'autres personnes travaillent en parallele). L'annulation est tout ou rien :
un seul element utilise ailleurs la refuse, avec la liste de ce qui bloque.
"""
from datetime import datetime

from sqlalchemy import event
from sqlmodel import Session, select

from .models import (
    AccountScope, ApiTokenScope, Application, Asset, AssetStatus, Assignment, AssignmentAsset, Besoin, Entite, ExternalLink,
    ImportLot, Policy, Signature, User, UserApplication,
)
from .rules import count

# type suivi -> modele ; l'ordre est celui de la suppression (dependants d'abord)
TRACKED = {
    "acces": UserApplication, "affectation_actif": AssignmentAsset, "affectation": Assignment,
    "actif": Asset, "salarie": User, "application": Application, "entite": Entite,
}
LABELS = {"acces": "acces applicatif(s)", "affectation": "affectation(s)", "actif": "actif(s)", "salarie": "salarie(s)",
          "application": "application(s)", "entite": "entite(s)"}


class Tracker:
    """Collecte les lignes inserees pendant l'import (a utiliser avant le premier flush de l'import)."""

    def __init__(self, session: Session):
        self.session = session
        self.ids: dict[str, list] = {k: [] for k in TRACKED}
        event.listen(session, "after_flush", self._grab)

    def _grab(self, session, _ctx):
        for obj in list(session.new):
            for key, model in TRACKED.items():
                if isinstance(obj, model):
                    if key == "affectation_actif":
                        self.ids[key].append([obj.assignment_id, obj.asset_id])
                    else:
                        self.ids[key].append(obj.id)

    def close(self):
        event.remove(self.session, "after_flush", self._grab)

    def total(self) -> int:
        return sum(len(v) for k, v in self.ids.items() if k != "affectation_actif")


def snapshot_statuts(session: Session) -> dict[str, str]:
    """Statuts des actifs avant un import d'affectations (pour les remettre en cas d'annulation)."""
    return {str(a.id): a.statut.value for a in session.exec(select(Asset)).all()}


def record(session: Session, kind: str, account: str, digest: str, tracker: Tracker, statuts: dict | None) -> ImportLot | None:
    if tracker.total() == 0:
        return None
    elements = {"ids": {k: v for k, v in tracker.ids.items() if v}}
    if statuts is not None:
        used = {str(aid) for _, aid in tracker.ids["affectation_actif"]}
        elements["statuts_actifs"] = {k: v for k, v in statuts.items() if k in used}
    lot = ImportLot(kind=kind, cree_par=account, sha256=digest, nb_creees=tracker.total(), elements=elements)
    session.add(lot)
    return lot


def _ids(lot: ImportLot, key: str) -> list:
    return (lot.elements or {}).get("ids", {}).get(key, [])


def analyser(session: Session, lot: ImportLot) -> dict:
    """Ce qui serait supprime et ce qui bloque (aucune ecriture)."""
    bloquants: list[str] = []
    a_supprimer: dict[str, int] = {}
    absents = 0

    def existing(model, key):
        nonlocal absents
        rows = [session.get(model, i) for i in _ids(lot, key)]
        found = [r for r in rows if r is not None]
        absents += len(rows) - len(found)
        return found

    def bloque(texte: str, n: int):
        if n:
            bloquants.append(f"{n} {texte}")

    acces = existing(UserApplication, "acces")
    a_supprimer["acces"] = len(acces)

    assignments = existing(Assignment, "affectation")
    a_supprimer["affectation"] = len(assignments)
    ids_aff = {a.id for a in assignments}
    bloque("affectation(s) deja signee(s) (le PDF scelle existe)",
           sum(1 for a in assignments if count(session, Signature, Signature.assignment_id == a.id)))
    bloque("affectation(s) deja restituee(s)", sum(1 for a in assignments if a.date_restitution is not None))
    bloque("affectation(s) qui ont solde un besoin de materiel",
           sum(1 for a in assignments if count(session, Besoin, Besoin.assignment_id == a.id)))

    actifs = existing(Asset, "actif")
    a_supprimer["actif"] = len(actifs)
    lies = lambda aid: [x for x in session.exec(select(AssignmentAsset).where(AssignmentAsset.asset_id == aid)).all()
                        if x.assignment_id not in ids_aff]
    bloque("actif(s) affecte(s) depuis l'import", sum(1 for a in actifs if lies(a.id)))
    bloque("actif(s) lie(s) a GLPI ou a un systeme externe",
           sum(1 for a in actifs if count(session, ExternalLink, ExternalLink.objet == "asset", ExternalLink.kikan_id == a.id)))

    salaries = existing(User, "salarie")
    a_supprimer["salarie"] = len(salaries)
    ids_acces = {x.id for x in acces}
    bloque("salarie(s) avec des affectations",
           sum(1 for u in salaries if any(x.id not in ids_aff for x in session.exec(select(Assignment).where(Assignment.user_id == u.id)).all())))
    bloque("salarie(s) avec des acces applicatifs",
           sum(1 for u in salaries if any(x.id not in ids_acces for x in session.exec(select(UserApplication).where(UserApplication.user_id == u.id)).all())))
    bloque("salarie(s) avec des besoins de materiel", sum(1 for u in salaries if count(session, Besoin, Besoin.user_id == u.id)))
    bloque("salarie(s) lie(s) a GLPI ou a un systeme externe",
           sum(1 for u in salaries if count(session, ExternalLink, ExternalLink.objet == "user", ExternalLink.kikan_id == u.id)))

    applications = existing(Application, "application")
    a_supprimer["application"] = len(applications)
    bloque("application(s) avec des acces attribues",
           sum(1 for a in applications if any(x.id not in ids_acces for x in session.exec(select(UserApplication).where(UserApplication.application_id == a.id)).all())))

    entites = existing(Entite, "entite")
    a_supprimer["entite"] = len(entites)
    ids_ent, codes_ent = {e.id for e in entites}, {e.code for e in entites}
    ids_sal = {u.id for u in salaries}
    ids_act = {a.id for a in actifs}
    ids_app = {a.id for a in applications}
    for label, model, field, own in (("salarie(s)", User, User.entite_id, ids_sal), ("actif(s)", Asset, Asset.entite_id, ids_act),
                                     ("application(s)", Application, Application.entite_id, ids_app)):
        bloque(f"entite(s) utilisee(s) par des {label} hors de l'import",
               sum(1 for e in entites if any(x.id not in own for x in session.exec(select(model).where(field == e.id)).all())))
    bloque("entite(s) qui portent une charte", sum(1 for e in entites if count(session, Policy, Policy.entite_id == e.id)))
    bloque("entite(s) mere(s) d'entites creees ailleurs",
           sum(1 for e in entites if any(c.code not in codes_ent for c in session.exec(select(Entite).where(Entite.code_parent == e.code)).all())))
    bloque("entite(s) dans le perimetre d'un compte ou d'un jeton d'API",
           sum(1 for e in entites if count(session, AccountScope, AccountScope.entite_id == e.id)
               or count(session, ApiTokenScope, ApiTokenScope.entite_id == e.id)))
    del ids_ent

    return {"annulable": lot.statut == "actif" and not bloquants, "statut": lot.statut,
            "a_supprimer": {k: v for k, v in a_supprimer.items() if v}, "deja_absents": absents, "bloquants": bloquants}


def annuler(session: Session, lot: ImportLot, account: str) -> dict:
    """Supprime ce que le lot a cree (l'appelant a verifie `analyser`). Valide en une seule transaction."""
    statuts = (lot.elements or {}).get("statuts_actifs", {})
    for aid, prev in statuts.items():  # les actifs remis par un import d'affectations reprennent leur statut d'avant
        asset = session.get(Asset, int(aid))
        if asset is not None and asset.statut == AssetStatus.affecte:
            asset.statut = AssetStatus(prev)
            session.add(asset)
    supprimes = 0
    for key, model in TRACKED.items():  # ordre : dependants d'abord
        for ref in _ids(lot, key):
            obj = session.get(model, tuple(ref) if key == "affectation_actif" else ref)
            if obj is not None:
                session.delete(obj)
                supprimes += 1
        session.flush()
    lot.statut = "annule"
    lot.annule_le = datetime.utcnow()
    lot.annule_par = account
    session.add(lot)
    session.commit()
    return {"supprimes": supprimes}
