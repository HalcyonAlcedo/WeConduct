/** WeConduct — API Response Types
 *  Mirrors the actual JSON responses from the Python backend.
 *  Verified against live backend @ 2026-06-18.
 */

import type { CompilationRequest, CompilationOutcome, CompileStatus } from './compilation'
import type { GraphModel } from './graph'
import type { DiagnosticGroup, DiagnosticSummary, PrimaryDiagnostic } from './diagnostics'
import type { GraphStats } from './graph'

// ===== Shared sub-types =====

export interface Capabilities {
  compiler_available: boolean
  runtime_available: boolean
  debug_available: boolean
}

export interface Entrypoints {
  snapshot: string
  compile_action: string
  graph_document?: string
  graph_validate_action?: string
  graph_compile_action?: string
  runtime_prepare_action?: string
  debug_prepare_action?: string
  host_info?: string
}

export interface UiHosting {
  ui_hosted: boolean
  ui_dist_available: boolean
  ui_dist_path: string
  ui_entrypoint: string | null
}

export interface SourceTemplate {
  entry_document: string
  source_text: string
}

// ===== GET /api/health =====

export interface HealthResponse {
  status: string
  service: string
  host_mode: string
  api_version: string
  workspace_state_version: number
  workspace_session_id: string
  service_started_at: string
  capabilities: Capabilities
  entrypoints: Entrypoints
  ui_hosting: UiHosting
}

// ===== GET /api/workbench/snapshot =====

export interface SnapshotWorkbench {
  host_mode: string
  api_version: string
  workspace_session_id: string
  service_started_at: string
  compile_counter: number
  workspace_state_version: number
}

export interface GraphCompatibilitySummary {
  status?: string; graph_data_version?: string; current_app_version?: string
  minimum_loader_app_version?: string; built_with_app_version?: string
  last_upgraded_by_app_version?: string; upgrade_history?: { from_version: string; to_version: string; upgrader_id: string; applied_at?: string }[]
  is_legacy_unversioned?: boolean; available_upgrade_path?: { from_version: string; to_version: string; upgrader_id: string }[]
}

export interface PendingGraphUpgrade {
  status: string; document_id?: string
  compatibility?: GraphCompatibilitySummary
  documents?: { document_id: string; document_role: string; display_name?: string; compatibility?: GraphCompatibilitySummary }[]
}

/** POST /api/workbench/project/graph-upgrade/recheck response */
export interface GraphUpgradeRecheckResponse {
  status: string
  project: Record<string, unknown>
  pending_graph_upgrade: PendingGraphUpgrade | null
}

export interface SnapshotProject {
  loaded: boolean
  project_id: string
  project_name: string
  project_status: string
  workspace_root: string
  has_persisted_workspace_state: boolean
  last_compile_status: CompileStatus | null
  last_compile_request_sequence: number | null
  /** P12: project storage model upgrade fields */
  project_file_schema_version?: string
  main_graph_path?: string
  project_resources_index_path?: string
  resource_overrides_path?: string
  /** 0.6.2: graph upgrade gate */
  pending_graph_upgrade?: PendingGraphUpgrade | null
}

export interface SnapshotCompiler {
  available_source_kinds: string[]
  default_source_kind: string
  supported_stage_names: string[]
  compile_statuses: string[]
  diagnostic_severities: string[]
  source_templates: Record<string, SourceTemplate>
  compile_history_limit: number
}

export interface StageCard {
  stage: string
  status: string
  diagnostic_count: number
}

export interface StageOverview {
  total_stage_count: number
  succeeded_stage_count: number
  failed_stage_count: number
  terminal_stage: string | null
}

export interface LastCompile {
  status: CompileStatus
  request_sequence: number
  compiled_at: string
  duration_ms: number | null
  source_kind: string
  entry_document: string
  stage_cards: StageCard[]
  stage_overview: StageOverview
  diagnostic_summary: DiagnosticSummary
  primary_diagnostic: PrimaryDiagnostic | null
  graph_stats: GraphStats
}

