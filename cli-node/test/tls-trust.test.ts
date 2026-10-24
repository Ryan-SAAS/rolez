import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { X509Certificate } from "node:crypto";
import * as tls from "node:tls";

import { applyTlsTrustPolicy, isDistrustedRoot } from "../src/tls-trust.ts";

function bySubject(cn: string): string {
  const pem = tls.rootCertificates.find((p) => new X509Certificate(p).subject.includes(`CN=${cn}`));
  if (!pem) throw new Error(`root ${cn} missing from Node's bundle`);
  return pem;
}

// Node 24's bundle no longer carries the Comodo root, so it comes from Node 18.20.8's.
const COMODO_AAA = readFileSync(new URL("./comodo-aaa-root.pem", import.meta.url), "utf8");
// Subject "O=eMudhra Inc" (G1 says "O=eMudhra Technologies Limited"); taken from Debian's store.
const EMSIGN_C1 = readFileSync(new URL("./emsign-c1-root.pem", import.meta.url), "utf8");
const EMSIGN_G1 = bySubject("emSign Root CA - G1");
const ISRG_X1 = bySubject("ISRG Root X1");
const DIGICERT = bySubject("DigiCert Global Root G2");

test("isDistrustedRoot flags eMudhra and Comodo AAA, keeps mainstream roots", () => {
  assert.equal(isDistrustedRoot(EMSIGN_G1), true);
  assert.equal(isDistrustedRoot(EMSIGN_C1), true);
  assert.equal(isDistrustedRoot(COMODO_AAA), true);
  assert.equal(isDistrustedRoot(ISRG_X1), false);
  assert.equal(isDistrustedRoot(DIGICERT), false);
});

test("applyTlsTrustPolicy sets the default list without the distrusted roots", () => {
  let set: string[] | undefined;
  const removed = applyTlsTrustPolicy({
    getCACertificates: () => [ISRG_X1, EMSIGN_G1, DIGICERT, COMODO_AAA],
    setDefaultCACertificates: (certs) => {
      set = certs;
    },
  });
  assert.equal(removed, 2);
  assert.deepEqual(set, [ISRG_X1, DIGICERT]);
});

test("applyTlsTrustPolicy warns on stderr and changes nothing without the API", (t) => {
  const writes: string[] = [];
  t.mock.method(process.stderr, "write", (s: string) => {
    writes.push(s);
    return true;
  });
  assert.equal(applyTlsTrustPolicy({}), 0);
  assert.match(writes.join(""), /still trusted/);
});

test("applyTlsTrustPolicy on the real runtime drops every eMudhra root", () => {
  const api = tls as unknown as { getCACertificates?: (t: "default") => string[] };
  if (!api.getCACertificates) return;
  applyTlsTrustPolicy();
  // Independent of isDistrustedRoot, so narrowing that check cannot hide a leftover.
  const left = api.getCACertificates("default").filter((p) => /eMudhra|emSign/i.test(new X509Certificate(p).subject));
  assert.equal(left.length, 0);
});
