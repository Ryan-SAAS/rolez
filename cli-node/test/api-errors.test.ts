import { test } from "node:test";
import assert from "node:assert/strict";

import { _describeFetchError_forTesting as describe } from "../src/api.ts";

test("describeFetchError surfaces err.cause when present", () => {
  const cause = new Error("ECONNREFUSED 192.0.2.1:443");
  const err: Error & { cause?: unknown } = new Error("fetch failed");
  err.cause = cause;
  const out = describe(err);
  assert.match(out, /fetch failed/);
  assert.match(out, /ECONNREFUSED/);
});

test("describeFetchError handles plain Error without cause", () => {
  const out = describe(new Error("dns failure"));
  assert.equal(out, "dns failure");
});

test("describeFetchError handles non-Error throws", () => {
  assert.equal(describe("plain string"), "plain string");
  assert.equal(describe(42), "42");
});

test("describeFetchError doesn't double-append when cause matches message", () => {
  const cause = new Error("same message");
  const err: Error & { cause?: unknown } = new Error("same message");
  err.cause = cause;
  const out = describe(err);
  assert.equal(out, "same message");
});
