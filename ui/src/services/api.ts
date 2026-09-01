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
  SubgraphAssetExportRequest, SubgraphAssetExportResponse,
  SubgraphAssetImportCommitRequest, SubgraphAssetImportCommitResponse, SubgraphAssetImportPreflightResponse,
  ComponentLibraryResponse,
  RuntimeSessionsResponse, RuntimeSessionDetailResponse,
  RuntimeProgress,
  DebugSessionsResponse, DebugSessionDetailResponse,
  DebugHistorySummaryResponse,
  DebugHistorySessionResponse,
  DebugProjectionResponse,
  DebugEventsResponse,
  DebugControlResponse,
  DebugNetworkSummaryResponse,
  DebugNetworkListResponse,
  DebugNetworkTraceResponse,
  DebugNetworkTraceBodyResponse,
  OAuthAuthorizationBeginRequest,
  OAuthDeviceBeginRequest,
  OAuthFlowSnapshot,
  OAuthFlowSubmitRequest,
  DebugVariablesApplyRequest,
  DebugVariablesApplyResponse,
  ExecutionHistoryResponse,
  PreferencesResponse,
  PreferencesUpdateRequest,
  ConfigValuesResponse,
  ConfigPatchRequest,
  UpdateCheckRequest,
  UpdateStatusResponse,
  NodeDraftResponse,
  WebControlConvertRequest,
  WebControlConvertResponse,
  PackagePreflightResponse,
  PackageBuildRequest,
  PackageBuildResponse,
  PackageInspectResponse,
  PackageLoadResponse,
  PythonRuntimeGetResponse,
  PythonRuntimeActionResponse,
  PythonRuntimeExportResponse,
  StartupDiagnosticsResponse,
  StartupRecoverResponse,
} from '@/types/domains/api'

const API_BASE = '/api'

function readUiTokenFromLocation(): string | null {
  if (typeof window === 'undefined') return null
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  if (!hash) return null
  const token = new URLSearchParams(hash).get('weconduct_token')
  if (!token) return null
  window.history.replaceState(
    window.history.state,
    document.title,
    `${window.location.pathname}${window.location.search}`,
  )
  return token
}

let uiToken: string | null = null

type DesktopTokenBridge = {
  get_ui_token: () => Promise<unknown> | unknown
}

function getDesktopTokenBridge(): DesktopTokenBridge | null {
  if (typeof window === 'undefined') return null
  const bridge = (window as Window & { pywebview?: { api?: unknown } }).pywebview?.api
  if (!bridge || typeof (bridge as DesktopTokenBridge).get_ui_token !== 'function') return null
  return bridge as DesktopTokenBridge
}

function hasUiTokenFragment(): boolean {
  if (typeof window === 'undefined') return false
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  return Boolean(hash && new URLSearchParams(hash).get('weconduct_token'))
}

async function waitForDesktopTokenBridge(): Promise<DesktopTokenBridge | null> {
  const currentBridge = getDesktopTokenBridge()
  if (currentBridge) return currentBridge
  if (hasUiTokenFragment()) return null
  return new Promise<DesktopTokenBridge>((resolve, reject) => {
    const onReady = () => {
      const bridge = getDesktopTokenBridge()
      if (!bridge) {
        finish(() => reject(new Error('desktop UI token bridge is unavailable')))
        return
      }
      finish(() => resolve(bridge))
    }
    const timeout = window.setTimeout(() => {
      finish(() => reject(new Error('desktop UI token bridge timed out')))
    }, 5000)
    const finish = (action: () => void) => {
      window.clearTimeout(timeout)
      window.removeEventListener('pywebviewready', onReady)
      action()
    }
    window.addEventListener('pywebviewready', onReady, { once: true })
    const bridgeAfterListener = getDesktopTokenBridge()
    if (bridgeAfterListener) finish(() => resolve(bridgeAfterListener))
  })
}

async function readUiTokenFromDesktopBridge(bridge: DesktopTokenBridge): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      reject(new Error('desktop UI token bridge timed out'))
    }, 5000)
    Promise.resolve(bridge.get_ui_token()).then((token) => {
      window.clearTimeout(timeout)
      if (typeof token !== 'string' || !token) {
        reject(new Error('desktop UI token bridge returned an empty token'))
        return
      }
      resolve(token)
    }, (error) => {
      window.clearTimeout(timeout)
      reject(new Error(`desktop UI token bridge failed: ${String(error)}`))
    })
  })
}

