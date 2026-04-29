from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["infra"])

log = logging.getLogger(__name__)


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    """Liveness probe.

    Returns 200 + ``{status: "ok", db: "ok"}`` when Postgres is reachable.
    Returns **503** + ``{status: "error", db: "error"}`` on any DB failure —
    a service whose entire job is reading/writing Postgres must NOT report
    itself healthy when the DB is unreachable, or k8s/Railway probes will
    happily route traffic to a doomed pod.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        log.exception("health check db probe failed")
        return JSONResponse(
            {"status": "error", "db": "error", "detail": str(e)},
            status_code=503,
        )
    return {"status": "ok", "db": "ok"}
