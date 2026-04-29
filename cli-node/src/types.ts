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

export interface Tools {
  readonly allow: readonly string[];
  readonly disallow: readonly string[];
}

export interface Prompt {
  readonly name: string;
  readonly body: string;
  readonly trigger_source?: string | null;
  readonly trigger_config?: Readonly<Record<string, unknown>>;
}

export interface IOEdge {
  readonly channel: string;
  readonly capability?: string | null;
}

export interface ConsumedIntegration {
  readonly catalog_slug: string;
  readonly env_needed: readonly string[];
}

export interface RequiredVariable {
  readonly name: string;
  readonly description?: string | null;
  readonly default?: string | null;
}

export interface CommunicationRules {
  readonly can_dm: readonly string[];
  readonly receives_dm: readonly string[];
  readonly listens_to: readonly string[];
  readonly posts_to: readonly string[];
}

export interface ContextFile {
  readonly path: string;
  readonly content: string;
}

export interface RoleManifest {
  readonly image: ImageRef;
  readonly identity: Identity;
  readonly skills: readonly NamedRef[];
  readonly subagents: readonly NamedRef[];
  readonly tools: Tools;
  readonly mcp_servers: readonly string[];
  readonly prompts: readonly Prompt[];
  readonly inputs: readonly IOEdge[];
  readonly outputs: readonly IOEdge[];
  readonly consumed_integrations: readonly ConsumedIntegration[];
  readonly required_variables: readonly RequiredVariable[];
  readonly communication_rules: CommunicationRules;
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

export interface ProvisionResult {
  readonly agent_id: string | null;
  readonly role_slug: string;
  readonly role_version: string;
  readonly status: number;
  readonly tech_saac_response?: unknown;
  readonly error?: string | null;
}
