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
  DebugSessionsResponse, DebugSessionDetailResponse,
  ExecutionHistoryResponse,
  PreferencesResponse,
  PreferencesUpdateRequest,
  NodeDraftResponse,
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

export function fetchGraphDocument(): Promise<GraphDocumentResponse> {
  return request<GraphDocumentResponse>('/workbench/graph')
}

export function putGraphDocument(graphModel: Record<string, unknown>, expectedRevision?: number): Promise<GraphSaveResponse> {
  const body: Record<string, unknown> = { ...graphModel }
  if (expectedRevision !== undefined) {
    body.expected_graph_document_save_revision = expectedRevision
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
export function postPreferencesReset(): Promise<PreferencesResponse> { return request<PreferencesResponse>('/workbench/preferences/reset', { method: 'POST', body: '{}' }) }

export { ApiError }
