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

"""Helpers de parsing CSV pour l'import (reprise de l'existant)."""
import csv
import io
from datetime import date


def read_rows(raw: bytes) -> tuple[list[dict], str]:
    """Decode UTF-8 (BOM gere), detecte le separateur ; ou , et renvoie les lignes."""
    text = raw.decode("utf-8-sig")
    first = next((ligne for ligne in text.splitlines() if ligne.strip()), "")
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for raw_row in reader:
        rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in raw_row.items()})
    return rows, delim


def as_bool(value, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("oui", "yes", "true", "1", "vrai", "o")


def as_date(value):
    value = (value or "").strip()
    if not value:
        return None
    return date.fromisoformat(value)  # leve ValueError si invalide


def as_str(value):
    value = (value or "").strip()
    return value or None
