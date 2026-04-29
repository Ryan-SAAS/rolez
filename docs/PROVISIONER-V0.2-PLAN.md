# Provisioner v0.2 — orchestrate the real `create_agent` flow

## Why

Live probing of `tech.startanaicompany.com/api/mcp` (recorded in
`tests-integration/test_techsaac_contract.py::EXPECTED_TOOLS`) found that
v0.1's provisioner sends a single `create_agent` call with seven fields,
six of which tech.saac doesn't accept and one of which we're missing. The
real `create_agent` tool only accepts:

```
product_id      [required]   string
name            [required]   display name
agent_name      [required]   HIVE-compat 4-word format (e.g. "acme-backend-code-reviewer")
description     optional     string
role            optional     short role label
```

Everything else rolez wants applied to a new agent — image, env vars,
integrations, context files — needs separate post-create MCP calls. v0.2
turns `provision()` into an orchestrator that issues `create_agent` then
drives the configuration sequence, and rolls back (`delete_agent`) on
failure.

The contract tests already pin the live schema for every tool v0.2 needs.
If any of them changes upstream, the test fails before the rewrite hits
production.

## Live tool schemas (pinned 2026-04-30)

| Tool | Required | Optional | Notes |
|---|---|---|---|
| `create_agent` | `product_id`, `name`, `agent_name` | `description`, `role` | `agent_name` must be 4 lowercase words ≥ 4 chars each, hyphenated |
| `set_agent_container_image` | `agent_id`, `container_image` | — | NB: field is `container_image`, not `image` |
| `set_agent_env_var` | `agent_id`, `key`, `value` | `description` | Per-key call — must loop over `manifest.required_variables` |
| `connect_integration` | `agent_id`, `provider`, `credentials` | `label` | `credentials` is an object of key/value pairs (e.g. `{"secret_key": "sk_..."}`) |
| `update_agent_context` | `agent_id` | `claude_md`, `hive_rules_md`, `custom_files` | Three explicit slots — split rolez's `context_files[]` accordingly |
| `delete_agent` | `agent_id` | — | Used for rollback |
| `list_container_images` | — | — | For admin-time image catalog resolution |

## Architectural changes

### 1. Provisioning becomes an orchestrated sequence

```
provision(slug, payload, caller_token)
├─ resolve role manifest (unchanged)
├─ derive agent_name from caller-supplied name (4-word HIVE format)
├─ TechsaacClient.call_tool("create_agent", {product_id, name, agent_name, description, role})
│    └─> agent_id
├─ for each variable in payload.variables:
│    TechsaacClient.call_tool("set_agent_env_var", {agent_id, key, value, description?})
├─ TechsaacClient.call_tool("set_agent_container_image", {agent_id, container_image: manifest.image.ref})
├─ for each binding in payload.integration_bindings:
│    TechsaacClient.call_tool("connect_integration", {agent_id, provider, credentials, label?})
├─ if manifest.context_files non-empty:
│    TechsaacClient.call_tool("update_agent_context", {agent_id, claude_md, hive_rules_md, custom_files})
└─ on any post-create failure:
     TechsaacClient.call_tool("delete_agent", {agent_id})  # best-effort rollback
     re-raise
```

The whole sequence runs under one caller token — the same delegated
principal applies throughout. `provision_events` records the *outcome*
(agent_id + final status) plus a structured trail of which step failed
on partial-success rollbacks.

### 2. Secrets handoff — the v0.1 assumption is wrong

v0.1 documented "tech.saac handles secrets internally; rolez forwards
`{catalog_slug, connection_id}` refs". The live `connect_integration`
tool actually requires the **full credentials object**
(`{"secret_key": "sk_live_..."}`), not a connection_id ref. Either:

- **Option A:** caller supplies credentials directly in
  `provision` payload (rolez carries them in memory but never persists)
- **Option B:** rolez resolves a connection_id → credentials via a new
  tech.saac tool we'd need to request (none exists today)

Recommend **Option A** for v0.2 — minimal scope, explicit data flow,
caller is the assistant which already holds these creds anyway. Update
`ProvisionIn.integration_bindings` to be
`list[{provider: str, credentials: dict[str,str], label?: str}]`,
typed via a new `IntegrationBinding` schema. Document plainly that
secrets pass through rolez memory (do not log them in `provision_events`).

