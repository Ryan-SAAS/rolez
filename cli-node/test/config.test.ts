import { test } from "node:test";
import assert from "node:assert/strict";

import { loadConfig } from "../src/config.ts";

const ENV_KEYS = [
  "ROLEZ_API_URL",
  "SAAC_AGENT_API_KEY",
  "ROLEZ_API_KEY",
  "MCP_ORCHESTRATOR_API_KEY",
] as const;

function withEnv<T>(env: Partial<Record<string, string>>, fn: () => T): T {
  const saved = new Map<string, string | undefined>();
  for (const k of ENV_KEYS) saved.set(k, process.env[k]);
  for (const k of ENV_KEYS) delete process.env[k];
  for (const [k, v] of Object.entries(env)) if (v !== undefined) process.env[k] = v;
  try {
    return fn();
  } finally {
    for (const [k, v] of saved) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
  }
}

test("apiUrl defaults to prod when ROLEZ_API_URL unset", () => {
  withEnv({ SAAC_AGENT_API_KEY: "ag_x" }, () => {
    assert.equal(loadConfig().apiUrl, "https://rolez.startanaicompany.com");
  });
});

test("apiUrl honours explicit ROLEZ_API_URL and strips trailing slash", () => {
  withEnv({ ROLEZ_API_URL: "https://staging.example/", SAAC_AGENT_API_KEY: "ag_x" }, () => {
    assert.equal(loadConfig().apiUrl, "https://staging.example");
  });
});

test("loadConfig accepts SAAC_AGENT_API_KEY", () => {
  withEnv({ SAAC_AGENT_API_KEY: "ag_abcdef" }, () => {
    assert.equal(loadConfig().apiKey, "ag_abcdef");
  });
});

test("loadConfig IGNORES ROLEZ_API_KEY (different credential, must not be conflated)", () => {
  let exitCode: number | undefined;
  const origExit = process.exit.bind(process);
  // @ts-expect-error — override for test
  process.exit = (code?: number) => {
    exitCode = code;
    throw new Error("__exit__");
  };
  try {
    withEnv({ ROLEZ_API_KEY: "rolez_admin_key" }, () => {
      assert.throws(() => loadConfig(), /__exit__/);
    });
  } finally {
    process.exit = origExit;
  }
  assert.equal(exitCode, 1);
});

test("loadConfig IGNORES MCP_ORCHESTRATOR_API_KEY (different credential, must not be conflated)", () => {
  let exitCode: number | undefined;
  const origExit = process.exit.bind(process);
  // @ts-expect-error — override for test
  process.exit = (code?: number) => {
    exitCode = code;
    throw new Error("__exit__");
  };
  try {
    withEnv({ MCP_ORCHESTRATOR_API_KEY: "mcp_x" }, () => {
      assert.throws(() => loadConfig(), /__exit__/);
    });
  } finally {
    process.exit = origExit;
  }
  assert.equal(exitCode, 1);
});