export interface SnapshotResponse {
  workbench: SnapshotWorkbench
  project: SnapshotProject
  capabilities: Capabilities
  entrypoints: Entrypoints
  compiler: SnapshotCompiler
  last_compile: LastCompile | null
  compile_history: LastCompile[]
  ui_hosting: UiHosting
  preferences?: Record<string, unknown>
  graph_workspace?: {
    graph_preferences?: Record<string, unknown>
    /** 嵌套分组对象: { program_settings: { default_project_directory: "active" }, ... } */
    preferences_state?: Record<string, Record<string, string>>
  }
  /** P16: lightweight project settings state */
  project_settings?: ProjectSettingsSnapshot
}

// ===== POST /api/workbench/compile =====

export interface CompileView {
  status: CompileStatus
  duration_ms: number | null
  stage_cards: StageCard[]
  stage_overview: StageOverview
  diagnostic_groups: DiagnosticGroup[]
  diagnostic_summary: DiagnosticSummary
  primary_diagnostic: PrimaryDiagnostic | null
  graph_stats: GraphStats
}

export interface CompileResponse {
  status: CompileStatus
  request: CompilationRequest
  outcome: CompilationOutcome
  view: CompileView
}

// ===== POST /api/workbench/compile request body =====

export interface CompileRequestBody {
  source_kind: string
  entry_document: string
  source_text: string
}

// ===== P3: Graph Workspace =====

export interface GraphDocumentView {
  authority_mode: string
  compile_source_authority: string
  graph_document_save_revision: number
  graph_document_saved_at: string | null
  last_compile_matches_saved_graph: boolean
  /** P16: false when wcrun loaded (graph is read-only) */
  is_editable?: boolean
}

export interface GraphDocumentResponse {
  graph_model: GraphModel | null
  view: GraphDocumentView
}

/** PUT body: graph model fields at top level, revision as sibling */
export type GraphSavePayload = Record<string, unknown> & {
  expected_graph_document_save_revision?: number
}

export interface GraphSaveResponse {
  status: string
  graph_model: import('./graph').GraphModel
  view: GraphDocumentView
}

// ===== P3: Graph Validate =====

export interface GraphValidateSummary {
  error_count: number
}

export interface GraphValidateResponse {
  status: 'valid' | 'invalid' | 'failed'
  summary: GraphValidateSummary
  diagnostics: import('./diagnostics').Diagnostic[]
}

// ===== P3: Graph Compile =====

export interface GraphCompileResponse {
  status: CompileStatus
  request: Record<string, unknown>
  outcome: CompilationOutcome
  view: CompileView
}

// ===== P3: Runtime Prepare =====

export interface RuntimePrepareRequest {
  graph_document?: Record<string, unknown>
}

export interface RuntimePlan {
  graph_model_id: string
  compilation_id: string
  node_count: number
  edge_count: number
  start_node_ids: string[]
  terminal_node_ids: string[]
  executable_nodes: ExecutableNode[]
  relation_edges: Record<string, unknown>[]
  viewport: Record<string, unknown> | null
}

export interface ExecutableNode {
  node_id: string
  display_name: string
  node_kind: string
  lowered_kind: string
  source_anchor_ref: string
  port_ids: string[]
  incoming_edge_ids: string[]
  outgoing_edge_ids: string[]
}

export interface RuntimePrepareResponse {
  status: 'ready' | 'failed'
  request: {
    compilation_id: string
    request_origin: string
    requested_graph_model_id: string | null
    requested_graph_save_revision: number | null
    requested_graph_saved_at: string | null
    compile_status: string
  }
  runtime_session: {
    session_id: string
    status: string
    execution_supported: boolean
  }
  runtime_plan: RuntimePlan | null
  diagnostics: {
    total_count: number
    highest_severity: string | null
    entries: import('./diagnostics').Diagnostic[]
  }
}

// ===== P3: Debug Prepare =====

export interface DebugPrepareRequest {
  graph_document?: Record<string, unknown>
}