export async function initializeUiToken(): Promise<void> {
  const bridge = await waitForDesktopTokenBridge()
  uiToken = bridge
    ? await readUiTokenFromDesktopBridge(bridge)
    : readUiTokenFromLocation()
}

function buildRequestHeaders(options?: RequestInit): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options?.headers instanceof Headers) {
    options.headers.forEach((value, key) => { headers[key] = value })
  } else if (Array.isArray(options?.headers)) {
    for (const [key, value] of options.headers) headers[key] = value
  } else if (options?.headers) {
    Object.assign(headers, options.headers)
  }
  if (uiToken) headers['X-WeConduct-Token'] = uiToken
  return headers
}

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
    ...options,
    headers: buildRequestHeaders(options),
  })

  const body = await res.json()

  if (!res.ok) {
    const error = new ApiError(res.status, body)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('weconduct:api-error', {
        detail: { error, path, method: options?.method || 'GET' },
      }))
    }
    throw error
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

export function putGraphDocument(
  graphModel: Record<string, unknown>,
  expectedRevision?: number,
  documentId?: string,
  requireExpectedRevision = false,
): Promise<GraphSaveResponse> {
  const body: Record<string, unknown> = { ...graphModel }
  if (expectedRevision !== undefined) {
    body.expected_graph_document_save_revision = expectedRevision
  }
  if (documentId) {
    body.document_id = documentId
  }
  if (requireExpectedRevision) {
    body.require_expected_graph_document_save_revision = true
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
export function postSubgraphAssetExport(body: SubgraphAssetExportRequest): Promise<SubgraphAssetExportResponse> { return request('/workbench/subgraph-assets/export', { method: 'POST', body: JSON.stringify(body) }) }
export function postSubgraphAssetImportPreflight(body: { import_path: string }): Promise<SubgraphAssetImportPreflightResponse> { return request('/workbench/subgraph-assets/import/preflight', { method: 'POST', body: JSON.stringify(body) }) }
export function postSubgraphAssetImportCommit(body: SubgraphAssetImportCommitRequest): Promise<SubgraphAssetImportCommitResponse> { return request('/workbench/subgraph-assets/import/commit', { method: 'POST', body: JSON.stringify(body) }) }

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
export function postRuntimeAbort(sessionId: string, reason = 'user_abort'): Promise<RuntimeSessionDetailResponse> { return request(`/workbench/runtime/${sessionId}/abort`, { method: 'POST', body: JSON.stringify({ reason }) }) }
export interface RuntimePendingInputField { field_id: string; label: string; value_type: string; sensitive: boolean; required: boolean }
export interface RuntimePendingInputSnapshot { execution_id: string | null; request_id: string | null; status: string; fields: RuntimePendingInputField[]; timeout_seconds: number | null }
export function fetchRuntimePendingInput(sessionId: string): Promise<RuntimePendingInputSnapshot> { return request(`/workbench/runtime/${sessionId}/pending-input`) }
export function postRuntimePendingInput(sessionId: string, requestId: string, values: Record<string, unknown>): Promise<RuntimePendingInputSnapshot> { return request(`/workbench/runtime/${sessionId}/pending-input`, { method: 'POST', body: JSON.stringify({ request_id: requestId, values }) }) }
export function postRuntimeParameterUnlock(sessionId: string, password: string): Promise<{ status: string; parameter_ids: string[] }> { return request(`/workbench/runtime/${sessionId}/unlock`, { method: 'POST', body: JSON.stringify({ password }) }) }
export function getRuntimeStreamUrl(sessionId: string): string { return `${API_BASE}/workbench/runtime/${sessionId}/stream` }
export function getRuntimeStreamPath(sessionId: string): string { return `/workbench/runtime/${sessionId}/stream` }

export type SseEvent = { event: string; id: string | null; data: string }

export async function consumeSse(
  path: string,
  options: {
    lastEventId?: number | string | null
    signal?: AbortSignal
    onEvent: (event: SseEvent) => void | Promise<void>
  },
): Promise<void> {
  const headers = buildRequestHeaders({ headers: { Accept: 'text/event-stream' } })
  if (options.lastEventId !== undefined && options.lastEventId !== null) {
    headers['Last-Event-ID'] = String(options.lastEventId)
  }
  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    signal: options.signal,
  })
  if (!response.ok) {
    let body: unknown = null
    try { body = await response.json() } catch { /* empty error body */ }
    throw new ApiError(response.status, body)
  }
  if (!response.body) throw new Error('SSE response body is unavailable')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'
  let eventId: string | null = null
  let dataLines: string[] = []

  const dispatch = async () => {
    if (!dataLines.length) {
      eventName = 'message'
      eventId = null
      return
    }
    const event: SseEvent = { event: eventName, id: eventId, data: dataLines.join('\n') }
    eventName = 'message'
    eventId = null
    dataLines = []
    await options.onEvent(event)
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line) {
        await dispatch()
      } else if (line.startsWith(':')) {
        continue
      } else if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('id:')) {
        eventId = line.slice(3).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).startsWith(' ') ? line.slice(6) : line.slice(5))
      }
    }
    if (done) {
      if (buffer) dataLines.push(buffer.startsWith('data:') ? buffer.slice(5).trimStart() : buffer)
      await dispatch()
      return
    }
  }
}

