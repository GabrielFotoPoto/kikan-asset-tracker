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

"""Recherche globale (palette Ctrl+K) : materiel et salaries (lecture, tous roles authentifies).

Memes regles que les listes : la portee par entite du compte s'applique (scope.py), un element hors portee n'apparait
jamais et les elements sans entite ne sont visibles que des comptes globaux. La comparaison ignore casse et accents et
exige tous les termes. Seuls des champs deja visibles dans les listes sont renvoyes (ni notes, ni e-mail). Un resultat
est limite a `limit` elements par groupe ; les totaux disent combien il y en a en tout.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..asset_catalog import fold
from ..auth import get_current_account
from ..db import get_session
from ..models import Asset, User
from ..scope import Scope, scope_dep

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(get_current_account)])

MIN_CARACTERES = 2


def _rang(premier: str, valeurs: list[str | None]) -> int:
    """0 si un champ commence par le premier terme (numero de serie, matricule, nom), 1 sinon : ces resultats passent devant."""
    return 0 if any(fold(v).startswith(premier) for v in valeurs if v) else 1


def _trouver(lignes, termes: list[str], champs, etiquette) -> list:
    """Lignes dont les champs contiennent tous les termes, les mieux classees d'abord."""
    trouvees = []
    for ligne in lignes:
        valeurs = [getattr(ligne, c) for c in champs]
        meule = fold(" ".join(v for v in valeurs if v))
        if all(t in meule for t in termes):
            trouvees.append((_rang(termes[0], valeurs), fold(etiquette(ligne)), ligne))
    trouvees.sort(key=lambda t: (t[0], t[1], t[2].id))
    return [t[2] for t in trouvees]


@router.get("")
def search(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=5, ge=1, le=10),
    session: Session = Depends(get_session),
    scope: Scope = Depends(scope_dep),
):
    termes = [t for t in fold(q).split(" ") if t]
    if sum(len(t) for t in termes) < MIN_CARACTERES:
        return {"q": q, "materiel": [], "utilisateurs": [], "total_materiel": 0, "total_utilisateurs": 0}

    actifs = _trouver(
        session.exec(scope.where(select(Asset), Asset.entite_id)).all(), termes,
        ("identifiant_interne", "type", "marque", "modele", "numero_serie"),
        lambda a: f"{a.marque or ''} {a.modele or ''} {a.numero_serie or ''}")
    salaries = _trouver(
        session.exec(scope.users(select(User))).all(), termes,
        ("nom", "prenom", "matricule"),
        lambda u: f"{u.nom or ''} {u.prenom or ''}")
    return {
        "q": q,
        "materiel": [
            {"id": a.id, "type": a.type, "marque": a.marque, "modele": a.modele, "numero_serie": a.numero_serie,
             "identifiant_interne": a.identifiant_interne, "statut": a.statut}
            for a in actifs[:limit]
        ],
        "utilisateurs": [
            {"id": u.id, "nom": u.nom, "prenom": u.prenom, "matricule": u.matricule, "statut": u.statut}
            for u in salaries[:limit]
        ],
        "total_materiel": len(actifs),
        "total_utilisateurs": len(salaries),
    }