export interface StageTimelineEntry {
  stage: string
  status: string
  diagnostic_count: number
}

export interface ObjectIndexNode {
  node_id: string
  source_anchor_ref: string
  display_name: string
  node_kind: string
  lowered_kind: string
  port_ids: string[]
}

export interface ObjectIndexPort {
  node_id: string
  port_id: string
  direction: string
  relation_layer: string
  semantic_slot: string
}

export interface ObjectIndexEdge {
  edge_id: string
  relation_layer: string
  from_node_id: string
  to_node_id: string
  from_port_id: string | null
  to_port_id: string | null
}

export interface ObjectIndex {
  graph_model_id: string
  nodes: ObjectIndexNode[]
  ports: ObjectIndexPort[]
  edges: ObjectIndexEdge[]
}

export interface DiagnosticLink {
  diagnostic_id: string
  stage: string
  severity: string
  category: string
  message: string
  object_ref: string | null
  trace_ref: string | null
  subject_ref: string | null
  source_ref: string | null
  graph_ref: Record<string, unknown> | null
}

export interface DebugPrepareResponse {
  status: 'ready' | 'failed'
  request: {
    compilation_id: string
    request_origin: string
    requested_graph_model_id: string | null
    requested_graph_save_revision: number | null
    requested_graph_saved_at: string | null
    compile_status: string
  }
  debug_session: {
    session_id: string
    status: string
    resume_supported: boolean
    breakpoint_slots: unknown[]
  }
  stage_timeline: StageTimelineEntry[]
  object_index: ObjectIndex | null
  diagnostic_links: DiagnosticLink[]
}

// ===== P3: Host Info =====

export interface HostInfoResponse {
  host_mode: string
  api_version: string
  server_bind: { host: string; port: number; base_url: string }
  ui_hosting: UiHosting
  release_manifest: {
    manifest_version: string; startup_command: string
    workspace_state_path: string; ui_dist_path: string
  }
}

// ===== P6: Project System =====

export interface ProjectDocumentResponse {
  project: {
    project_id: string; project_name: string; project_schema_version: string
    project_status: string; workspace_root: string; source_of_truth: string
    main_graph_document_id: string; resource_registry_revision: number
    project_file_path: string | null; project_file_name: string | null
    is_dirty: boolean; recent_project_count: number; recent_projects: RecentProject[]
    has_persisted_workspace_state: boolean
    last_compile_status: string | null; last_compile_request_sequence: number | null
    /** P12: project storage model upgrade */
    project_file_schema_version?: string
    main_graph_path?: string
    project_resources_index_path?: string
    resource_overrides_path?: string
    builtin_resource_refs?: string[]
    project_resource_refs?: string[]
  }
  graph_workspace: Record<string, unknown>
}
export interface ProjectPostResponse {
  status: string
  project: ProjectDocumentResponse['project']
  graph_document: Record<string, unknown>
}
export interface RecentProject { project_name: string; project_path: string }
export interface ProjectNewRequest { project_name: string; project_directory?: string }
export interface ProjectOpenRequest { project_path: string }
export interface ProjectSaveAsRequest { project_path: string; graph_document?: Record<string, unknown> }
export interface RecentProjectRemoveRequest { project_path: string }

// ===== P6: Project Documents =====

export interface ProjectDocumentsResponse {
  main_graph_document_id: string
  documents: {
    document_id: string; document_role: string; document_type: string
    graph_schema_version: string; node_count: number; edge_count: number
    save_revision: number; saved_at: string | null
  }[]
}

// ===== P6: Resources =====