export function getUiToken(): string | null { return uiToken }
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
export function postDebugParameterUnlock(sessionId: string, password: string): Promise<DebugSessionDetailResponse> {
  return request(`/workbench/debug/${sessionId}/unlock`, { method: 'POST', body: JSON.stringify({ password }) })
}
export function postDebugSensitiveValuesReveal(sessionId: string, variableNames: string[], password: string): Promise<{ session_id: string; values: Record<string, unknown> }> {
  return request(`/workbench/debug/${sessionId}/sensitive-values/reveal`, { method: 'POST', body: JSON.stringify({ variable_names: variableNames, password }) })
}
export function fetchDebugHistorySessions(): Promise<DebugHistorySummaryResponse> { return request('/workbench/debug/history') }
export function fetchDebugHistorySession(id: string): Promise<DebugHistorySessionResponse> { return request(`/workbench/debug/history/${id}`) }

export function fetchDebugSessionNetworkSummary(sessionId: string): Promise<DebugNetworkSummaryResponse> {
  return request<DebugNetworkSummaryResponse>(`/workbench/debug/${sessionId}/network/summary`)
}

export function fetchDebugSessionNetwork(sessionId: string): Promise<DebugNetworkListResponse> {
  return request<DebugNetworkListResponse>(`/workbench/debug/${sessionId}/network`)
}

export function fetchDebugSessionNetworkTrace(sessionId: string, traceId: string): Promise<DebugNetworkTraceResponse> {
  return request<DebugNetworkTraceResponse>(`/workbench/debug/${sessionId}/network/${traceId}`)
}

export function fetchDebugSessionNetworkTraceBody(sessionId: string, traceId: string, part?: 'all' | 'request' | 'response' | 'messages'): Promise<DebugNetworkTraceBodyResponse> {
  const suffix = part && part !== 'all' ? `?part=${encodeURIComponent(part)}` : ''
  return request<DebugNetworkTraceBodyResponse>(`/workbench/debug/${sessionId}/network/${traceId}/body${suffix}`)
}

export function fetchDebugHistorySessionNetworkSummary(sessionId: string): Promise<DebugNetworkSummaryResponse> {
  return request<DebugNetworkSummaryResponse>(`/workbench/debug/history/${sessionId}/network/summary`)
}

export function fetchDebugHistorySessionNetwork(sessionId: string): Promise<DebugNetworkListResponse> {
  return request<DebugNetworkListResponse>(`/workbench/debug/history/${sessionId}/network`)
}

export function fetchDebugHistorySessionNetworkTrace(sessionId: string, traceId: string): Promise<DebugNetworkTraceResponse> {
  return request<DebugNetworkTraceResponse>(`/workbench/debug/history/${sessionId}/network/${traceId}`)
}

export function fetchDebugHistorySessionNetworkTraceBody(sessionId: string, traceId: string, part?: 'all' | 'request' | 'response' | 'messages'): Promise<DebugNetworkTraceBodyResponse> {
  const suffix = part && part !== 'all' ? `?part=${encodeURIComponent(part)}` : ''
  return request<DebugNetworkTraceBodyResponse>(`/workbench/debug/history/${sessionId}/network/${traceId}/body${suffix}`)
}

