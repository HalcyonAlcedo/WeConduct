/** WeConduct — API Service Layer
 *  Calls the Python backend at http://127.0.0.1:8000 (via Vite proxy)
 *  All types match the Core Python contracts exactly.
 */

import type {
  HealthResponse,
  SnapshotResponse,
  CompileResponse,
  CompileRequestBody,
  GraphDocumentResponse,
  GraphSaveResponse,
  GraphValidateResponse,
  GraphCompileResponse,
  RuntimePrepareRequest,
  RuntimePrepareResponse,
  DebugPrepareRequest,
  DebugPrepareResponse,
  HostInfoResponse,
  ProjectDocumentResponse, ProjectPostResponse, ProjectNewRequest, ProjectOpenRequest, ProjectSaveAsRequest,
  RecentProjectRemoveRequest, RecentProjectsResponse,
  ProjectDocumentsResponse,
  ResourceEnabledResponse, ResourceTagsResponse, ResourceImportResponse, ResourcesResponse, ResourceExportRequest, ResourceImportRequest,
  ComponentLibraryResponse,
  RuntimeSessionsResponse, RuntimeSessionDetailResponse,
  RuntimeProgress,
  DebugSessionsResponse, DebugSessionDetailResponse,
  ExecutionHistoryResponse,
  PreferencesResponse,
  PreferencesUpdateRequest,
  UpdateCheckRequest,
  UpdateStatusResponse,
  NodeDraftResponse,
  WebControlConvertRequest,
  WebControlConvertResponse,
  ProjectSettingsResponse,
  RuntimeDefaults,
  RuntimeDefaultsResponse,
  RuntimeDefaultsUpdateResponse,
  PackagePreflightResponse,
  PackageBuildRequest,
  PackageBuildResponse,
  PackageInspectResponse,
  PackageLoadResponse,
  PythonRuntimeGetResponse,
  PythonRuntimeActionResponse,
  PythonRuntimeExportResponse,
} from '@/types/domains/api'

const API_BASE = '/api'

class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    const message =
      typeof body === 'object' && body !== null
        ? 'message' in body
          ? String((body as Record<string, unknown>).message)
          : 'error' in body
            ? String((body as Record<string, unknown>).error)
            : `HTTP ${status}`
        : `HTTP ${status}`
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  const body = await res.json()

  if (!res.ok) {
    throw new ApiError(res.status, body)
  }

  return body as T
}

// ===== Health =====

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

// ===== Workbench Snapshot =====

export function fetchSnapshot(): Promise<SnapshotResponse> {
  return request<SnapshotResponse>('/workbench/snapshot')
}

// ===== Compile =====

