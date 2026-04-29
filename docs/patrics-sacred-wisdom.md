# Agent Role System v2 — Design Discussion

> Status: Design draft for team feedback. Not a build plan yet.
> Scope: Orchestrator-side (hiveorchweb). Agents run as saac-agent containers.
> Revision history: Appendix B.

## 0. Terminology

"Role" and "persona" are both loaded words in this codebase. This doc uses:

- **Role template** — the role-type definition (e.g. `support-lead`). Authored by SaaC, composed of capabilities. In v2 this lives in a new `role_templates` table. The v1 equivalent `agent_persona_templates` keeps its name so the two coexist cleanly during rollout.
- **Capability** — a reusable building block a role template composes: prompts, activation rules, tool allowlist, CLAUDE.md snippet, referenced skills, referenced subagents, consumed integrations, required variables.
- **Skill** — a Claude Code skill authored and distributed via `skillz`.
- **Subagent** — a Claude Code sub-agent authored via `agentz`. Separate service, separate repo, own CLI — scaffolded from skillz but deployed independently. Same API shape as skillz, different host.
- **Integration** — a customer-facing connector (Zendesk, Slack, email, Discord, …) defined in the existing `integration_catalog`, bound per-org via `integration_connections`.
- **Agent** — a running instance of a role template, owned by an org.

Unrelated: `agent_portraits.persona_name` is the per-agent display name ("Helen Local AI"). Out of scope.

## 1. Context

Today, 26 agent personas live in a 2,700-line TypeScript seed file (`scripts/seed-agent-personas.ts`). Admin UI is read-only. The CLAUDE.md generator is hardcoded in `daemon.service.ts`. There is no versioning, no propagation to running agents, no per-role tool allowlists. Adding a new role means editing the seed and redeploying; existing agents never pick up changes.

We want a system where SaaC can define any new role (support, HR, sales, anything) as a composition of reusable building blocks, edit them safely, and have changes flow to running agents. Orgs customize by providing credentials and specific bindings — not by forking the role.

## 2. The broad shape

Three layers with clear ownership.

**SaaC owns the role library.** Platform admins author role templates and capabilities in an admin UI. A role template is identity + a list of capabilities. A capability is a reusable bundle.

**Orgs own their instance.** When an org spins up an agent, they supply specifics — which Zendesk account, which Slack workspace, which email inbox — via the existing `integration_connections` flow. They do not fork the role template.

**The agent is the composition at runtime.** The orchestrator combines role template → capability contents → resolved integration credentials → CLAUDE.md + agent.yaml + subagent files + skills → synced to the container.

A role template at the level a platform admin thinks about it:

```yaml
slug: support-lead
identity: { name, role, icon, description, tone }
capabilities:
  - core.conversation
  - support.ticket-triage
  - email.inbound
  - slack.inbound
  - workspace.file-bugs
communication_rules:      # see §5
  can_dm: ['*']           # can DM any role in the org
  listens_to: ['#support', '#general']
```

Each capability is its own versioned artifact. Authoring them is the Capabilities Library; composing them is the Role Template Builder.

## 3. What a role template includes

For MVP, a role template (and the capabilities it includes) defines:

- **Role identity** — name, icon, description, tone.
- **Skills** — Claude Code skills, referenced by `skillz` slug + pinned version. Resolved at sync time into the container's `.claude/skills/`.
- **Subagents** — Claude Code sub-agents, referenced by `agentz` slug + pinned version. Resolved into `.claude/agents/`.
- **Tools** — allowed/disallowed built-in and MCP tool names.
- **MCP servers** — which MCP servers the container mounts.
- **Prompts** — the role's prompts + their activation rules (bugs, HIVE messages, inbound webhooks).
- **Inputs** — which inbound bridges the agent listens to (email, Slack, Discord, Telegram, HIVE). See §4.
- **Outputs** — which outbound bridges the agent can use. See §4.
- **Consumed integrations** — which `integration_catalog` entries the agent draws credentials from.
- **Required variables** — named placeholders the org fills in (e.g. `SUPPORT_CHANNEL`, `SUPPORT_INBOX_EMAIL`).
- **Communication rules** — which other roles this role is allowed to DM. See §5.
- **CLAUDE.md snippet** — role-specific prose that the renderer composes into the final context file.

**Hot-reload is not an MVP requirement.** Config changes take effect on the next container bounce, triggered by a `sync_config` daemon task. Hot-reload (config read per query) is a post-MVP nice-to-have (§10).