// ===== 0.9.2: Interactive OAuth =====
export function postOAuthAuthorization(body: OAuthAuthorizationBeginRequest): Promise<OAuthFlowSnapshot> {
  return request<OAuthFlowSnapshot>('/workbench/oauth/authorization', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function postOAuthDevice(body: OAuthDeviceBeginRequest): Promise<OAuthFlowSnapshot> {
  return request<OAuthFlowSnapshot>('/workbench/oauth/device', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchOAuthFlow(flowId: string): Promise<OAuthFlowSnapshot> {
  return request<OAuthFlowSnapshot>(`/workbench/oauth/${encodeURIComponent(flowId)}`)
}

export function postOAuthFlowSubmit(flowId: string, body: OAuthFlowSubmitRequest): Promise<OAuthFlowSnapshot> {
  return request<OAuthFlowSnapshot>(`/workbench/oauth/${encodeURIComponent(flowId)}/submit`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function postOAuthFlowCancel(flowId: string): Promise<OAuthFlowSnapshot> {
  return request<OAuthFlowSnapshot>(`/workbench/oauth/${encodeURIComponent(flowId)}/cancel`, {
    method: 'POST',
    body: '{}',
  })
}

// ===== 0.8.0: Debugger Projection =====

export function fetchDebugProjection(sessionId: string, mode: 'live' | 'history', eventIndex?: number, keyframeId?: string): Promise<DebugProjectionResponse> {
  const params = new URLSearchParams()
  if (eventIndex != null) params.set('event_index', String(eventIndex))
  if (keyframeId) params.set('keyframe_id', keyframeId)
  const qs = params.size ? `?${params.toString()}` : ''
  return request<DebugProjectionResponse>(`/workbench/debug/projection/${mode}/${sessionId}${qs}`)
}

// ===== 0.8.0: Debugger Control =====

export function postDebugContinue(sessionId: string): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/continue`, { method: 'POST', body: '{}' })
}
export function postDebugStepOver(sessionId: string): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/step-over`, { method: 'POST', body: '{}' })
}
export function postDebugStepInto(sessionId: string): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/step-into`, { method: 'POST', body: '{}' })
}
export function postDebugStepOut(sessionId: string): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/step-out`, { method: 'POST', body: '{}' })
}

// ===== 0.8.0: Debugger Variables =====

export function postDebugVariablesApply(sessionId: string, body: DebugVariablesApplyRequest): Promise<DebugVariablesApplyResponse> {
  return request<DebugVariablesApplyResponse>(`/workbench/debug/${sessionId}/variables/apply`, { method: 'POST', body: JSON.stringify(body) })
}

export function postDebugNodeDebuggerApply(
  sessionId: string,
  nodeId: string,
  debuggerConfig: Record<string, unknown>,
): Promise<DebugSessionDetailResponse & { node_id: string; debugger: Record<string, unknown> }> {
  return request(`/workbench/debug/${sessionId}/debugger-config/apply`, {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, debugger: debuggerConfig }),
  })
}

// ===== 0.8.0: Debugger Events =====

export function fetchDebugEvents(sessionId: string): Promise<DebugEventsResponse> {
  return request<DebugEventsResponse>(`/workbench/debug/${sessionId}/events`)
}