export interface ResourceItem {
  resource_id: string; resource_type: string; display_name: string
  resource_key: string; enabled: boolean
  origin?: string; source_graph_document_id?: string; source_graph_document_save_revision?: number
  node_taxonomy?: string
  resource_manager_visible?: boolean
  compatibility_only?: boolean
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  description?: string
  category_path?: string[]
  category_group_path?: string[]
  category_group_label?: string
  display_name_i18n?: Record<string, string>
  description_i18n?: Record<string, string>
  tags?: string[]
  search_tokens?: string[]
}
export interface ResourcesResponse {
  registry_revision: number; resource_types: string[]
  summary: { total_resource_count: number; builtin_resource_count: number; user_resource_count: number; enabled_resource_count: number }
  resources: ResourceItem[]
  facets?: Facets
}
export interface ResourceEnabledResponse { status: string; registry_revision: number; resource: ResourceItem }
export interface ResourceTagsResponse { status: string; registry_revision: number; resource: ResourceItem }
export interface ResourceImportResponse { status: string; registry_revision: number; resource: ResourceItem }
export interface ResourceExportRequest { resource_id: string; export_path: string }
export interface ResourceImportRequest { import_path: string; replace_existing?: boolean }

// ===== P6: Component Library =====

export interface ComponentLibraryItem {
  resource_id: string; display_name: string; resource_type: string
  resource_key: string; enabled: boolean; category: string
  node_taxonomy?: string
  component_library_visible?: boolean
  resource_manager_visible?: boolean
  user_creatable?: boolean
  compatibility_only?: boolean
  graph_semantic_kind?: string
  category_path?: string[]
  category_group_path?: string[]
  category_group_label?: string
  tags?: string[]
  search_tokens?: string[]
  display_name_i18n?: Record<string, string>
  description?: string
  description_i18n?: Record<string, string>
}
export interface FacetCategoryPath { path: string[]; label: string }
export interface Facets { category_paths: FacetCategoryPath[]; category_groups: FacetCategoryPath[]; user_tags: string[] }
export interface ComponentLibraryResponse {
  summary: { available_resource_count: number }
  items: ComponentLibraryItem[]
  facets?: Facets
}

// ===== P13-B: WebControl Converter =====

export interface WebControlConvertRequest {
  source_path: string
  blueprint_paths?: string[]
  blueprint_directory?: string
  output_project_path: string
  project_name?: string
  overwrite_output?: boolean
  auto_open_project?: boolean
  preserve_legacy_metadata?: boolean
  write_conversion_report?: boolean
}

export interface WebControlConvertResponse {
  status: string
  message?: string
  report_path?: string
  project?: {
    project_id: string
    project_name: string
    project_file_path: string
    project_status: string
    workspace_root: string
  }
  graph_document?: Record<string, unknown>
  report?: {
    source_kind?: string
    main_graph_node_count?: number
    main_graph_edge_count?: number
    imported_blueprint_count?: number
    generated_resource_count?: number
    warnings?: unknown[]
    errors?: unknown[]
  }
}

// ===== P16: Project Settings & .wcrun Package =====

export interface ProjectSettings {
  project_settings_schema_version: number
  project_identity: { name: string; description?: string; version?: string; tags?: string[] }
  runtime_defaults: { initial_variables: Record<string, unknown>; browser_config: Record<string, unknown>; execution_defaults: Record<string, unknown> }
  packaging: { default_output_name?: string }
  external_resources: Record<string, unknown>[]
  resource_policy: { embedded_resources: string[]; external_resource_bindings: Record<string, unknown>[] }
  compile_profile: { source_of_truth: string; inject_project_runtime_defaults_into_main_flow_start: boolean }
  /** 0.7-E: Python runtime profile (editable in project settings) */
  python_runtime_profile: PythonRuntimeProfile
}

export interface ProjectSettingsSnapshot {
  loaded?: boolean; source_of_truth?: string; state_source?: string
  project_file_path?: string | null; project_settings_path?: string | null; session_dir?: string | null
  is_dirty?: boolean; project_settings_schema_version?: number
  has_external_resources?: boolean; embedded_resource_count?: number; external_resource_count?: number
  package_default_output_name?: string
  main_graph_compatibility?: GraphCompatibilitySummary
}

