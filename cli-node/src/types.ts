/**
 * Wire types for the rolez API. These mirror the resolved (pinned) shape
 * the server stores and serves. The CLI consumes only — it never builds
 * a manifest, so a single pinned form is enough; we don't model the
 * server-side draft variant here.
 */

export interface RoleSummary {
  readonly slug: string;
  readonly display_name?: string | null;
  readonly description?: string | null;
  readonly kind: string;
  readonly tags: readonly string[];
  readonly latest_version: string | null;
  readonly versions_count: number;
  readonly created_at: string;
  readonly updated_at: string;
  readonly deleted_at?: string | null;
}

export interface RoleListOut {
  readonly total: number;
  readonly items: readonly RoleSummary[];
}

export interface NamedRef {
  readonly name: string;
  readonly version: string;
}

export interface ImageRef {
  readonly ref: string;
  readonly version: string;
}

export interface Identity {
  readonly name: string;
  readonly icon?: string | null;
  readonly tone?: string | null;
  readonly description?: string | null;
}

export interface ContextFile {
  readonly name: string;
  readonly content: string;
}

/**
 * Rolez owns the recruiting brief: image, identity, skills, subagents,
 * and the role-specific context appended to tech.saac's default.
 * Everything else (tools, prompts, inputs/outputs, integrations, variables,
 * communication rules) is tech.saac's concern, controlled via its admin UI.
 */
export interface RoleManifest {
  readonly image: ImageRef;
  readonly identity: Identity;
  readonly skills: readonly NamedRef[];
  readonly subagents: readonly NamedRef[];
  readonly context_files: readonly ContextFile[];
}

export interface RoleVersionSummary {
  readonly version: string;
  readonly manifest_sha256: string;
  readonly created_at: string;
}

export interface RoleDetailOut extends RoleSummary {
  readonly manifest?: RoleManifest;
  readonly manifest_sha256?: string;
  readonly versions: readonly RoleVersionSummary[];
}

