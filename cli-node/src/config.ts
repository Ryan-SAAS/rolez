import { EXIT_USAGE, die } from "./errors.js";

export interface Config {
  apiUrl: string;
  apiKey: string;
}

export function loadConfig(): Config {
  const apiUrl = (process.env.ROLEZ_API_URL ?? "").replace(/\/+$/, "");
  if (!apiUrl) {
    die(EXIT_USAGE, "missing required env var ROLEZ_API_URL");
  }

  // Accept ROLEZ_API_KEY as the canonical name; fall back to
  // MCP_ORCHESTRATOR_API_KEY (the env name @startanaicompany/techsaac-cli uses)
  // so assistants don't have to plumb a second key.
  const apiKey = process.env.ROLEZ_API_KEY ?? process.env.MCP_ORCHESTRATOR_API_KEY ?? "";
  if (!apiKey) {
    die(EXIT_USAGE, "missing required env var ROLEZ_API_KEY (or MCP_ORCHESTRATOR_API_KEY)");
  }

  return { apiUrl, apiKey };
}
