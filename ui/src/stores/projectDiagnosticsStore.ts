import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  Diagnostic,
  DiagnosticSeverity,
  ProjectDiagnostic,
  ProjectDiagnosticSource,
} from '@/types/domains/diagnostics'

type ProjectContext = { project_id?: string | null; project_name?: string | null }
type IngestOptions = {
  source: ProjectDiagnosticSource
  operation?: string | null
  project?: ProjectContext
  httpStatus?: number | null
  errorCode?: string | null
  rawDetails?: unknown
}

function isHiddenCompletedInfo(diagnostic: Pick<Diagnostic, 'severity' | 'category'>) {
  return diagnostic.severity === 'info' && diagnostic.category.endsWith('.completed')
}

function fingerprintOf(diagnostic: Diagnostic, options: IngestOptions) {
  return [
    options.source,
    options.operation ?? '',
    diagnostic.stage,
    diagnostic.category,
    diagnostic.severity,
    diagnostic.message,
    diagnostic.object_ref ?? '',
  ].join('|')
}

function normalizeDiagnostic(input: Partial<Diagnostic>, fallbackMessage: string): Diagnostic {
  return {
    diagnostic_id: typeof input.diagnostic_id === 'string' ? input.diagnostic_id : '',
    stage: (input.stage ?? 'ui') as Diagnostic['stage'],
    severity: (input.severity ?? 'error') as DiagnosticSeverity,
    category: typeof input.category === 'string' ? input.category : 'ui.operation_failed',
    message: typeof input.message === 'string' && input.message ? input.message : fallbackMessage,
    object_ref: typeof input.object_ref === 'string' ? input.object_ref : null,
    trace_ref: typeof input.trace_ref === 'string' ? input.trace_ref : null,
    stage_extension: input.stage_extension && typeof input.stage_extension === 'object' ? input.stage_extension : {},
    degraded_extension: input.degraded_extension && typeof input.degraded_extension === 'object' ? input.degraded_extension : null,
  }
}

function graphReferenceOf(diagnostic: Diagnostic): Record<string, unknown> | null {
  const extension = diagnostic.stage_extension
  if (!extension || typeof extension !== 'object') return null
  const graphRef = (extension as Record<string, unknown>).graph_ref
  return graphRef && typeof graphRef === 'object' && !Array.isArray(graphRef)
    ? graphRef as Record<string, unknown>
    : null
}

function referencesGraphObject(diagnostic: Diagnostic, nodeIds: ReadonlySet<string>, edgeIds: ReadonlySet<string>): boolean {
  const graphRef = graphReferenceOf(diagnostic)
  const objectRef = diagnostic.object_ref
  const nodeRef = typeof graphRef?.node_id === 'string' ? graphRef.node_id : null
  const edgeRef = typeof graphRef?.edge_id === 'string' ? graphRef.edge_id : null
  return (typeof objectRef === 'string' && (nodeIds.has(objectRef) || edgeIds.has(objectRef)
    || nodeIds.has(objectRef.replace(/^node:/, '')) || edgeIds.has(objectRef.replace(/^edge:/, ''))))
    || (nodeRef !== null && nodeIds.has(nodeRef))
    || (edgeRef !== null && edgeIds.has(edgeRef))
}

function isGraphDiagnostic(diagnostic: Diagnostic): boolean {
  return diagnostic.category.startsWith('graph.') || graphReferenceOf(diagnostic) !== null
}

