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


def decode_text(raw: bytes) -> tuple[str, str]:
    """UTF-8 (BOM gere) en priorite, sinon Windows-1252 (export Excel francais)."""
    try:
        return raw.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "Windows-1252"


def read_csv(raw: bytes) -> tuple[list[dict], list[str], dict]:
    """Lignes (dict), en-tetes nettoyes et informations de lecture (encodage, separateur)."""
    if b"\x00" in raw[:4096]:
        raise ValueError("fichier binaire, un CSV (texte) est attendu")
    text, encoding = decode_text(raw)
    first = next((ligne for ligne in text.splitlines() if ligne.strip()), "")
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    headers = [(h or "").strip() for h in (reader.fieldnames or [])]
    rows = []
    for raw_row in reader:
        rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in raw_row.items() if k is not None})
    return rows, headers, {"encodage": encoding, "separateur": delim}


def read_rows(raw: bytes) -> tuple[list[dict], str]:
    """Compatibilite : lignes et separateur."""
    rows, _, info = read_csv(raw)
    return rows, info["separateur"]


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
