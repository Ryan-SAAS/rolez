# Rolez

Headless role registry + provisioner for the startanaicompany.com agent fleet.
A role is a *composition* of:

- a Docker image owned by **tech.saac** (`tech.startanaicompany.com`)
- skills owned by **skillz** (`skillz.startanaicompany.com`)
- subagents owned by **agentz** (`agentz.startanaicompany.com`)
- role-specific glue: prompts, tools, MCP servers, inputs/outputs, consumed
  integrations, required variables, communication rules, context files.

Rolez stores references with **pinned versions** — the underlying content
stays in skillz / agentz / tech.saac. Rolez never duplicates artifacts.

No UI lives here — the admin console is at `tech.startanaicompany.com` and
calls `/api/admin/*`.

## Surfaces

| Path | Audience | Auth |
|---|---|---|
| `GET /api/v1/*` | Assistants | Caller's tech.saac MCP api key (delegated, validated upstream) |
| `POST /api/v1/roles/{slug}/provision` | Assistants | Same — token re-used downstream as the principal |
| `GET\|POST\|DELETE /api/admin/*` | tech.saac UI / backend | Single env-var `ROLEZ_ADMIN_API_KEY` |
| `GET /cli/rolez` | Agent containers self-installing the CLI | Public |
| `GET /health` | Infra | Public |
| `GET /metrics` | Prometheus | (basic auth, future) |

## Auth model

Assistants present their tech.saac MCP api key as `Authorization: ApiKey <token>`.
Rolez verifies the key against tech.saac via a cheap `tools/list` JSON-RPC
probe (cached for 60s by sha256 of token). When provisioning, rolez re-uses
the same caller token in its downstream `create_agent` call to tech.saac, so
the new agent is owned by the caller's principal — rolez holds no
service-account credentials for tech.saac.

The `ROLEZ_ADMIN_API_KEY` env var is the single secret used by the tech.saac
admin UI to do role-template CRUD against `/api/admin/*`.

## Local dev

```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8000/health
```

Run the test suite:

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
.venv/bin/pytest -q
```

## CLI install (inside agent containers)

Stdlib Python CLI, served by the API itself:

```bash
export ROLEZ_API_URL=https://rolez.startanaicompany.com
export ROLEZ_API_KEY="$MCP_ORCHESTRATOR_API_KEY"   # or set ROLEZ_API_KEY directly
curl -fsSL "$ROLEZ_API_URL/cli/rolez" -o /usr/local/bin/rolez
chmod +x /usr/local/bin/rolez

rolez list
rolez show support-agent
rolez provision support-agent \
  --org "$ORG_ID" --product "$PRODUCT_ID" --name support-eu \
  --var SUPPORT_CHANNEL=#eu-support \
  --skill csv-tools@0.4.1 \
  --binding zendesk=$ZENDESK_CONNECTION_ID
```

Or via npm:

```bash
npx -p @startanaicompany/rolez rolez list
```

## Provisioning flow

```
assistant ──ApiKey<token>──▶ rolez ──validate──▶ tech.saac (tools/list)
                                │
                                ├── load role manifest from DB
                                ├── merge --skill / --subagent extras (later wins)
                                ├── validate required_variables
                                └── tech.saac (tools/call create_agent)
                                       └── tech.saac materialises
                                           secrets per integration_bindings
                                           (rolez never sees them)
```

`provision_events` records every attempt — successful or not — with a
caller-token fingerprint, the resolved role version, and tech.saac's status.

## Project layout

```
app/                        FastAPI service
  main.py                   bootstrap, CORS, root + /cli/rolez
  config.py                 env-driven Settings
  db.py                     async SQLAlchemy engine
  auth.py                   admin api-key check
  upstream_auth.py          delegated tech.saac validation + 60s cache
  models.py                 RoleTemplate, RoleTemplateVersion, ProvisionEvent, AgentEvent
  validation.py             pydantic schemas for the role manifest
  resolver.py               resolves "latest" → pinned via skillz / agentz
  provisioner.py            merges extras, validates vars, calls tech.saac, logs event
  clients/                  HTTP clients for skillz, agentz, tech.saac
  routers/
    public.py               /api/v1/* — list / search / show / provision
    admin.py                /api/admin/* — role CRUD
    health.py               /health

cli/rolez                   stdlib Python CLI, served at /cli/rolez
cli-node/                   TypeScript Node CLI, npm @startanaicompany/rolez

migrations/                 Alembic
tests/                      pytest suite (74 tests)
docs/                       design docs
```

## Railway deploy

1. Create a Railway project from this repo.
2. Attach the Postgres plugin — Railway injects `DATABASE_URL`.
3. Set env vars: `ROLEZ_ADMIN_API_KEY`, `ADMIN_ALLOWED_ORIGINS`,
   `MCP_ORCHESTRATOR_URL`, `SKILLZ_API_URL`, `SKILLZ_TOKEN`,
   `AGENTZ_API_URL`, `AGENTZ_TOKEN`, `METRICS_USER`, `METRICS_PASS`.
4. Deploy. The container runs `alembic upgrade head` on boot, then Uvicorn.
