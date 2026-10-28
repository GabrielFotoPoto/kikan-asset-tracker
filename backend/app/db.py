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

import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, create_engine

from .config import settings

log = logging.getLogger("kikan.db")

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)

# Racine du backend (contient alembic.ini et migrations/).
BACKEND_DIR = Path(__file__).resolve().parent.parent
# Schema d'une base creee avant l'arrivee d'Alembic (create_all) : revision de reference.
BASELINE_REVISION = "0001"
_MIGRATION_LOCK_ID = 727274  # verrou consultatif PostgreSQL : un seul processus migre a la fois


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def run_migrations() -> None:
    """Applique les migrations en attente (alembic upgrade head).

    Une base existante creee avant Alembic (tables presentes, pas de table alembic_version)
    est d'abord marquee a la revision de reference, sans toucher a ses donnees.
    """
    cfg = _alembic_config()
    with engine.connect() as lock_conn:
        lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _MIGRATION_LOCK_ID})
        try:
            tables = set(inspect(lock_conn).get_table_names())
            if "alembic_version" not in tables and "users" in tables:
                log.warning("Base existante sans Alembic : marquage a la revision %s", BASELINE_REVISION)
                command.stamp(cfg, BASELINE_REVISION)
            command.upgrade(cfg, "head")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _MIGRATION_LOCK_ID})
            lock_conn.commit()


def init_db(retries: int = 12, delay: float = 3.0) -> None:
    """Migre le schema, en attendant que PostgreSQL soit pret."""
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            run_migrations()
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay)
    if last_error:
        raise last_error


def get_session():
    with Session(engine) as session:
        yield session
