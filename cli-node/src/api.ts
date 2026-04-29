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

// Exposed for unit tests; not part of the public CLI API surface.
export function _describeFetchError_forTesting(err: unknown): string {
  return describeFetchError(err);
}

function describeFetchError(err: unknown): string {
  // Node 18+ fetch puts the actual underlying socket / DNS / cert error in
  // `err.cause` while `err.message` is the unhelpful "fetch failed". Surface
  // both so users have something to act on.
  let msg = err instanceof Error ? err.message : String(err);
  if (err instanceof Error && "cause" in err && err.cause) {
    const cause = err.cause;
    const causeMsg = cause instanceof Error ? cause.message : String(cause);
    if (causeMsg && !msg.includes(causeMsg)) {
      msg += ` (cause: ${causeMsg})`;
    }
  }
  return msg;
}

async function readBodySafe(resp: Response): Promise<string> {
  try {
    return await resp.text();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return `<body read failed: ${msg}>`;
  }
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
    die(EXIT_NETWORK, `network error: ${describeFetchError(err)}`);
  }
  if (resp.status === 401) {
    die(EXIT_AUTH, "unauthorized (check ROLEZ_API_KEY / MCP_ORCHESTRATOR_API_KEY)");
  }
  if (resp.status === 404) {
    die(EXIT_NOT_FOUND, `not found: ${path}`);
  }
  if (resp.status >= 400 && resp.status < 500) {
    die(EXIT_CALLER, `client error ${resp.status}: ${await readBodySafe(resp)}`);
  }
  if (!resp.ok) {
    die(EXIT_NETWORK, `server error ${resp.status}: ${await readBodySafe(resp)}`);
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
