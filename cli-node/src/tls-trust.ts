// Removes distrusted root certificates from Node's built-in trust list.
//
// On 2026-10-20 the private keys of every eMudhra (emSign) CA were shown to be
// trivially weak, so anyone can mint certificates those roots will vouch for.
// Node ships its own copy of the Mozilla root list and ignores the OS store, so
// an OS ca-certificates update does not reach this CLI. Even Node 24.22.1 still
// trusts "emSign Root CA - G1". Ubuntu also pulled Comodo's "AAA Certificate
// Services", which cross-signed eMudhra; we drop it for the same reason. A fake
// certificate for the rolez API would leak the agent's SAAC_AGENT_API_KEY.
//
// Delete this once Node's bundled list no longer contains these roots.

import { X509Certificate } from "node:crypto";
import * as tls from "node:tls";

// Any root whose subject names eMudhra as its organisation.
const DISTRUSTED_ORG = /\bO=eMudhra\b/;

// SHA-256 of Comodo "AAA Certificate Services".
const DISTRUSTED_FINGERPRINTS = new Set([
  "D7:A7:A0:FB:5D:7E:27:31:D7:71:E9:48:4E:BC:DE:F7:1D:5F:0C:3E:0A:29:48:78:2B:C8:3E:E0:EA:69:9E:F4",
]);

export function isDistrustedRoot(pem: string): boolean {
  const cert = new X509Certificate(pem);
  return DISTRUSTED_ORG.test(cert.subject) || DISTRUSTED_FINGERPRINTS.has(cert.fingerprint256);
}

// tls.getCACertificates / setDefaultCACertificates exist from Node 22.19 / 24.5.
export interface TlsTrustApi {
  getCACertificates?: (type: "default") => string[];
  setDefaultCACertificates?: (certs: string[]) => void;
}

// Silent on success: stdout is the CLI's output and agents parse it.
export function applyTlsTrustPolicy(api: TlsTrustApi = tls as unknown as TlsTrustApi): number {
  if (!api.getCACertificates || !api.setDefaultCACertificates) {
    process.stderr.write(
      "rolez: warning: this Node cannot edit its trust list; eMudhra roots are still trusted. Upgrade to Node 22.23.4+ or 24.22.1+.\n",
    );
    return 0;
  }
  const current = api.getCACertificates("default");
  const kept = current.filter((pem) => !isDistrustedRoot(pem));
  api.setDefaultCACertificates(kept);
  return current.length - kept.length;
}
