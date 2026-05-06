import { EXIT_USAGE, die } from "./errors.js";

const DEFAULT_API_URL = "https://rolez.startanaicompany.com";

export interface Config {
  apiUrl: string;
  apiKey: string;
}

export function loadConfig(): Config {
  const apiUrl = (process.env.ROLEZ_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");

  // SAAC_AGENT_API_KEY is the per-agent us_*-token tech.saac injects into
  // every container. It is the only credential the rolez CLI accepts — it's
  // semantically distinct from MCP_ORCHESTRATOR_API_KEY (techsaac-cli
  // shared key) and ROLEZ_API_KEY (rolez admin key); using either of those
  // would be a category error.
  const apiKey = process.env.SAAC_AGENT_API_KEY ?? "";
  if (!apiKey) {
    die(EXIT_USAGE, "missing required env var SAAC_AGENT_API_KEY");
  }

  return { apiUrl, apiKey };
}
