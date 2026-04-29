export interface RoleSummary {
  slug: string;
  display_name?: string | null;
  description?: string | null;
  kind: string;
  tags: string[];
  latest_version: string | null;
  versions_count: number;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export interface RoleListOut {
  total: number;
  items: RoleSummary[];
}

export interface RoleManifestRef {
  name: string;
  version: string;
}

export interface RoleManifest {
  image: { ref: string; version: string };
  identity: { name: string; icon?: string | null; tone?: string | null; description?: string | null };
  skills: RoleManifestRef[];
  subagents: RoleManifestRef[];
  required_variables?: { name: string; description?: string | null; default?: string | null }[];
  // ...other fields are passed through verbatim by the server.
}

export interface RoleDetailOut extends RoleSummary {
  manifest?: RoleManifest;
  manifest_sha256?: string;
  versions: { version: string; manifest_sha256: string; created_at: string }[];
}

export interface ProvisionResult {
  agent_id: string | null;
  role_slug: string;
  role_version: string;
  status: number;
  tech_saac_response?: unknown;
  error?: string | null;
}
