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

## Manifest shape (v0.2.0)

```json
{
  "image":     { "ref": "saac/x", "version": "1.0.0" },
  "skills":    [{ "name": "...", "version": "1.0.0" }],
  "subagents": [{ "name": "...", "version": "0.5.0" }],
  "context":   "..."
}
```

Top-level role row has `slug`, `display_name`, `description`, `tags`. No `identity` block, no `kind`, no `context_files` array — all dropped in 0.2.0 per Ryan's UI simplification.

## Recent deliverables
- **0.2.0 schema cut**: dropped `manifest.identity`, `role.kind` column, `manifest.context_files` array. Replaced context_files with singular `manifest.context: str`. Migration 0003 flattens existing rows (extracts `context_files[name='CLAUDE.md'].content` → new `context` field, drops the rest).
- POST /api/admin/roles/validate — dry-run validate-and-resolve.
- Pagination on GET /api/v1/roles + GET /api/admin/roles.
- Provisioning was removed in 0.1.x — done by tech.saac via `create_agent --rolez_slug`.

## HIVE Protocol Reminders
- Poll HIVE after completing tasks
- Respond to all DMs and @mentions immediately
- Channel messages SHORT (1-3 sentences)
- Detailed technical info via DM
- Same `agent_name` across all sessions
