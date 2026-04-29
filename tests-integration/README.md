# Integration / contract tests

Live HTTP probes against the external services rolez depends on:

- **skillz** at `skillz.startanaicompany.com` — response shape stability
- **agentz** at `agentz.startanaicompany.com` — same
- **tech.saac MCP** at `tech.startanaicompany.com/api/mcp` — auth probe + tool-by-tool input-schema contracts (the surface `app/upstream_auth.verify_token` and `app/provisioner.provision` rely on)
- **rolez itself** (optional, post-deploy smoke)

## Why a separate directory

These tests live outside `tests/` because they must escape the parent `tests/conftest.py` — the unit-test conftest imports `respx`, which patches `httpx` session-wide and (in WSL2 environments) breaks DNS resolution for unrelated network calls. Running with `pytest --confcutdir=tests-integration` keeps the conftest sandboxed.

## Running

```bash
# Set the credentials you want to exercise. Missing ones cause skips, not failures.
export SKILLZ_TOKEN=...
export AGENTZ_TOKEN=...
export MCP_ORCHESTRATOR_API_KEY=...
export ROLEZ_INTEGRATION_URL=https://rolez.startanaicompany.com   # optional

pytest tests-integration -m integration --confcutdir=tests-integration
```

## What's tested

### Tool contracts (`test_techsaac_contract.py`)

The `EXPECTED_TOOLS` dict pins the tech.saac MCP tools rolez calls (today + planned for v0.2). For each tool it asserts:

1. The tool exists in `tools/list`
2. Its `inputSchema.required` matches what we expect
3. Every field rolez sends is in `inputSchema.properties` (catches renames like `image` → `container_image`)

When rolez starts calling a new MCP tool, **add an entry to `EXPECTED_TOOLS`** — the test is the source of truth for our contract.

### Response-shape contracts (`test_{skillz,agentz}_contract.py`)

Probe a real existing skill/agent (whatever's first in the registry — no hardcoded slugs to rot) and assert the resolver-relevant fields are present and typed right (`name`, `latest_version`, `versions`).

### Live deployment smoke (`test_rolez_live_smoke.py`)

Optional, gated on `ROLEZ_INTEGRATION_URL`. Verifies the deployed service advertises the right endpoints, requires auth where it should, and serves the bootstrap CLI.

## CI

Recommended: run on a nightly cron via GitHub Actions, plus on PRs that touch `app/clients/`, `app/provisioner.py`, or `app/upstream_auth.py`. Secrets via repo settings; PR runs from forks should NOT receive secrets — the contract drift signal is per-repo, not per-PR.

The default `pytest` invocation excludes the `integration` marker — these tests never run as part of the inner-loop quality gate (`/saac:check`).