## 4. Inputs and outputs

How an agent sees and speaks to the outside world. The Telegram pattern that works today generalizes cleanly.

**Inputs (email, Slack, Discord, Zendesk webhooks, etc.)**

1. Each external channel has a bridge service that owns its protocol.
2. External events arrive at `/api/webhooks/integrations/:connection_id/event`.
3. The bridge normalizes the payload into a HIVE message posted to the agent's group. The sender is `email-bridge-*`, `slack-bridge-*`, etc.
4. The agent's capability has an activation rule that fires on matching HIVE messages.

Enablement requires two things: (a) the role template includes the relevant bridge capability, AND (b) the org has a matching `integration_connections` binding with credentials.

**Outputs (reply via email, post to Slack)**

Same pattern reversed. The agent sends a HIVE message in a conventional shape; the bridge reads it and calls the external API using the org's bound credentials.

New channel = one new bridge service + one new capability in the library. The orchestrator core is untouched.

## 5. Communication rules

v2 preserves today's two-tier enforcement and adds one small piece of structure.

**Tier 1: HIVE security groups enforce membership (unchanged).** An agent can only send messages into groups it belongs to. Groups are `personal-{agent}`, `company-{org}`, `product-{org}-{product}`. Agents join their org and product groups on creation. This is HIVE-server-enforced and v2 does not change it.

**Tier 2: Role template CLAUDE.md enforces role boundaries via prose (preserved, now data-driven).** Today, rules like "the tester only talks to the Product Owner; the domain expert never DMs developers" live as hand-written sentences in `creation-pipeline.service.ts:188-216` `ROLE_TIPS`, copied into each persona's CLAUDE.md. Self-enforced by the agent + reinforced by workspace CLI scoping (e.g., testers can only file bugs, not comment on features). No HIVE-layer or DB-layer allow matrix exists today.

v2 adds a structured `communication_rules` field on the role template:

```yaml
communication_rules:
  can_dm:       [product-owner]          # role slugs this role is allowed to DM
  receives_dm:  [product-owner, '*']     # who is allowed to DM this role
  listens_to:   ['#support', '#general'] # HIVE channels this role monitors
  posts_to:     ['#support']             # HIVE channels this role can write to
```

The renderer turns these into consistent prose inside the CLAUDE.md snippet, so authors stop hand-writing role-boundary sentences and stop copy-pasting them across 26 templates. Enforcement still happens at the agent's discretion via CLAUDE.md — exactly like today — but the source of truth is now data, not prose. If HIVE ever grows per-agent ACLs, we wire enforcement to this field without changing how it's authored.

## 6. Versioning and auto-push

Each capability and each role template is versioned. Publishing a new version enqueues `sync_config` / `sync_files` daemon tasks to all agents running that capability with auto-update enabled. The existing daemon machinery handles the transport.

User overrides at the agent level (e.g. a platform admin edited CLAUDE.md for one specific agent) are preserved — that field stops receiving template updates, and the fleet view surfaces drift so nothing silently falls behind.

Canary rollout, dry-run preview, per-version telemetry — all post-MVP (§10).

## 7. Admin surfaces

**Platform admin** (extends AdminOffice):
- **Capabilities Library** — author and version capabilities.
- **Role Template Builder** — compose capabilities, live-preview the rendered CLAUDE.md, declare communication rules.
- **Integrations Library** — author integration catalog entries.
- **Fleet View** — which agents run which version, where overrides exist.

**Org admin** (extends TheOffice):
- **Per-agent setup** — fill required variables, pick which integration bindings this agent uses, edit CLAUDE.md overrides.
- **Integrations** — bind the org's accounts (Zendesk, Slack, email) via the existing `integration_connections` flow.

Each admin surface ships as its own routed page under `web/src/features/roles-v2/`. Nothing lands inside the TheOffice.tsx or AdminOffice.tsx monoliths.

## 8. Rollout: side-by-side with v1

v1 keeps running untouched. Add `agents.role_system_version INT NOT NULL DEFAULT 1`. All existing agents stay on 1; pilot-org agents get 2. One branch point in `daemonService.getAgentConfigForDaemon()` routes to either today's generator or the new renderer.

Pilot on 1–2 friendly orgs. If it works, open to new-org signup. Existing orgs opt in per-agent. v1 retirement is a separate later plan; indefinite coexistence is fine.

