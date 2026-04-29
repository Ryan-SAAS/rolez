import {
  EXIT_AUTH,
  EXIT_CALLER,
  EXIT_NETWORK,
  EXIT_NOT_FOUND,
  die,
} from "./errors.js";
import type { Config } from "./config.js";
import type { ProvisionResult, RoleDetailOut, RoleListOut } from "./types.js";

const USER_AGENT = "@startanaicompany/rolez-cli";

function authHeaders(cfg: Config): Record<string, string> {
  return {
    Authorization: `ApiKey ${cfg.apiKey}`,
    "User-Agent": USER_AGENT,
  };
}

async function request(
  cfg: Config,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = cfg.apiUrl + path;
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...authHeaders(cfg),
        ...(init.headers as Record<string, string> | undefined),
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    die(EXIT_NETWORK, `network error: ${msg}`);
  }
  if (resp.status === 401) {
    die(EXIT_AUTH, "unauthorized (check ROLEZ_API_KEY / MCP_ORCHESTRATOR_API_KEY)");
  }
  if (resp.status === 404) {
    die(EXIT_NOT_FOUND, `not found: ${path}`);
  }
  if (resp.status >= 400 && resp.status < 500) {
    const body = await resp.text().catch(() => "");
    die(EXIT_CALLER, `client error ${resp.status}: ${body}`);
  }
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    die(EXIT_NETWORK, `server error ${resp.status}: ${body}`);
  }
  return resp;
}

export async function listRoles(
  cfg: Config,
  opts: { tag?: string; kind?: string } = {},
): Promise<RoleListOut> {
  const params = new URLSearchParams();
  if (opts.tag) params.set("tag", opts.tag);
  if (opts.kind) params.set("kind", opts.kind);
  const qs = params.toString();
  const path = "/api/v1/roles" + (qs ? `?${qs}` : "");
  const resp = await request(cfg, path);
  return (await resp.json()) as RoleListOut;
}

export async function searchRoles(cfg: Config, query: string): Promise<RoleListOut> {
  const params = new URLSearchParams({ q: query });
  const resp = await request(cfg, `/api/v1/roles/search?${params}`);
  return (await resp.json()) as RoleListOut;
}

export async function showRole(
  cfg: Config,
  slug: string,
  version?: string,
): Promise<RoleDetailOut> {
  const path = version
    ? `/api/v1/roles/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}`
    : `/api/v1/roles/${encodeURIComponent(slug)}`;
  const resp = await request(cfg, path);
  return (await resp.json()) as RoleDetailOut;
}

export interface ProvisionPayload {
  organization_id: string;
  product_id: string;
  name: string;
  version?: string;
  variables?: Record<string, string>;
  integration_bindings?: { catalog_slug: string; connection_id: string }[];
  extra_skills?: { name: string; version: string }[];
  extra_subagents?: { name: string; version: string }[];
}

export async function provisionRole(
  cfg: Config,
  slug: string,
  payload: ProvisionPayload,
): Promise<ProvisionResult> {
  const resp = await request(cfg, `/api/v1/roles/${encodeURIComponent(slug)}/provision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await resp.json()) as ProvisionResult;
}
