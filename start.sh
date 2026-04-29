#!/bin/sh
set -e

PORT="${PORT:-8000}"

echo "[start] rolez booting on port ${PORT}"
echo "[start] DATABASE_URL present: $([ -n "${DATABASE_URL}" ] && echo yes || echo NO)"
echo "[start] ROLEZ_ADMIN_API_KEY present: $([ -n "${ROLEZ_ADMIN_API_KEY}" ] && echo yes || echo NO)"
echo "[start] MCP_ORCHESTRATOR_URL=${MCP_ORCHESTRATOR_URL:-<unset>}"
echo "[start] SKILLZ_API_URL=${SKILLZ_API_URL:-<unset>}"
echo "[start] AGENTZ_API_URL=${AGENTZ_API_URL:-<unset>}"

echo "[start] running alembic upgrade head"
alembic upgrade head
echo "[start] alembic done"

echo "[start] launching uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