export const useProjectDiagnosticsStore = defineStore('projectDiagnostics', () => {
  const entries = ref<ProjectDiagnostic[]>([])
  const activeProjectId = ref<string | null>(null)
  const activeProjectName = ref<string | null>(null)
  let apiErrorListenerInstalled = false

  const visibleEntries = computed(() => entries.value.filter(entry => !isHiddenCompletedInfo(entry)))

  function switchProject(project: ProjectContext = {}) {
    const nextId = project.project_id ?? null
    const nextName = project.project_name ?? null
    if (nextId !== activeProjectId.value || nextName !== activeProjectName.value) {
      entries.value = []
    }
    activeProjectId.value = nextId
    activeProjectName.value = nextName
  }

  function ingestDiagnostic(input: Partial<Diagnostic>, options: IngestOptions) {
    const diagnostic = normalizeDiagnostic(input, '操作失败')
    if (isHiddenCompletedInfo(diagnostic)) return null
    const now = new Date().toISOString()
    const projectId = options.project?.project_id ?? activeProjectId.value
    const projectName = options.project?.project_name ?? activeProjectName.value
    const fingerprint = fingerprintOf(diagnostic, options)
    const existing = entries.value.find(entry =>
      (diagnostic.diagnostic_id && entry.diagnostic_id === diagnostic.diagnostic_id)
      || entry.fingerprint === fingerprint,
    )
    if (existing) {
      existing.count += 1
      existing.last_seen_at = now
      existing.raw_details = options.rawDetails ?? existing.raw_details
      return existing
    }
    const entry: ProjectDiagnostic = {
      ...diagnostic,
      diagnostic_id: diagnostic.diagnostic_id || `ui:${fingerprint}`,
      source: options.source,
      operation: options.operation ?? null,
      project_id: projectId,
      project_name: projectName,
      fingerprint,
      http_status: options.httpStatus ?? null,
      error_code: options.errorCode ?? diagnostic.category,
      raw_details: options.rawDetails ?? null,
      count: 1,
      first_seen_at: now,
      last_seen_at: now,
    }
    entries.value.push(entry)
    return entry
  }

  function ingestCatalog(catalog: unknown, options: IngestOptions) {
    const sourceEntries = Array.isArray(catalog)
      ? catalog
      : (catalog as any)?.entries
    if (!Array.isArray(sourceEntries)) return
    for (const entry of sourceEntries) {
      if (entry && typeof entry === 'object') ingestDiagnostic(entry, options)
    }
  }

  function ingestApiError(error: any, options: Omit<IngestOptions, 'rawDetails'>) {
    const body = error?.body && typeof error.body === 'object' ? error.body : null
    const structured = body?.details?.primary_diagnostic ?? body?.primary_diagnostic
    if (structured && typeof structured === 'object') {
      return ingestDiagnostic(structured, {
        ...options,
        httpStatus: error?.status ?? body?.status ?? null,
        errorCode: body?.error ?? structured.category ?? null,
        rawDetails: body,
      })
    }
    return ingestDiagnostic({
      stage: 'ui',
      severity: 'error',
      category: 'ui.operation_failed',
      message: body?.message || body?.error || error?.message || '操作失败',
      object_ref: body?.object_ref ?? null,
      stage_extension: { operation: options.operation ?? null },
    }, {
      ...options,
      httpStatus: error?.status ?? null,
      errorCode: body?.error ?? null,
      rawDetails: body ?? error,
    })
  }

  function clearForProject() { entries.value = [] }

  function clearGraphObjectDiagnostics(targets: { nodeIds?: Iterable<string>; edgeIds?: Iterable<string> }) {
    const nodeIds = new Set(targets.nodeIds ?? [])
    const edgeIds = new Set(targets.edgeIds ?? [])
    if (nodeIds.size === 0 && edgeIds.size === 0) return
    entries.value = entries.value.filter(entry => !referencesGraphObject(entry, nodeIds, edgeIds))
  }

  function clearGraphDiagnostics() {
    entries.value = entries.value.filter(entry => !isGraphDiagnostic(entry))
  }

  if (typeof window !== 'undefined' && !apiErrorListenerInstalled) {
    window.addEventListener('weconduct:api-error', ((event: CustomEvent) => {
      const detail = event.detail || {}
      ingestApiError(detail.error, {
        source: 'ui',
        operation: `${detail.method || 'GET'} ${detail.path || 'api'}`,
      })
    }) as EventListener)
    apiErrorListenerInstalled = true
  }

  return {
    entries,
    visibleEntries,
    activeProjectId,
    activeProjectName,
    switchProject,
    ingestDiagnostic,
    ingestCatalog,
    ingestApiError,
    clearForProject,
    clearGraphObjectDiagnostics,
    clearGraphDiagnostics,
  }
})
