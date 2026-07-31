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

  it('clears only diagnostics targeting edited graph nodes and edges', () => {
    const store = useProjectDiagnosticsStore()
    store.ingestCatalog({ entries: [
      { diagnostic_id: 'node-ref', stage: 'validate', severity: 'error', category: 'graph.node.invalid', message: 'node error', object_ref: 'node:node-a' },
      { diagnostic_id: 'edge-ref', stage: 'validate', severity: 'error', category: 'graph.edge.invalid', message: 'edge error', object_ref: 'edge-a' },
      { diagnostic_id: 'extension-ref', stage: 'compile', severity: 'fatal', category: 'graph.edge.invalid', message: 'extension edge error', stage_extension: { graph_ref: { edge_id: 'edge-b' } } },
      { diagnostic_id: 'unrelated', stage: 'validate', severity: 'error', category: 'graph.node.invalid', message: 'unrelated', object_ref: 'node-b' },
    ] }, { source: 'compilation', operation: 'compile' })

    store.clearGraphObjectDiagnostics({ nodeIds: ['node-a'], edgeIds: ['edge-a', 'edge-b'] })

    expect(store.visibleEntries.map(entry => entry.diagnostic_id)).toEqual(['unrelated'])
  })

  it('clears every graph diagnostic before a new validation or compilation attempt', () => {
    const store = useProjectDiagnosticsStore()
    store.ingestCatalog({ entries: [
      { diagnostic_id: 'graph', stage: 'validate', severity: 'error', category: 'graph.node.invalid', message: 'graph error', object_ref: 'node-a' },
      { diagnostic_id: 'ui', stage: 'ui', severity: 'error', category: 'ui.operation_failed', message: 'api error' },
    ] }, { source: 'compilation', operation: 'compile' })

    store.clearGraphDiagnostics()

    expect(store.visibleEntries.map(entry => entry.diagnostic_id)).toEqual(['ui'])
  })

  it('does not treat a node-prefixed reference as an edge with the same identifier', () => {
    const store = useProjectDiagnosticsStore()
    store.ingestDiagnostic(
      { diagnostic_id: 'node-ref', stage: 'validate', severity: 'error', category: 'graph.node.invalid', message: 'node error', object_ref: 'node:shared-id' },
      { source: 'compilation', operation: 'compile' },
    )

    store.clearGraphObjectDiagnostics({ edgeIds: ['shared-id'] })

    expect(store.visibleEntries.map(entry => entry.diagnostic_id)).toEqual(['node-ref'])
  })
})
