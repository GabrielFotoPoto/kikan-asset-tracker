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
