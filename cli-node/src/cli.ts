#!/usr/bin/env node
import { parseArgs } from "node:util";

import { listRoles, provisionRole, searchRoles, showRole } from "./api.js";
import { loadConfig } from "./config.js";
import { EXIT_OK, EXIT_USAGE, die } from "./errors.js";
import type { RoleManifest, RoleSummary } from "./types.js";

const VERSION = "0.1.0";

const USAGE = `rolez — agent-side CLI for the rolez role registry + provisioner

usage: rolez <command> [options]

commands:
  list [--tag <t>] [--kind agent|assistant] [--json]
                                    list available roles
  search <query> [--json]           full-text search over slug + description
  show <slug>[@version]             show role manifest (resolved skills/subagents/image)
  inspect <slug>[@version]          show + summarise referenced parts
  provision <slug> --org <id> --product <id> --name <name>
            [--version <v>] [--var KEY=value]... [--skill name@version]...
            [--subagent name@version]... [--binding catalog=connection_id]...
                                    instantiate an agent of this role on tech.saac

env:
  ROLEZ_API_URL                 required  e.g. https://rolez.startanaicompany.com
  ROLEZ_API_KEY                 required  the assistant's tech.saac MCP api key
                                          (also accepts MCP_ORCHESTRATOR_API_KEY)

exit codes: 0 ok  1 usage  2 auth  3 not found  4 network  5 client error
`;

function parseTarget(arg: string): { name: string; version?: string } {
  const at = arg.indexOf("@");
  if (at === -1) return { name: arg };
  return { name: arg.slice(0, at), version: arg.slice(at + 1) || undefined };
}

function parseKv(values: string[] | undefined, label: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const kv of values ?? []) {
    const eq = kv.indexOf("=");
    if (eq === -1) die(EXIT_USAGE, `${label} must be KEY=value, got ${JSON.stringify(kv)}`);
    out[kv.slice(0, eq)] = kv.slice(eq + 1);
  }
  return out;
}

function parseVersionedRefs(values: string[] | undefined, label: string): { name: string; version: string }[] {
  return (values ?? []).map((v) => {
    const t = parseTarget(v);
    if (!t.version) die(EXIT_USAGE, `${label} entry must be name@version, got ${JSON.stringify(v)}`);
    return { name: t.name, version: t.version };
  });
}

function parseBindings(values: string[] | undefined): { catalog_slug: string; connection_id: string }[] {
  return (values ?? []).map((v) => {
    const eq = v.indexOf("=");
    if (eq === -1) die(EXIT_USAGE, `--binding must be catalog_slug=connection_id, got ${JSON.stringify(v)}`);
    return { catalog_slug: v.slice(0, eq), connection_id: v.slice(eq + 1) };
  });
}

function formatRoleRow(s: RoleSummary, slugW: number, verW: number): string {
  const ver = s.latest_version ?? "-";
  const desc = (s.description ?? "").replace(/\s+/g, " ").trim();
  return `${s.slug.padEnd(slugW)}  ${ver.padEnd(verW)}  ${desc}`;
}

async function cmdList(args: string[]): Promise<number> {
  const { values } = parseArgs({
    args,
    options: {
      tag: { type: "string" },
      kind: { type: "string" },
      json: { type: "boolean" },
    },
    strict: true,
    allowPositionals: false,
  });
  const cfg = loadConfig();
  const data = await listRoles(cfg, { tag: values.tag, kind: values.kind });
  if (values.json) {
    process.stdout.write(JSON.stringify(data.items, null, 2) + "\n");
    return EXIT_OK;
  }
  if (data.items.length === 0) {
    console.log("(no roles)");
    return EXIT_OK;
  }
  const slugW = Math.max(4, ...data.items.map((i) => i.slug.length));
  const verW = Math.max(7, ...data.items.map((i) => (i.latest_version ?? "-").length));
  for (const r of data.items) console.log(formatRoleRow(r, slugW, verW));
  return EXIT_OK;
}

async function cmdSearch(args: string[]): Promise<number> {
  const { values, positionals } = parseArgs({
    args,
    options: { json: { type: "boolean" } },
    strict: true,
    allowPositionals: true,
  });
  if (positionals.length !== 1) die(EXIT_USAGE, "usage: rolez search <query>");
  const cfg = loadConfig();
  const data = await searchRoles(cfg, positionals[0]!);
  if (values.json) {
    process.stdout.write(JSON.stringify(data.items, null, 2) + "\n");
    return EXIT_OK;
  }
  if (data.items.length === 0) {
    console.log("(no matches)");
    return EXIT_OK;
  }
  for (const r of data.items) {
    const desc = (r.description ?? "").replace(/\s+/g, " ").trim();
    console.log(`${r.slug} (${r.latest_version ?? "-"}) — ${desc}`);
  }
  return EXIT_OK;
}

