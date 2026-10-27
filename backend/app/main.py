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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_bootstrap_account
from .config import settings
from .db import init_db
from .routers import (
    applications,
    assets,
    assignments,
    auth,
    entites,
    import_data,
    lifecycle,
    reports,
    rgpd,
    stats,
    user_apps,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_bootstrap_account()
    yield


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)

# CORS ouvert en developpement (front React). A restreindre en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}


app.include_router(auth.router)
app.include_router(entites.router)
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
