from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, health, public

log = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="rolez",
    description="Role catalogue for the startanaicompany.com agent fleet.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": "rolez",
        "version": app.version,
        "public_url": settings.public_url,
        "endpoints": {
            "public": "/api/v1",
            "admin": "/api/admin",
            "health": "/health",
        },
    }
