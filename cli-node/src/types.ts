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

/**
 * Rolez owns the recruiting brief: image, skills, subagents, plugins, and
 * one `context` text appended to tech.saac's default CLAUDE.md at
 * daemon-config-build time. Everything else (identity, kind, tools,
 * prompts, env vars, integrations, comm rules) is tech.saac's concern.
 */
export interface RoleManifest {
  readonly image: ImageRef;
  readonly skills: readonly NamedRef[];
  readonly subagents: readonly NamedRef[];
  readonly plugins: readonly NamedRef[];
  readonly context: string;
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