## 9. MVP prerequisites

Four upstream changes before v2 can pilot. None block the others.

1. **Generalize `activation_rules.rule_type`** — from hardcoded enum (bugs/testcases/features/potasks/pull_requests/hive) to free-text `trigger_source` + `trigger_config` JSONB. Orchestrator-only change; the saac-agent container ignores this field at runtime (verified with peer `ryanhiveagentbuilder`).
2. **Enforce tool allowlists end-to-end** — the existing `allowed_mcp_tools` field is stored but never read. saac-images extends `agent-sdk/src/agent.ts buildQueryOptions()` to read a `tools:` block from `agent.yaml` (restart-on-change is fine for MVP). Parser details in Appendix A. Coordinate with `ryanhiveagentbuilder`.
3. **Add the `role_system_version` column** — one migration.
4. **agentz exists** — a separate service in its own repo, scaffolded from skillz. Own CLI + own `/api/v1/agents/*` routes at its own host + own admin tokens + own mirror config + own install target (`~/.claude/agents/`). API shape is identical to skillz, so client code is portable — the orchestrator adds `AGENTZ_API_URL` + `AGENTZ_TOKEN` env vars alongside the existing skillz ones. Sync-time resolution of subagent manifests hits agentz; if we validate a subagent's `skills[]` references at authoring time, that's a separate call to skillz. Two services, two env vars, otherwise no new plumbing. **Out of scope for this repo** — a separate Claude instance is building agentz in its own repo.

## 10. Open questions (post-MVP)

- **Hot-reload** — CLAUDE.md / tools / subagents read per-query instead of on container restart. Dropped from MVP per user feedback; nice-to-have later.
- **Canary rollout** — two-tier capability versions (current + canary) with opt-in flag.
- **Audit log UI** — the versions tables record author + notes; UI comes later.
- **Dry-run preview** — "render this role template against a synthetic agent" inspector.
- **Per-capability-version telemetry** — activations, errors, token spend.
- **Third-party authoring** — orgs or partners publishing capabilities / integrations.
- **Capability conflict resolution** — priority ordering for contested files/events.
- **HIVE-layer enforcement of `communication_rules`** — today it's prose-plus-group-membership; could become real ACLs.

## 11. Out of scope

- Rewriting the agent daemon or HIVE protocol — unchanged.
- saac-agent container internals — unchanged except the two small extensions in §9.
- Billing / token quota per capability.
- Deploying as a separate microservice — v2 lives in-repo as `src/modules/roles-v2/` + `web/src/features/roles-v2/`. Module-level isolation keeps it off the TheOffice.tsx megafile trajectory.
- `agent_portraits.persona_name` — separate display-identity concept, untouched.
- Authoring v2 capabilities *as* skillz/agentz artifacts — capabilities are a distinct orchestrator-side authoring layer. They *reference* skills and subagents.
- First-class skill materialization for the main agent — deferred. Subagents (which do have a `skills: []` field in the SDK) cover the specialist-with-skills case. Revisit if a real main-agent skill use case emerges.

---

## Appendix A: Implementation notes

Parser semantics, merge rules, and other details for the builder.

**Tool allowlist parser (§9.2)**
- Fold into `/app/config/agent.yaml` under a `tools:` block. No new `tools.json`. No new sync type.
- Daemon writes with write-then-rename for atomicity.
- On parse failure, agent-sdk falls back to hardcoded defaults, not crash.
- Disallow wins on conflict (matches SDK semantics).
- Two axes: tool *names* (allow/disallow list) vs MCP *servers* (mounted at boot via `setup-claude-mcp.sh`). Capability manifests keep them separate; MCP server changes are restart-level.

**Subagent delivery (MVP: filesystem)**
- Orchestrator resolves each capability's referenced subagent from the agentz catalog at sync time and writes `.claude/agents/{slug}.md` with YAML frontmatter per Claude Code spec.
- Filesystem subagents are startup-only in Claude Code, so a container bounce on `sync_config` picks them up. Fine for MVP.
- Post-MVP hot-reload path (if pursued): saac-images parses a `subagents:` block in `agent.yaml` and passes programmatically to the SDK `agents: {}` option. Parser rules agreed with `ryanhiveagentbuilder`:
  - Partial validation — bad entry logged and skipped, rest kept.
  - Tool intersection lives in agent-sdk, not orchestrator.
  - Model precedence: `subagent.model > ANTHROPIC_MODEL env > SDK default`.
  - Session-resume: subagent config is per-query; in-flight calls use the definition they launched with.

