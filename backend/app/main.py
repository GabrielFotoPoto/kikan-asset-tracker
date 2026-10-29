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
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from .audit import audit
from .auth import IS_PROD, MUTATING, LoginLimiter, actor_from_request, client_ip, ensure_bootstrap_account
from .config import settings
from .db import engine, init_db
from . import reminders
from .filestore import StorageError, sync_pending
from .routers import (
    applications,
    assets,
    assignments,
    audit_log,
    auth,
    backup_admin,
    besoins,
    entites,
    import_data,
    integrations,
    glpi_admin,
    api_v1,
    lifecycle,
    mail_admin,
    parametres,
    policies,
    reports,
    sso,
    rgpd,
    stats,
    storage_admin,
    user_apps,
    users,
)


log = logging.getLogger("kikan.main")


def _sync_storage_in_background() -> None:
    """Au demarrage : depose les PDF restes dans le tampon local (partage indisponible auparavant)."""
    try:
        with Session(engine) as session:
            result = sync_pending(session)
        if result["pending"]:
            log.warning("Depots en attente : %d, deposes : %d, echecs : %d",
                        result["pending"], result["synced"], result["failed"])
    except Exception:  # noqa: BLE001
        log.exception("Synchronisation du stockage impossible au demarrage")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_bootstrap_account()
    threading.Thread(target=_sync_storage_in_background, daemon=True).start()
    if os.environ.get("KIKAN_SCHEDULER", "1") != "0":
        reminders.start_scheduler()
    yield


# En production, la documentation interactive n'est pas exposee.
_docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if IS_PROD else {}
VERSION = os.environ.get("KIKAN_VERSION", "dev").lstrip("v")
app = FastAPI(title=f"{settings.app_name} API", version=VERSION, lifespan=lifespan, **_docs)

# CORS : le front passe par Nginx (meme origine), donc inutile en usage normal.
# Seules les origines listees sont autorisees (jamais "*").
_origins = [o.strip() for o in os.environ.get(
    "KIKAN_CORS_ORIGINS", "http://localhost:3000,https://localhost:3443"
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# Les refus (401/403) sont journalises, mais plafonnes par adresse IP : sans cela, des requetes anonymes
# en boucle rempliraient la table d'audit. Les ecritures authentifiees restent toujours journalisees.
_denied = LoginLimiter(max_per_account=10**9, max_per_ip=60, window=60)


def _denial_loggable(ip: str) -> bool:
    if _denied.retry_after(ip, ""):
        return False
    _denied.fail(ip, "")
    return True


@app.middleware("http")
async def audit_and_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    # Journal : toute ecriture, et tout refus d'acces (401/403). Jamais de corps de requete
    # (mots de passe, donnees personnelles). Les connexions sont journalisees dans /auth/login.
    denied = response.status_code in (401, 403)
    if path != "/health" and path != "/auth/login" and (
        (request.method in MUTATING and not denied) or (denied and _denial_loggable(client_ip(request)))
    ):
        await run_in_threadpool(
            audit, actor_from_request(request), f"{request.method} {path}",
            status=response.status_code, ip=client_ip(request),
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": VERSION}


app.include_router(auth.router)
app.include_router(entites.router)
app.include_router(policies.router)
app.include_router(parametres.router)
app.include_router(sso.router)
app.include_router(users.router)
app.include_router(assets.router)
app.include_router(applications.router)
app.include_router(assignments.router)
app.include_router(import_data.router)
app.include_router(lifecycle.router)
app.include_router(reports.router)
app.include_router(rgpd.router)
app.include_router(user_apps.router)
app.include_router(stats.router)
app.include_router(audit_log.router)
app.include_router(storage_admin.router)
app.include_router(mail_admin.router)
app.include_router(besoins.router)
app.include_router(backup_admin.router)
app.include_router(integrations.router)
app.include_router(glpi_admin.router)
app.include_router(api_v1.router)