export interface ProjectSettingsState {
  loaded: boolean; source: string; project_file_path: string | null
  session_dir: string | null; project_settings_path: string | null; is_dirty: boolean
  /** 0.6.2: main graph compatibility summary */
  main_graph_compatibility?: GraphCompatibilitySummary
}

export interface ProjectSettingsResponse { project_settings: ProjectSettings; state: ProjectSettingsState; python_runtime_summary?: PythonRuntimeSummary }

export interface RuntimeDefaults {
  initial_variables: Record<string, unknown>; browser_config: Record<string, unknown>; execution_defaults: Record<string, unknown>
}

export interface RuntimeDefaultsResponse { runtime_defaults: RuntimeDefaults; state: ProjectSettingsState }

export interface RuntimeDefaultsUpdateResponse {
  status: string; runtime_defaults: RuntimeDefaults
  graph_projection_refresh?: { node_id: string; node_config: Record<string, unknown> }
}

export interface PackagePreflightEntry {
  diagnostic_id: string; severity: string; stage: string; category: string; message: string
  object_ref?: string; setting_field?: string; node_id?: string; resource_id?: string
}

export interface PackagePreflightResponse {
  status: string
  summary: { error_count: number; warning_count: number; info_count: number; blocking: boolean }
  entries: PackagePreflightEntry[]
}

export interface PackageBuildRequest { output_path?: string; mode?: string; source_of_truth?: string }
export interface PackageBuildResponse {
  status: string; output_path?: string
  package_info?: { package_id: string; package_version: string; built_at: string }
  summary?: Record<string, unknown>; diagnostics?: { total_count: number; entries: unknown[] }
}

export interface PackageInspectResponse {
  status: string
  package_summary: Record<string, unknown>; project_settings_summary: Record<string, unknown>
  resource_summary: Record<string, unknown>; dependency_summary: Record<string, unknown>
  graph_detail_summary: Record<string, unknown>; external_binding_summary: Record<string, unknown>
  runtime_requirement_summary: Record<string, unknown>; runtime_readiness_summary: Record<string, unknown>
  package: Record<string, unknown>
}

export interface PackageLoadResponse extends PackageInspectResponse {
  session_restore_summary: Record<string, unknown>
  project: Record<string, unknown>; project_settings: ProjectSettings; graph_workspace: Record<string, unknown>
}

// ===== P12: Node Draft =====

export interface NodeDraftResponse {
  resource: {
    resource_id: string
    resource_key: string
    display_name: string
    display_name_i18n?: Record<string, string>
    resource_type: string
    node_taxonomy?: string
    graph_semantic_kind?: string
  }
  node: import('./graph').GraphNode
  parameter_schema?: Record<string, ParameterFieldSchema>
}

export interface ParameterFieldSchema {
  editor_kind?: string        // "path" | "text" | "select" | ...
  path_kind?: string           // "open_file" | "save_file" | "open_directory"
  file_types?: string[]        // e.g. ["*.xlsx", "*.csv"]
  label?: string
  description?: string
}

// ===== Preferences =====

export interface PreferencesUpdateRequest {
  section: string
  values: Record<string, unknown>
  confirm_high_risk?: boolean
}

export interface PreferencesResponse {
  preferences: Record<string, unknown>
}

// ===== 0.7-E: Python Runtime =====

export interface PythonRuntimeProfile {
  // Editable fields (1-14):
  runtime_enabled: boolean
  python_version_spec: string
  interpreter_strategy: 'bundled' | 'system' | 'custom_path'
  custom_python_path: string | null
  cache_location_mode: 'software_cache' | 'project_cache'
  project_cache_mode: 'wheelhouse_rebuild' | 'full_venv'
  requirements_source_mode: 'inline' | 'requirements_txt' | 'lock_file'
  requirements_inline: string[]
  requirements_file_path: string | null
  lock_file_path: string | null
  index_strategy: 'default' | 'custom'
  custom_index_url: string | null
  auto_prepare_on_run: boolean
  package_embed_mode: 'none' | 'wheelhouse_rebuild' | 'full_venv'
  // Read-only status fields (15-17):
  materialized_runtime_hash: string | null
  last_health_status: 'unknown' | 'ready' | 'missing' | 'broken' | 'stale'
  last_health_message: string | null
}

