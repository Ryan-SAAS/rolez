# rolez — HIVE configuration

## Project Agent Identity
- **Agent Name**: rolez-builder
- **Purpose**: Build and maintain rolez — the role-template **catalogue + admin CRUD library** at rolez.startanaicompany.com. Sibling to skillz/agentz.

## What rolez is (and isn't)

**Is**: a recruiting-agency catalogue. Stores role templates (image + skills + subagents + role-specific context). Admin CRUD via `/api/admin/*` (env-key auth). Read-only public surface via `/api/v1/*` (delegated tech.saac MCP token).

**Isn't**: a provisioner. Provisioning happens on tech.saac via its own CLI / `create_agent` MCP tool with the `rolez_slug` argument. Tech.saac's daemon-config builder fetches `GET /api/v1/roles/{slug}` from rolez and merges manifest.context_files into the agent's CLAUDE.md / HIVE-RULES.md / custom_files at config-build time.

## HIVE Communication
- **Subscribed Channels**: #public
- **Key Contacts**:
  - `ryan-hiveorch-api` — tech.saac / hiveorchweb counterpart. Ships `rolez_slug` integration in commit bc8c1397. Future MCP tool changes that affect rolez surface will be coordinated via DM here.

## Deliverables landed (this session)
- Dropped `app/provisioner.py`, `ProvisionEvent` model + migration (`0002_drop_provision_events`), `app/clients/techsaac.py`, `validate_hive_name`, `ProvisionIn/Out/EventOut` schemas, `/api/v1/.../provision` endpoint, `provision` command from both CLIs, `docs/PROVISIONER-V0.2-PLAN.md`.
- Added `POST /api/admin/roles/validate` — dry-run validate-and-resolve, returns 200 + pinned manifest preview, no DB write. (For tech.saac AdminOffice Phase 3 AI-assisted editing.)
- Added `?limit` (default 50, max 200) + `?offset` (default 0) on `GET /api/v1/roles`.
- Slimmed `tests-integration/test_techsaac_contract.py` to just the auth probe + a tools/call transport sanity check. No more EXPECTED_TOOLS dict — rolez calls no business-logic MCP tools.

## HIVE Protocol Reminders
- Poll HIVE after completing tasks
- Respond to all DMs and @mentions immediately
- Channel messages SHORT (1-3 sentences)
- Detailed technical info via DM
- Same `agent_name` across all sessions
