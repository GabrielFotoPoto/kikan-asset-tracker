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

"""Index sur toutes les cles etrangeres (migration 0024) : aucune cle etrangere sans index sur sa premiere colonne.

Usage :
  docker exec -i -e TEST_ADMIN_USER=admin -e TEST_ADMIN_PASSWORD=... kikan-api python - < tests/index_check.py

Lecture seule sur le catalogue PostgreSQL, aucune donnee creee. Code de sortie 1 si un test echoue.
"""
import sys

from sqlalchemy import text
from sqlmodel import Session

from app.db import engine

fails = 0


def show(name, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail)[:160] if detail else ""))


SANS_INDEX = """
SELECT c.conrelid::regclass::text, a.attname
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f'
  AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
ORDER BY 1, 2
"""

ATTENDUS = ("ix_users_entite_id", "ix_assets_entite_id", "ix_applications_entite_id", "ix_policies_entite_id",
            "ix_assignments_policy_id", "ix_assignment_assets_asset_id", "ix_echange_retours_asset_id",
            "ix_account_scopes_entite_id", "ix_api_token_scopes_entite_id", "ix_besoins_assignment_id")

with Session(engine) as s:
    manquantes = [f"{t}.{c}" for t, c in s.execute(text(SANS_INDEX)).all()]
    show("aucune cle etrangere sans index", not manquantes, manquantes)

    presents = {r[0] for r in s.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()")).all()}
    absents = [n for n in ATTENDUS if n not in presents]
    show("les 10 index de la migration 0024 existent sous le nom attendu", not absents, absents)

    version = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
    show("la base est au moins a la revision 0024", version is not None and version >= "0024", version)

print("")
print("ECHECS: %d" % fails)
sys.exit(1 if fails else 0)
