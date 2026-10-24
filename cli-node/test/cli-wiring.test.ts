import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const run = (args: string[]) =>
  spawnSync(
    process.execPath,
    [
      "--import",
      "tsx/esm",
      "--import",
      fileURLToPath(new URL("./tls-wiring-preload.mjs", import.meta.url)),
      fileURLToPath(new URL("../src/cli.ts", import.meta.url)),
      ...args,
    ],
    { encoding: "utf8", env: { ...process.env, SAAC_AGENT_API_KEY: "test-token", ROLEZ_API_URL: "https://rolez.example" } },
  );

test("cli applies the TLS trust policy before its first network call", () => {
  const out = run(["list", "--json"]);
  assert.equal(out.status, 0, out.stderr);
  assert.match(out.stderr, /trust-policy-before-fetch=true/);
});

test("cli --version makes no network call", () => {
  const out = run(["--version"]);
  assert.equal(out.status, 0, out.stderr);
  assert.doesNotMatch(out.stderr, /trust-policy-before-fetch/);
});
