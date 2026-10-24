// Preload for cli-wiring.test.ts: records whether the CLI filtered the trust
// list before its first fetch, then answers that fetch with an empty list.
import { createRequire, syncBuiltinESMExports } from "node:module";

const tls = createRequire(import.meta.url)("node:tls");
let applied = false;
tls.setDefaultCACertificates = () => {
  applied = true;
};
tls.getCACertificates ??= () => [];
syncBuiltinESMExports();
globalThis.fetch = async () => {
  process.stderr.write(`trust-policy-before-fetch=${applied}\n`);
  return new Response(JSON.stringify({ total: 0, items: [] }), { status: 200 });
};
