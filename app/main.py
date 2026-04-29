from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from app.config import get_settings
from app.routers import admin, health, public

log = logging.getLogger(__name__)

CLI_PATH = Path(__file__).resolve().parent.parent / "cli" / "rolez"

settings = get_settings()

app = FastAPI(
    title="rolez",
    description="Role registry + provisioner for the startanaicompany.com agent fleet.",
    version="0.1.0",
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


@app.get("/cli/rolez", include_in_schema=False)
async def serve_cli():
    if not CLI_PATH.is_file():
        # If we hit this, the Docker image was built without cli/rolez and
        # every agent that curl's the bootstrap endpoint will write a 500
        # response into /usr/local/bin/rolez. Surface this loudly in logs so
        # ops can see the broken image immediately.
        log.error("CLI bootstrap requested but %s missing — image build is broken", CLI_PATH)
        return PlainTextResponse("CLI not packaged in this image", status_code=500)
    return FileResponse(
        path=CLI_PATH,
        media_type="text/x-python",
        filename="rolez",
        headers={"Content-Disposition": 'attachment; filename="rolez"'},
    )


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
            "cli": "/cli/rolez",
        },
    }