### 3. Image resolution — make it real

Move `_resolve_image` from "deferred passthrough" to a real
`list_container_images` lookup at admin save time. Pinned image refs in
the manifest become genuine — `RoleManifest` (the strict variant) gets
to be reachable code.

### 4. HIVE 4-word agent_name generator

`agent_name` is required and must match the 4-word format. Rolez has the
role slug (e.g. `support-agent`) and the caller's display name (e.g.
`support-eu`). Strategy:

- Take `<org-slug>-<product-slug>-<role-slug>-<sequence>`
  - Each ≥ 4 chars; pad with the role slug if any segment is too short
  - Sequence = next available integer (probe via `list_agents`)
- Reject if the result still doesn't match the format — surface a 422
  with a hint pointing at the constraint in the create_agent tool docs.

A small helper `app/hive_naming.py` with focused unit tests handles this.
The contract test `test_create_agent_agent_name_format_documented`
already guards the upstream constraint description for us.

### 5. Skills and subagents — open question

There is **no first-class MCP tool** in the live tools/list for
installing skills or subagents into an agent's container. The current
in-fleet mechanism is presumably the saac-images container's own
sync-from-skillz/agentz logic at startup, driven by env vars or the
container's own config.

Two routes for v0.2:

- **(a)** Pass `SKILLZ_INSTALL=skill1@1.2.3,skill2@0.4.0` and
  `AGENTZ_INSTALL=...` as env vars via `set_agent_env_var`, and rely on
  the container's startup hook to install them. Requires saac-images to
  honour those env vars (verify with `ryanhiveagentbuilder` peer).
- **(b)** Write the skill/subagent slugs into a `.claude/skillz.json` /
  `.claude/agentz.json` via `update_agent_context`'s `custom_files`
  slot, and expect the container to read them.

Both are testable without an MCP tool change. Pick after a quick chat
with the saac-images team (out of scope for this plan).

## Code touch points

| File | Change |
|---|---|
| `app/provisioner.py` | Replace single-call body with orchestration sequence + rollback. Existing `record(...)` closure stays. |
| `app/clients/techsaac.py` | Already has `call_tool(name, args, caller_token=...)` — no change. |
| `app/schemas.py` | `ProvisionIn.integration_bindings: list[IntegrationBinding]` (the new shape). |
| `app/resolver.py` | `_resolve_image` calls `list_container_images` via a new tech.saac client method (or via `TechsaacClient.call_tool` with rolez's own service token if we get one). |
| `app/hive_naming.py` | NEW: `hive_agent_name(org_slug, product_slug, role_slug, sequence) -> str` + validator. |
| `tests/test_provisioner.py` | Mock the multi-call sequence (respx still mocks `/api/mcp` end-to-end); add rollback test (post-create failure → `delete_agent` called); add per-variable env-var test. |
| `tests/test_hive_naming.py` | NEW: name generation + edge cases. |
| `tests-integration/test_techsaac_contract.py` | Already in place — no change unless tech.saac adds new tools we adopt. |

## Migration path

1. Land v0.2 as a single PR. Behind a `ROLEZ_PROVISIONER_VERSION` env
   flag (default `v1`) so production doesn't switch until intentionally
   enabled.
2. Smoke-test against a sacrificial org/product on the live deployment.
3. Flip the flag to `v2` in a follow-up commit; remove the v1 branch
   one release later.

## Out of scope for v0.2

- Hot-reload / config-sync after provision (separate concern).
- Migrating existing v0.1-provisioned agents — there are none yet.
- Replacing `connect_integration`'s synchronous-credentials API surface
  with a connection_id model (would need a tech.saac change).
- Skill/subagent install mechanism — pending answer from saac-images
  team (see §5).

## Verification

- `pytest -m 'not integration'` — full unit suite green (including
  rewritten provisioner tests).
- `pytest tests-integration -m integration --confcutdir=tests-integration`
  with all three tokens set — contract tests green.
- Manual: `rolez provision <slug> --org X --product Y --name <hive-name>`
  against a sacrificial org → agent appears in `techsaac list-agents`,
  has correct image / env vars / integrations / context, and survives
  a `start_agent`. Cleanup with `delete_agent`.
