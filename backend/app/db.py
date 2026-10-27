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

import time

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)


def init_db(retries: int = 12, delay: float = 3.0) -> None:
    """Cree les tables, en attendant que PostgreSQL soit pret."""
    from . import models  # noqa: F401  (enregistre les tables)

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            SQLModel.metadata.create_all(engine)
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay)
    if last_error:
        raise last_error


def get_session():
    with Session(engine) as session:
        yield session
