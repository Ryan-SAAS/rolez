from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Configure test env BEFORE app imports — Settings is lru_cached.
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="rolez-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_ROOT}/db.sqlite3")
os.environ.setdefault("ROLEZ_ADMIN_API_KEY", "test-admin-api-key")
os.environ.setdefault("ADMIN_ALLOWED_ORIGINS", "https://tech.startanaicompany.com")
os.environ.setdefault("ROLEZ_PUBLIC_URL", "http://testserver")
os.environ.setdefault("SKILLZ_API_URL", "https://skillz.example")
os.environ.setdefault("SKILLZ_TOKEN", "test-skillz-token")
os.environ.setdefault("AGENTZ_API_URL", "https://agentz.example")
os.environ.setdefault("AGENTZ_TOKEN", "test-agentz-token")
os.environ.setdefault("MCP_ORCHESTRATOR_URL", "https://techsaac.example/api/mcp")
os.environ.setdefault("ROLEZ_AUTH_TTL_SECONDS", "60")


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP_ROOT


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp():
    yield
    # Don't rmtree — under tools that re-use the Python process for many test
    # sessions (mutmut), tearing down the tempdir invalidates DATABASE_URL for
    # the next session and breaks every subsequent test with "unable to open
    # database file". Leaving the dir lets the OS reclaim it later.


@pytest.fixture
async def client(tmp_root):
    """Build a fresh FastAPI app with tables created for each test."""
    from httpx import ASGITransport, AsyncClient

    from app.config import get_settings
    from app.db import Base, get_engine
    from app.main import app

    # If a previous run rmtree'd the tmp dir (or never created it), recreate it
    # so the DATABASE_URL points at something writable.
    tmp_root.mkdir(parents=True, exist_ok=True)

    get_settings.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": "ApiKey test-admin-api-key"}


@pytest.fixture
def agent_headers() -> dict[str, str]:
    """A header carrying the assistant's tech.saac MCP token. Tests that need
    upstream validation should additionally mock MCP_ORCHESTRATOR_URL via respx."""
    return {"Authorization": "ApiKey test-assistant-mcp-token"}