export function postDebugPause(sessionId: string, body?: { reason: string; node_id?: string }): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/pause`, { method: 'POST', body: JSON.stringify(body || { reason: 'manual_pause' }) })
}

export function postDebugAbort(sessionId: string, body?: { reason: string }): Promise<DebugControlResponse> {
  return request<DebugControlResponse>(`/workbench/debug/${sessionId}/abort`, { method: 'POST', body: JSON.stringify(body || { reason: 'user_abort' }) })
}

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

// ===== 0.8.1: Configuration (legacy visual adapter) =====
type ProgramConfigurationValues = { values: Record<string, Record<string, unknown>> }
const PROGRAM_SECTION_DOMAINS: Record<string, string[]> = { program_settings: ['ui', 'workspace', 'updates'], security_settings: ['security'], python_runtime_settings: ['python_defaults'], network_settings: ['network_defaults'] }
function legacyPreferences(values: Record<string, Record<string, unknown>>): PreferencesResponse { return { preferences: { preferences_file_version: 2, program_settings: { ...(values.ui || {}), ...(values.workspace || {}), ...(values.updates || {}) }, compile_settings: {}, security_settings: values.security || {}, python_runtime_settings: values.python_defaults || {}, network_settings: values.network_defaults || {}, graph_settings: {}, other_settings: {} } } }
function configurationOperations(section: string, values: Record<string, unknown>) {
  const domains = PROGRAM_SECTION_DOMAINS[section] || []
  const known = new Map<string, string>([['default_window_size', 'ui'], ['theme', 'ui'], ['language', 'ui'], ['resource_language', 'ui'], ['font_scale', 'ui'], ['default_project_directory', 'workspace'], ['recent_project_limit', 'workspace'], ['preferences_auto_save', 'workspace'], ['check_updates_on_startup', 'updates']])
  return Object.entries(values).flatMap(([key, value]) => {
    const domain = known.get(key) || (domains.includes('security') ? 'security' : domains.includes('python_defaults') ? 'python_defaults' : domains.includes('network_defaults') ? 'network_defaults' : undefined)
    return domain ? [{ op: 'replace', path: `/${domain}/${key}`, value }] : []
  })
}
export async function fetchPreferences(): Promise<PreferencesResponse> { const result = await request<ProgramConfigurationValues>('/workbench/config/values?scope=program'); return legacyPreferences(result.values) }
export async function postPreferences(body: PreferencesUpdateRequest): Promise<PreferencesResponse> { const result = await request<ProgramConfigurationValues>('/workbench/config/values', { method: 'PATCH', body: JSON.stringify({ scope: 'program', operations: configurationOperations(body.section, body.values), confirm_high_risk: body.confirm_high_risk === true }) }); return legacyPreferences(result.values) }
export async function postPreferencesPreview(body: { section: string; values: Record<string, unknown> }): Promise<{ section: string; current_values: Record<string, unknown>; proposed_values: Record<string, unknown>; confirmation_required: boolean; high_risk_changes: { field: string; from: unknown; to: unknown; reason: string }[] }> { const result = await request<any>('/workbench/config/preview', { method: 'POST', body: JSON.stringify({ scope: 'program', operations: configurationOperations(body.section, body.values) }) }); return { section: body.section, current_values: legacyPreferences(result.current_values).preferences[body.section] as Record<string, unknown>, proposed_values: legacyPreferences(result.proposed_values).preferences[body.section] as Record<string, unknown>, confirmation_required: result.confirmation_required, high_risk_changes: (result.high_risk_changes || []).map((item: any) => ({ field: String(item.path || '').split('/').pop() || '', from: item.from, to: item.to, reason: 'changes high-risk configuration' })) } }
export async function postPreferencesReset(): Promise<PreferencesResponse> { const result = await request<ProgramConfigurationValues>('/workbench/config/reset', { method: 'POST', body: JSON.stringify({ scope: 'program' }) }); return legacyPreferences(result.values) }

export type ExternalApiPreferences = { enabled: boolean; token: string | null; token_configured: boolean; local_api_port: number; active_listener: { host: string; port: number }; restart_required: boolean; project_allowed_roots: string[] }
export type ExternalApiPreferencesUpdate = { enabled: boolean; token?: string; clear_token: boolean; local_api_port: number; project_allowed_roots: string[]; confirm_high_risk: boolean }
export function fetchExternalApiPreferences(): Promise<ExternalApiPreferences> { return request('/workbench/preferences/external-api') }
export function postExternalApiPreferences(body: ExternalApiPreferencesUpdate): Promise<ExternalApiPreferences> { return request('/workbench/preferences/external-api', { method: 'POST', body: JSON.stringify(body) }) }

export function fetchConfigValues<TValues = Record<string, unknown>>(scope: 'program' | 'project' | 'graph'): Promise<ConfigValuesResponse<TValues>> {
  return request<ConfigValuesResponse<TValues>>(`/workbench/config/values?scope=${encodeURIComponent(scope)}`)
}

export function patchConfigValues<TValues = Record<string, unknown>>(body: ConfigPatchRequest): Promise<ConfigValuesResponse<TValues>> {
  return request<ConfigValuesResponse<TValues>>('/workbench/config/values', {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function resetConfigValues<TValues = Record<string, unknown>>(scope: 'program' | 'project' | 'graph'): Promise<ConfigValuesResponse<TValues>> {
  return request<ConfigValuesResponse<TValues>>('/workbench/config/reset', {
    method: 'POST',
    body: JSON.stringify({ scope }),
  })
}

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
export function postGraphUpgradeApply(decision: 'upgrade_and_load'): Promise<{ status: string; project: Record<string, unknown>; graph_document: Record<string, unknown> }> {
  return request('/workbench/project/graph-upgrade/apply', { method: 'POST', body: JSON.stringify({ decision }) })
}
export function postGraphUpgradeRecheck(): Promise<import('@/types/domains/api').GraphUpgradeRecheckResponse> {
  return request('/workbench/project/graph-upgrade/recheck', { method: 'POST', body: '{}' })
}

// ===== P16: Project Settings & .wcrun Package =====
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

export type EncryptedParameterDefinition = { parameter_id: string; name: string; type: string }
export type EncryptedParameterSummary = { configured: boolean; parameter_set_id: string | null; parameters: EncryptedParameterDefinition[] }
export function fetchEncryptedParameters(): Promise<EncryptedParameterSummary> { return request('/workbench/project/encrypted-parameters') }
export function postEncryptedParameters(body: { parameter_set_id: string; parameters: EncryptedParameterDefinition[]; values: Record<string, unknown>; password: string; confirm_overwrite: boolean }): Promise<EncryptedParameterSummary> { return request('/workbench/project/encrypted-parameters', { method: 'POST', body: JSON.stringify(body) }) }
export function postRekeyEncryptedParameters(body: { current_password: string; new_password: string }): Promise<EncryptedParameterSummary> { return request('/workbench/project/encrypted-parameters/rekey', { method: 'POST', body: JSON.stringify(body) }) }
export function postDeleteEncryptedParameters(body: { confirm_delete: boolean }): Promise<EncryptedParameterSummary> { return request('/workbench/project/encrypted-parameters/delete', { method: 'POST', body: JSON.stringify(body) }) }

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

// ===== 0.7.4: Security Requirements =====

export function postSecurityEnableRequired(body: { confirm_high_risk: boolean }): Promise<import('@/types/domains/api').SecurityEnableRequiredResponse> {
  return request('/workbench/project/security/enable-required', { method: 'POST', body: JSON.stringify(body) })
}

// ===== Startup diagnostics & recovery =====

/**
 * Fetch the startup diagnostics report. It intentionally bypasses `request`
 * so it does NOT emit a `weconduct:api-error` event — this endpoint is itself
 * the error-reporting path. It still uses the common header builder because
 * desktop startup diagnostics are protected by the in-memory UI session token.
 * Throws on transport failure (backend fully unreachable) so the caller can
 * fall back to a client-side "critical" classification.
 */
export async function fetchStartupDiagnostics(): Promise<StartupDiagnosticsResponse> {
  const res = await fetch(`${API_BASE}/startup/diagnostics`, {
    headers: buildRequestHeaders({ headers: { 'Content-Type': 'application/json' } }),
  })
  const body = await res.json()
  if (!res.ok) throw new ApiError(res.status, body)
  return body as StartupDiagnosticsResponse
}

export function postStartupRecover(targets?: string[]): Promise<StartupRecoverResponse> {
  return request<StartupRecoverResponse>('/startup/recover', {
    method: 'POST',
    body: JSON.stringify(targets ? { targets } : {}),
  })
}

// ===== 0.8.2: Language packs (external, runtime-loaded) =====

/** One entry from `GET /api/workbench/languages` — a discovered pack manifest. */
export interface LanguageManifest {
  locale: string
  display_name: string
  author?: string
  version?: string
  description?: string
}

export interface LanguagesResponse {
  languages: LanguageManifest[]
  /** Absolute path to the program's `languages/` directory (for "open data dir"). */
  languages_directory?: string
}

export interface LanguagePackResponse {
  locale: string
  messages: Record<string, unknown>
}

/** List the language packs discovered in the program's `languages/` directory. */
export function fetchLanguages(): Promise<LanguagesResponse> {
  return request<LanguagesResponse>('/workbench/languages')
}

/** Load the merged message tree for one locale (null-safe via 404 handling in caller). */
export function fetchLanguagePack(locale: string): Promise<LanguagePackResponse> {
  return request<LanguagePackResponse>(`/workbench/languages/${encodeURIComponent(locale)}`)
}

export { ApiError }