export interface PythonRuntimeStatus {
  health_status: string | null
  health_message: string | null
  runtime_root: string | null
  python_executable: string | null
  manifest_hash: string | null
  cache_location_mode: string | null
  project_cache_mode: string | null
}

export interface PythonRuntimeSummary {
  enabled: boolean
  health_status: string | null
  health_message: string | null
  runtime_root: string | null
  python_executable: string | null
  manifest_hash: string | null
  cache_location_mode: string | null
  project_cache_mode: string | null
  package_embed_mode: string | null
}

export interface PythonRuntimeGetResponse {
  python_runtime_profile: PythonRuntimeProfile
  runtime_status: PythonRuntimeStatus
  diagnostics: unknown[]
}

export interface PythonRuntimeActionResponse {
  python_runtime_profile: PythonRuntimeProfile
  runtime_status: PythonRuntimeStatus
  diagnostics: unknown[]
}

export interface PythonRuntimeExportBundle {
  output_path: string
  bundle_mode: string
  bundle_root: string | null
  entry_count: number
  written_bytes: number
}

export interface PythonRuntimeExportResponse {
  status: string
  python_runtime_profile: PythonRuntimeProfile
  runtime_status: PythonRuntimeStatus
  export_bundle: PythonRuntimeExportBundle
  diagnostics: unknown[]
}

// ===== P6: Recent Projects =====

export interface RecentProjectsResponse { recent_projects: RecentProject[] }

// ===== P6: Runtime Sessions =====

export interface RuntimeSessionsResponse { sessions: RuntimeSessionSummary[] }
export interface RuntimeSessionSummary {
  session_id: string; status: string; graph_model_id: string | null
}
export interface RuntimeExecutionSummary {
  status: string
  completed_node_count: number
  failed_node_count: number
  event_count: number
  diagnostic_event_count: number
  node_status_counts?: Record<string, number>
  latest_event_kind?: string | null
}
export interface RuntimeProgress {
  session_id: string
  status: string
  total_node_count: number
  completed_node_count: number
  failed_node_count: number
  running_node_count: number
  pending_node_count: number
  percent: number
  event_count: number
}
export interface RuntimeSessionDetailResponse {
  status: string; request: Record<string, unknown>
  runtime_session: { session_id: string | null; status: string; execution_supported: boolean }
  runtime_plan: RuntimePlan | null
  node_states: Record<string, unknown>[]
  event_log: Record<string, unknown>[]
  execution_summary?: RuntimeExecutionSummary
  result: Record<string, unknown> | null
  diagnostics?: { total_count: number; highest_severity: string | null; entries: unknown[] }
  diagnostic_events?: Record<string, unknown>[]
}
export interface RuntimeStreamSnapshot extends RuntimeSessionDetailResponse {
  session_id: string
}
export type RuntimeStreamTerminalEventName = 'runtime.completed' | 'runtime.failed'
export type RuntimeStreamEventName =
  | 'runtime.snapshot'
  | 'runtime.summary'
  | RuntimeStreamTerminalEventName

// ===== P6: Debug Sessions =====

export interface DebugSessionsResponse { sessions: DebugSessionSummary[] }
export interface DebugSessionSummary {
  session_id: string; status: string; graph_model_id: string | null
}
export interface DebugSessionDetailResponse {
  status: string; request: Record<string, unknown>
  debug_session: { session_id: string; status: string; resume_supported: boolean; breakpoint_slots: unknown[] }
  stage_timeline: StageTimelineEntry[]
  object_index: ObjectIndex | null
  diagnostic_links: DiagnosticLink[]
}

// ===== P6: Execution History =====

export interface ExecutionHistoryResponse {
  summary: { runtime_run_count: number; debug_session_count: number }
  runtime_runs: Record<string, unknown>[]
  debug_sessions: Record<string, unknown>[]
}
