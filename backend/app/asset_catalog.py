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

"""Catalogue marques / modeles deduit du materiel saisi : recherche assistee et graphie canonique.

Les comparaisons ignorent la casse, les accents et les espaces multiples (jamais la ponctuation : "T14" et
"T-14" restent distincts). Une valeur saisie qui ne differe d'une entree existante que par ces points reprend la
graphie la plus utilisee, ce qui evite de recreer des doublons. Les donnees deja en base ne sont jamais modifiees.
"""
import re
import unicodedata
from collections import Counter

from sqlalchemy import func
from sqlmodel import Session, select

from .models import Asset

MAX_LEN = 100


def fold(value: str | None) -> str:
    """Cle de comparaison : sans accents, sans casse, espaces uniques."""
    s = unicodedata.normalize("NFKD", value or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold()).strip()


def clean(value: str | None) -> str | None:
    """Espaces normalises ; None si vide."""
    s = re.sub(r"\s+", " ", value or "").strip()[:MAX_LEN]
    return s or None


def _best(counter: Counter) -> str:
    """Graphie la plus utilisee (a egalite : ordre alphabetique, pour rester deterministe)."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


class AssetCatalog:
    """Instantane du catalogue (une requete) ; sert a la recherche et a la normalisation."""

    def __init__(self, session: Session):
        self.marques: dict[str, Counter] = {}
        self.modeles: dict[str, dict[str, Counter]] = {}
        self.types: dict[tuple[str, str], Counter] = {}  # (marque, modele) -> types vus
        rows = session.exec(
            select(Asset.marque, Asset.modele, Asset.type, func.count())
            .group_by(Asset.marque, Asset.modele, Asset.type)
        ).all()
        for marque, modele, typ, n in rows:
            mk = fold(marque)
            if not mk:
                continue
            self.marques.setdefault(mk, Counter())[marque.strip()] += n
            ok = fold(modele)
            if ok:
                self.modeles.setdefault(mk, {}).setdefault(ok, Counter())[modele.strip()] += n
                if fold(typ):
                    self.types.setdefault((mk, ok), Counter())[fold(typ)] += n

    # --- Normalisation a l'enregistrement ---

    def canon_marque(self, value: str | None) -> str | None:
        v = clean(value)
        if not v:
            return None
        ctr = self.marques.setdefault(fold(v), Counter())
        best = _best(ctr) if ctr else v
        ctr[best] += 1  # la graphie retenue se renforce (utile pour un import : le premier gagne)
        return best

    def canon_modele(self, marque: str | None, value: str | None) -> str | None:
        v = clean(value)
        if not v:
            return None
        ctr = self.modeles.setdefault(fold(marque), {}).setdefault(fold(v), Counter())
        best = _best(ctr) if ctr else v
        ctr[best] += 1
        return best

    # --- Recherche assistee ---

    @staticmethod
    def _tier(key: str, qk: str) -> int | None:
        if not qk or key.startswith(qk):
            return 0
        return 1 if qk in key else None

    def suggest_marques(self, q: str | None, limit: int) -> list[dict]:
        qk = fold(q)
        out = []
        for key, ctr in self.marques.items():
            tier = self._tier(key, qk)
            if tier is not None:
                out.append((tier, -sum(ctr.values()), _best(ctr).lower(), {"nom": _best(ctr), "count": sum(ctr.values())}))
        out.sort(key=lambda t: t[:3])
        return [t[3] for t in out[:limit]]

    def suggest_modeles(self, marque: str | None, type_: str | None, q: str | None, limit: int) -> list[dict]:
        qk, tk = fold(q), fold(type_)
        brands = [fold(marque)] if fold(marque) else list(self.modeles)
        merged: dict[str, Counter] = {}
        seen_types: dict[str, Counter] = {}
        for mk in brands:
            for ok, ctr in self.modeles.get(mk, {}).items():
                merged.setdefault(ok, Counter()).update(ctr)
                seen_types.setdefault(ok, Counter()).update(self.types.get((mk, ok), Counter()))
        out = []
        for ok, ctr in merged.items():
            tier = self._tier(ok, qk)
            if tier is None:
                continue
            same_type = 0 if (tk and seen_types[ok].get(tk)) else 1  # modeles deja vus avec ce type d'abord
            out.append((same_type, tier, -sum(ctr.values()), _best(ctr).lower(), {"nom": _best(ctr), "count": sum(ctr.values())}))
        out.sort(key=lambda t: t[:4])
        return [t[4] for t in out[:limit]]
