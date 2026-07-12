import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useProjectDiagnosticsStore } from './projectDiagnosticsStore'

describe('projectDiagnosticsStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('deduplicates diagnostics, filters completed info, and clears on project switch', () => {
    const store = useProjectDiagnosticsStore()
    store.switchProject({ project_id: 'project-a', project_name: 'A' })
    store.ingestCatalog({ entries: [
      { diagnostic_id: 'done-1', stage: 'validate', severity: 'info', category: 'validate.completed', message: 'done' },
      { diagnostic_id: 'error-1', stage: 'bind', severity: 'error', category: 'bind.failed', message: 'bad binding' },
    ] }, { source: 'compilation', operation: 'compile' })
    store.ingestDiagnostic(
      { diagnostic_id: 'error-1', stage: 'bind', severity: 'error', category: 'bind.failed', message: 'bad binding' },
      { source: 'compilation', operation: 'compile' },
    )

    expect(store.visibleEntries).toHaveLength(1)
    expect(store.visibleEntries[0].count).toBe(2)
    store.switchProject({ project_id: 'project-b', project_name: 'B' })
    expect(store.entries).toEqual([])
  })

  it('normalizes unstructured API failures', () => {
    const store = useProjectDiagnosticsStore()
    store.ingestApiError(
      { status: 503, message: 'service unavailable' },
      { source: 'workspace', operation: 'workspace.refresh_snapshot' },
    )

    expect(store.visibleEntries[0]).toMatchObject({
      category: 'ui.operation_failed',
      http_status: 503,
      operation: 'workspace.refresh_snapshot',
      message: 'service unavailable',
    })
  })
})