async function cmdShow(args: string[]): Promise<number> {
  const { positionals } = parseArgs({
    args,
    options: {},
    strict: true,
    allowPositionals: true,
  });
  if (positionals.length !== 1) die(EXIT_USAGE, "usage: rolez show <slug>[@version]");
  const target = parseTarget(positionals[0]!);
  const cfg = loadConfig();
  const data = await showRole(cfg, target.name, target.version);
  process.stdout.write(JSON.stringify(data, null, 2) + "\n");
  return EXIT_OK;
}

async function cmdInspect(args: string[]): Promise<number> {
  const { positionals } = parseArgs({
    args,
    options: {},
    strict: true,
    allowPositionals: true,
  });
  if (positionals.length !== 1) die(EXIT_USAGE, "usage: rolez inspect <slug>[@version]");
  const target = parseTarget(positionals[0]!);
  const cfg = loadConfig();
  const data = await showRole(cfg, target.name, target.version);
  const manifest = data.manifest as RoleManifest | undefined;
  if (!manifest) {
    process.stdout.write(JSON.stringify(data, null, 2) + "\n");
    return EXIT_OK;
  }
  console.log(`role:      ${data.slug}@${data.latest_version ?? target.version ?? "?"}`);
  console.log(`image:     ${manifest.image.ref}@${manifest.image.version}`);
  console.log("skills:");
  for (const s of manifest.skills ?? []) console.log(`  - ${s.name}@${s.version}`);
  console.log("subagents:");
  for (const s of manifest.subagents ?? []) console.log(`  - ${s.name}@${s.version}`);
  const reqVars = (manifest.required_variables ?? []).map((v) => v.name);
  console.log(`required_variables: ${JSON.stringify(reqVars)}`);
  return EXIT_OK;
}

async function cmdProvision(args: string[]): Promise<number> {
  const { values, positionals } = parseArgs({
    args,
    options: {
      org: { type: "string" },
      product: { type: "string" },
      name: { type: "string" },
      version: { type: "string" },
      var: { type: "string", multiple: true },
      skill: { type: "string", multiple: true },
      subagent: { type: "string", multiple: true },
      binding: { type: "string", multiple: true },
      json: { type: "boolean" },
    },
    strict: true,
    allowPositionals: true,
  });
  if (positionals.length !== 1) die(EXIT_USAGE, "usage: rolez provision <slug> --org <id> --product <id> --name <name>");
  if (!values.org) die(EXIT_USAGE, "--org is required");
  if (!values.product) die(EXIT_USAGE, "--product is required");
  if (!values.name) die(EXIT_USAGE, "--name is required");

  const cfg = loadConfig();
  const result = await provisionRole(cfg, positionals[0]!, {
    organization_id: values.org,
    product_id: values.product,
    name: values.name,
    version: values.version ?? "latest",
    variables: parseKv(values.var, "--var"),
    integration_bindings: parseBindings(values.binding),
    extra_skills: parseVersionedRefs(values.skill, "--skill"),
    extra_subagents: parseVersionedRefs(values.subagent, "--subagent"),
  });

  if (values.json) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    return EXIT_OK;
  }
  const id = result.agent_id ?? "<no agent_id returned>";
  console.log(`provisioned ${positionals[0]}@${result.role_version} as agent ${id}`);
  return EXIT_OK;
}

const COMMANDS: Record<string, (args: string[]) => Promise<number>> = {
  list: cmdList,
  search: cmdSearch,
  show: cmdShow,
  inspect: cmdInspect,
  provision: cmdProvision,
};

async function main(): Promise<void> {
  const [cmd, ...rest] = process.argv.slice(2);
  if (!cmd || cmd === "-h" || cmd === "--help" || cmd === "help") {
    process.stdout.write(USAGE);
    process.exit(EXIT_OK);
  }
  if (cmd === "--version" || cmd === "-V") {
    console.log(VERSION);
    process.exit(EXIT_OK);
  }
  const fn = COMMANDS[cmd];
  if (!fn) {
    die(EXIT_USAGE, `unknown command ${JSON.stringify(cmd)}\n${USAGE}`);
  }
  const code = await fn(rest);
  process.exit(code);
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  die(4, `unhandled: ${msg}`);
});
