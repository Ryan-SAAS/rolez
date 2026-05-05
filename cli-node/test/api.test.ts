import { test } from "node:test";
import assert from "node:assert/strict";

import { listRoles, showRole } from "../src/api.ts";

const cfg = { apiUrl: "https://rolez.example", apiKey: "test-token" };

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>): () => void {
  const orig = globalThis.fetch;
  globalThis.fetch = ((url: string | URL | Request, init?: RequestInit) =>
    impl(typeof url === "string" ? url : url.toString(), init)) as typeof fetch;
  return () => {
    globalThis.fetch = orig;
  };
}

test("listRoles sends ApiKey header and parses items", async () => {
  let captured: { url: string; auth?: string } = { url: "" };
  const restore = mockFetch(async (url, init) => {
    captured = {
      url,
      auth: (init?.headers as Record<string, string> | undefined)?.Authorization,
    };
    return new Response(JSON.stringify({ total: 1, items: [{ slug: "x", latest_version: "1.0.0", kind: "agent", tags: [], versions_count: 1, created_at: "", updated_at: "" }] }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  try {
    const out = await listRoles(cfg);
    assert.equal(out.total, 1);
    assert.equal(out.items[0]!.slug, "x");
    assert.equal(captured.auth, "ApiKey test-token");
    assert.equal(captured.url, "https://rolez.example/api/v1/roles");
  } finally {
    restore();
  }
});

test("listRoles forwards tag and kind filters", async () => {
  let captured = "";
  const restore = mockFetch(async (url) => {
    captured = url;
    return new Response(JSON.stringify({ total: 0, items: [] }), { status: 200 });
  });
  try {
    await listRoles(cfg, { tag: "support", kind: "agent" });
    assert.ok(captured.includes("tag=support"));
    assert.ok(captured.includes("kind=agent"));
  } finally {
    restore();
  }
});

test("showRole appends /versions/<v> when version supplied", async () => {
  let captured = "";
  const restore = mockFetch(async (url) => {
    captured = url;
    return new Response(JSON.stringify({ slug: "support-agent", kind: "agent", tags: [], versions_count: 1, latest_version: "0.1.0", versions: [], created_at: "", updated_at: "" }), { status: 200 });
  });
  try {
    await showRole(cfg, "support-agent", "0.1.0");
    assert.ok(captured.endsWith("/api/v1/roles/support-agent/versions/0.1.0"));
  } finally {
    restore();
  }
});