**CLAUDE.md rendering order**
Stable → volatile. Identity → core capabilities → role capabilities → integration contributions → role template override → per-agent user override. Keeps the prompt-cacheable prefix stable.

**Merge rules for capability contributions**
- Scripts / custom files — by filename; later layer wins.
- Crontabs — concatenate, each entry source-tagged.
- Tools — `allow` union, `disallow` union; disallow wins on conflict.
- Subagents — by slug; later layer wins.

**Subagent version pinning (flagged by peer `skillz`)**
Capability manifests pin subagents to concrete version numbers, never `@latest`. Orchestrator resolves at capability-save time via `GET ${AGENTZ_API_URL}/api/v1/agents/{name}`. Reason: `normalize_to_targz` is byte-deterministic for pinned versions but not `@latest` — otherwise re-syncs drift silently. Skills follow the same rule against `SKILLZ_API_URL`.

**Integrations**
Reuse existing `integration_catalog` + `integration_connections` + remote AES-256-GCM credential storage on `apps.startanaicompany.com`. Capabilities declare `consumes_integrations: [{ catalog_slug, env_needed[] }]`. Credentials inject as env vars through the existing daemon flow. No new infrastructure.

**Events**
No pub/sub; codebase is request-response + HIVE. "Capability emits X event" = capability sends a HIVE message in a conventional shape on a known channel. Bridges/workers subscribe via existing HIVE webhook registration.

**Communication-rules rendering**
The `communication_rules` structured field is transformed by the renderer into prose sentences inside the role template's CLAUDE.md snippet — e.g. `can_dm: [product-owner]` → "You only send direct messages to agents with the role `product-owner`. Never DM anyone else." This replaces the hand-written `ROLE_TIPS` strings in `creation-pipeline.service.ts:188-216`.

---

## Appendix B: Revision history

- Fresh-eyes review against v1 codebase (daemon contract, integration_catalog, activation rules, MCP tools) and against saac-images agent-sdk runtime (via peer `ryanhiveagentbuilder`).
- Integration model rebuilt on existing `integration_catalog`; pub/sub abstraction dropped.
- Subagent support verified against Claude Code docs (filesystem subagents = startup-only; programmatic `agents: {}` = hot-reloadable). MVP uses filesystem.
- Subagent distribution via `agentz` (skillz sibling); Hybrid architecture confirmed with peer `skillz`.
- Parser semantics for saac-images extensions agreed with peer `ryanhiveagentbuilder`.
- Hot-reload dropped as an MVP requirement (moved to §10) per user feedback.
- Communication rules section added based on investigation of HIVE security groups (`agent-hive.service.ts:292-509`) and the prose-based enforcement in `creation-pipeline.service.ts:188-216` `ROLE_TIPS`.
- Aggressive simplification pass: full manifest YAML examples, field-level version schema tables, and detailed merge rules moved from the main sections to Appendix A. Main doc is now ~5-minute-read broad-strokes; appendix holds implementation detail.
- Renamed the primitive from "persona template" to **role template** throughout. v2 schema uses `role_templates`; v1's `agent_persona_templates` keeps its name so the two coexist without ambiguity. Module paths use `roles-v2`. Agent-level switch is `agents.role_system_version`.
- agentz pivoted from Hybrid (skillz sibling, shared backend) to Full Clone (separate repo, separate service, separate deploy) on 2026-04-22. API shape unchanged; orchestrator adds `AGENTZ_API_URL` + `AGENTZ_TOKEN` env vars alongside the existing skillz ones. Cross-kind references (a subagent listing `skills[]`) now require two calls — agentz for the subagent, skillz to validate the referenced skill names.
- Rolez itself was externalised on 2026-04-29 from `src/modules/roles-v2/` (the home this doc originally proposed) into a standalone microservice mirroring skillz/agentz. Lives at `rolez.startanaicompany.com`. Adds an `image` field to the role-template manifest (the original doc predated the "agents/assistants differ by image" decision). Auth for assistants is delegated upstream — they present their existing tech.saac MCP key, rolez verifies it via `tools/list`. Admin CRUD uses a single env-var api key (`ROLEZ_ADMIN_API_KEY`) consumed by the tech.saac admin UI.