export function postCompile(body: CompileRequestBody): Promise<CompileResponse> {
  return request<CompileResponse>('/workbench/compile', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ===== P3: Graph Workspace =====

export function fetchGraphDocument(documentId?: string): Promise<GraphDocumentResponse> {
  const qs = documentId ? `?document_id=${encodeURIComponent(documentId)}` : ''
  return request<GraphDocumentResponse>('/workbench/graph' + qs)
}

export function putGraphDocument(graphModel: Record<string, unknown>, expectedRevision?: number, documentId?: string): Promise<GraphSaveResponse> {
  const body: Record<string, unknown> = { ...graphModel }
  if (expectedRevision !== undefined) {
    body.expected_graph_document_save_revision = expectedRevision
  }
  if (documentId) {
    body.document_id = documentId
  }
  return request<GraphSaveResponse>('/workbench/graph', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

// ===== P3: Graph Validate =====

export function postGraphValidate(graphModel?: Record<string, unknown>): Promise<GraphValidateResponse> {
  return request<GraphValidateResponse>('/workbench/graph/validate', {
    method: 'POST',
    body: graphModel ? JSON.stringify(graphModel) : '{}',
  })
}

// ===== P3: Graph Compile =====

export function postGraphCompile(graphModel?: Record<string, unknown>): Promise<GraphCompileResponse> {
  return request<GraphCompileResponse>('/workbench/graph/compile', {
    method: 'POST',
    body: graphModel ? JSON.stringify(graphModel) : '{}',
  })
}

export function postGraphNormalize(graphModel: Record<string, unknown>): Promise<{ status: string; changed: boolean; graph_model: Record<string, unknown>; view: Record<string, unknown> }> {
  return request('/workbench/graph/normalize', {
    method: 'POST',
    body: JSON.stringify(graphModel),
  })
}

// ===== P3: Runtime Prepare =====

export function postRuntimePrepare(body?: RuntimePrepareRequest): Promise<RuntimePrepareResponse> {
  return request<RuntimePrepareResponse>('/workbench/runtime/prepare', {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

// ===== P3: Debug Prepare =====

export function postDebugPrepare(body?: DebugPrepareRequest): Promise<DebugPrepareResponse> {
  return request<DebugPrepareResponse>('/workbench/debug/prepare', {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

// ===== P3: Host Info =====

export function fetchHostInfo(): Promise<HostInfoResponse> {
  return request<HostInfoResponse>('/host/info')
}

// ===== P6: Project =====
export function fetchProject(): Promise<ProjectDocumentResponse> { return request('/workbench/project') }
export function postCreateEmptyCustomComponent(resourceName: string): Promise<{ status: string; registry_revision: number; resource: { resource_id: string; resource_key: string; display_name: string } }> {
  return request('/workbench/resources/custom-node-graphs/create-empty', { method: 'POST', body: JSON.stringify({ resource_name: resourceName }) })
}
export function fetchProjectDocuments(): Promise<ProjectDocumentsResponse> { return request('/workbench/project/documents') }
export function postProjectNew(body: ProjectNewRequest): Promise<ProjectPostResponse> { return request('/workbench/project/new', { method: 'POST', body: JSON.stringify(body) }) }
export function postProjectOpen(body: ProjectOpenRequest): Promise<ProjectPostResponse> { return request('/workbench/project/open', { method: 'POST', body: JSON.stringify(body) }) }
export function postProjectSave(graphDocument?: Record<string, unknown>): Promise<ProjectPostResponse> {
  const body: Record<string, unknown> = {}
  if (graphDocument) body.graph_document = graphDocument
  return request('/workbench/project/save', { method: 'POST', body: JSON.stringify(body) })
}
export function postProjectSaveAs(body: ProjectSaveAsRequest): Promise<ProjectPostResponse> { return request('/workbench/project/save-as', { method: 'POST', body: JSON.stringify(body) }) }
export function fetchRecentProjects(): Promise<RecentProjectsResponse> { return request('/workbench/recent-projects') }
export function postRecentProjectRemove(body: RecentProjectRemoveRequest): Promise<void> { return request('/workbench/recent-projects/remove', { method: 'POST', body: JSON.stringify(body) }) }

// ===== P6: Resources =====
export function fetchResources(params?: { query?: string; tags?: string; enabled?: boolean; origin?: string; resource_type?: string }): Promise<ResourcesResponse> {
  const qs = params ? '?' + new URLSearchParams(Object.entries(params).filter(([,v]) => v != null).map(([k,v]) => [k, String(v)])).toString() : ''
  return request('/workbench/resources' + qs)
}
export function postResourceEnabled(resourceId: string, enabled: boolean): Promise<ResourceEnabledResponse> { return request(`/workbench/resources/${resourceId}/enabled`, { method: 'POST', body: JSON.stringify({ enabled }) }) }
export function postResourceExport(body: ResourceExportRequest): Promise<Record<string, unknown>> { return request('/workbench/resources/export', { method: 'POST', body: JSON.stringify(body) }) }
export function postResourceImport(body: ResourceImportRequest): Promise<ResourceImportResponse> { return request('/workbench/resources/import', { method: 'POST', body: JSON.stringify(body) }) }
export function postResourceTags(resourceId: string, tags: string[]): Promise<ResourceTagsResponse> { return request(`/workbench/resources/${resourceId}/tags`, { method: 'POST', body: JSON.stringify({ tags }) }) }
export function postResourceMetadata(resourceId: string, metadata: { display_name?: string; description?: string; display_name_i18n?: Record<string, string>; description_i18n?: Record<string, string> }): Promise<ResourceTagsResponse> { return request('/workbench/resources/metadata', { method: 'POST', body: JSON.stringify({ resource_id: resourceId, ...metadata }) }) }
export function postResourceDelete(resourceId: string): Promise<{ status: string }> { return request('/workbench/resources/delete', { method: 'POST', body: JSON.stringify({ resource_id: resourceId }) }) }

// ===== P6: Component Library =====
export function fetchComponentLibrary(params?: { query?: string; tags?: string; enabled?: boolean; origin?: string; resource_type?: string }): Promise<ComponentLibraryResponse> {
  const qs = params ? '?' + new URLSearchParams(Object.entries(params).filter(([,v]) => v != null).map(([k,v]) => [k, String(v)])).toString() : ''
  return request('/workbench/component-library' + qs)
}

// ===== P6: Runtime =====
export function fetchRuntimeSessions(): Promise<RuntimeSessionsResponse> { return request('/workbench/runtime/sessions') }
export function fetchRuntimeSession(id: string): Promise<RuntimeSessionDetailResponse> { return request(`/workbench/runtime/${id}`) }
export function postRuntimeStart(body?: Record<string, unknown>): Promise<RuntimeSessionDetailResponse> { return request('/workbench/runtime/start', { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }
export function postRuntimeRun(sessionId: string): Promise<RuntimeSessionDetailResponse> { return request(`/workbench/runtime/${sessionId}/run`, { method: 'POST', body: '{}' }) }
export function getRuntimeStreamUrl(sessionId: string): string { return `${API_BASE}/workbench/runtime/${sessionId}/stream` }
export function buildRuntimeProgressFromSession(detail: RuntimeSessionDetailResponse): RuntimeProgress {
  const nodeStates = Array.isArray(detail.node_states) ? detail.node_states : []
  const totalNodeCount = nodeStates.length
  const completedNodeCount = nodeStates.filter((node: any) => node?.node_status === 'completed').length
  const failedNodeCount = nodeStates.filter((node: any) => node?.node_status === 'failed').length
  const runningNodeCount = nodeStates.filter((node: any) => node?.node_status === 'running').length
  const pendingNodeCount = nodeStates.filter((node: any) => node?.node_status === 'pending').length
  const percent = totalNodeCount > 0 ? Number((((completedNodeCount + failedNodeCount) / totalNodeCount) * 100).toFixed(1)) : 0
  return {
    session_id: detail.runtime_session.session_id ?? '',
    status: detail.runtime_session.status ?? detail.status,
    total_node_count: totalNodeCount,
    completed_node_count: completedNodeCount,
    failed_node_count: failedNodeCount,
    running_node_count: runningNodeCount,
    pending_node_count: pendingNodeCount,
    percent,
    event_count: Array.isArray(detail.event_log) ? detail.event_log.length : 0,
  }
}

// ===== P6: Debug =====
export function fetchDebugSessions(): Promise<DebugSessionsResponse> { return request('/workbench/debug/sessions') }
export function fetchDebugSession(id: string): Promise<DebugSessionDetailResponse> { return request(`/workbench/debug/${id}`) }
export function postDebugStart(body?: Record<string, unknown>): Promise<DebugSessionDetailResponse> { return request('/workbench/debug/start', { method: 'POST', body: body ? JSON.stringify(body) : undefined }) }

// ===== P6: Execution History =====
export function fetchExecutionHistory(): Promise<ExecutionHistoryResponse> { return request('/workbench/execution-history') }

// ===== P7: Source Projection =====
export function postSourceProjection(body: { target_source_kind: string; graph_document: Record<string, unknown> }): Promise<{ status: string; source_kind?: string; source_text?: string; entry_document?: string; message?: string; diagnostics?: unknown[] }> {
  return request('/workbench/graph/source-projection', { method: 'POST', body: JSON.stringify(body) })
}

// ===== P8.1: Host File Dialog =====
export function postFileDialog(body: { mode: string; title?: string; file_types?: string[]; default_path?: string }): Promise<{ status: string; mode: string; paths: string[] }> {
  return request('/host/file-dialog', { method: 'POST', body: JSON.stringify(body) })
}

// ===== P8.1: Host Open Path =====
export function postOpenPath(body: { path: string }): Promise<{ status: string; path: string; target_kind: string }> {
  return request('/host/open-path', { method: 'POST', body: JSON.stringify(body) })
}

// ===== P8.1: Host Read File =====
export function postReadFile(body: { path: string; encoding?: string; max_bytes?: number }): Promise<{ status: string; path: string; encoding: string; content: string; bytes_read: number }> {
  return request('/host/read-file', { method: 'POST', body: JSON.stringify(body) })
}

// ===== P12: Node Draft =====
export function fetchNodeDraft(params: { resource_key: string; node_id?: string; x?: number; y?: number }): Promise<NodeDraftResponse> {
  const qs = '?' + new URLSearchParams(Object.entries(params).filter(([,v]) => v != null).map(([k,v]) => [k, String(v)])).toString()
  return request<NodeDraftResponse>('/workbench/graph/node-draft' + qs)
}

// ===== Preferences =====
export function fetchPreferences(): Promise<PreferencesResponse> { return request<PreferencesResponse>('/workbench/preferences') }
export function postPreferences(body: PreferencesUpdateRequest): Promise<PreferencesResponse> { return request<PreferencesResponse>('/workbench/preferences', { method: 'POST', body: JSON.stringify(body) }) }
export function postPreferencesPreview(body: { section: string; values: Record<string, unknown> }): Promise<{ section: string; current_values: Record<string, unknown>; proposed_values: Record<string, unknown>; confirmation_required: boolean; high_risk_changes: { field: string; from: unknown; to: unknown; reason: string }[] }> { return request('/workbench/preferences/preview', { method: 'POST', body: JSON.stringify(body) }) }
export function postPreferencesReset(): Promise<PreferencesResponse> { return request<PreferencesResponse>('/workbench/preferences/reset', { method: 'POST', body: '{}' }) }

// ===== 0.7.2: Updates =====
export function fetchUpdateStatus(): Promise<UpdateStatusResponse> {
  return request<UpdateStatusResponse>('/workbench/update/status')
}

export function postUpdateCheck(body: UpdateCheckRequest): Promise<UpdateStatusResponse> {
  return request<UpdateStatusResponse>('/workbench/update/check', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ===== P13-B: WebControl Converter =====
export function postConvertWebcontrol(body: WebControlConvertRequest): Promise<WebControlConvertResponse> {
  return request<WebControlConvertResponse>('/workbench/project/convert-webcontrol', { method: 'POST', body: JSON.stringify(body) })
}

// ===== 0.6.2: Graph Upgrade =====
export function postGraphUpgradeApply(decision: 'upgrade_and_load' | 'force_load'): Promise<{ status: string; project: Record<string, unknown>; graph_document: Record<string, unknown> }> {
  return request('/workbench/project/graph-upgrade/apply', { method: 'POST', body: JSON.stringify({ decision }) })
}
export function postGraphUpgradeRecheck(): Promise<import('@/types/domains/api').GraphUpgradeRecheckResponse> {
  return request('/workbench/project/graph-upgrade/recheck', { method: 'POST', body: '{}' })
}

// ===== P16: Project Settings & .wcrun Package =====
export function fetchProjectSettings(): Promise<ProjectSettingsResponse> { return request('/workbench/project/settings') }
export function postProjectSettings(body: { project_settings: Record<string, unknown> }): Promise<ProjectSettingsResponse> { return request('/workbench/project/settings', { method: 'POST', body: JSON.stringify(body) }) }
export function fetchRuntimeDefaults(): Promise<RuntimeDefaultsResponse> { return request('/workbench/project/runtime-defaults') }
export function postRuntimeDefaults(body: { runtime_defaults: RuntimeDefaults }): Promise<RuntimeDefaultsUpdateResponse> { return request('/workbench/project/runtime-defaults', { method: 'POST', body: JSON.stringify(body) }) }
export function postPackagePreflight(body?: { mode?: string; source_of_truth?: string }): Promise<PackagePreflightResponse> {
  return request('/workbench/project/package/preflight', {
    method: 'POST',
    body: JSON.stringify(body || {}),
  })
}
export function postPackageBuild(body?: PackageBuildRequest): Promise<PackageBuildResponse> { return request('/workbench/project/package/build', { method: 'POST', body: JSON.stringify(body || {}) }) }
export function fetchPackageInspect(packagePath: string): Promise<PackageInspectResponse> { return request(`/workbench/project/package/inspect?package_path=${encodeURIComponent(packagePath)}`) }
export function postPackageLoad(packagePath: string): Promise<PackageLoadResponse> { return request('/workbench/project/package/load', { method: 'POST', body: JSON.stringify({ package_path: packagePath }) }) }
export function postPackageUnload(): Promise<{ status: string }> { return request('/workbench/project/package/unload', { method: 'POST', body: '{}' }) }
export function postPackageBindExternal(body: { resource_id: string; value: string }): Promise<{ status: string }> { return request('/workbench/project/package/external-resources/bind', { method: 'POST', body: JSON.stringify(body) }) }

// ===== 0.7-E: Python Runtime =====

export function fetchPythonRuntime(): Promise<PythonRuntimeGetResponse> {
  return request<PythonRuntimeGetResponse>('/workbench/project/python-runtime')
}

export function postPythonRuntimeHealthCheck(): Promise<PythonRuntimeActionResponse> {
  return request<PythonRuntimeActionResponse>('/workbench/project/python-runtime/health-check', { method: 'POST', body: '{}' })
}

export function postPythonRuntimePrepare(): Promise<PythonRuntimeActionResponse> {
  return request<PythonRuntimeActionResponse>('/workbench/project/python-runtime/prepare', { method: 'POST', body: '{}' })
}

export function postPythonRuntimeRebuild(): Promise<PythonRuntimeActionResponse> {
  return request<PythonRuntimeActionResponse>('/workbench/project/python-runtime/rebuild', { method: 'POST', body: '{}' })
}

export function postPythonRuntimeClear(): Promise<PythonRuntimeActionResponse> {
  return request<PythonRuntimeActionResponse>('/workbench/project/python-runtime/clear', { method: 'POST', body: '{}' })
}

export function postPythonRuntimeExportBundle(body: { output_path: string; package_embed_mode?: string }): Promise<PythonRuntimeExportResponse> {
  return request<PythonRuntimeExportResponse>('/workbench/project/python-runtime/export-bundle', { method: 'POST', body: JSON.stringify(body) })
}

export { ApiError }
