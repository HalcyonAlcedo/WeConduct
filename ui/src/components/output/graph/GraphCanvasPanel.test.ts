import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const graphWorkspaceState = vi.hoisted(() => ({
  isLoaded: true,
  graphModel: { graph_model_id: 'graph:workspace', nodes: [], edges: [] } as any,
  currentDocumentId: null as string | null,
  isGraphEditable: true,
  saveRevision: 1,
  lastCompileMatches: true,
  graphDocuments: [] as any[],
  loadGraph: vi.fn(),
  refreshGraphDocuments: vi.fn(),
  syncSource: vi.fn(),
  saveGraph: vi.fn(),
}))

const graphStoreState = vi.hoisted(() => ({
  selectNode: vi.fn(),
  selectGraphModel: vi.fn(({ workspaceModel }: any) => ({ model: workspaceModel, source: 'workspace' })),
}))

const compilationState = vi.hoisted(() => ({
  outcome: null as any,
  lastResponse: null as any,
  compilePhase: 'idle',
  compileError: null as string | null,
  resetCompilation: vi.fn(),
}))

const diagnosticsState = vi.hoisted(() => ({
  ingestCatalog: vi.fn(),
  ingestApiError: vi.fn(),
  clearGraphDiagnostics: vi.fn(),
}))

const apiState = vi.hoisted(() => ({
  validate: vi.fn(),
  compile: vi.fn(),
}))

vi.mock('@/stores/graphWorkspaceStore', () => ({ useGraphWorkspaceStore: () => graphWorkspaceState }))
vi.mock('@/stores/graphStore', () => ({ useGraphStore: () => graphStoreState }))
vi.mock('@/stores/compilationStore', () => ({ useCompilationStore: () => compilationState }))
vi.mock('@/stores/projectDiagnosticsStore', () => ({ useProjectDiagnosticsStore: () => diagnosticsState }))
vi.mock('@/stores/toastStore', () => ({ useToastStore: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('@/stores/resourceStore', () => ({ useResourceStore: () => ({ refreshAll: vi.fn() }) }))
vi.mock('@/services/api', () => ({
  postGraphValidate: (...args: unknown[]) => apiState.validate(...args),
  postGraphCompile: (...args: unknown[]) => apiState.compile(...args),
  postCreateEmptyCustomComponent: vi.fn(),
}))

import GraphCanvasPanel from './GraphCanvasPanel.vue'

const diagnostic = {
  diagnostic_id: 'graph-validate-1', stage: 'validate', severity: 'fatal',
  category: 'graph.edge.relation_layer_mismatch', message: 'edge relation_layer mismatch',
  object_ref: 'edge-1', trace_ref: null, stage_extension: {}, degraded_extension: null,
}

describe('GraphCanvasPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    compilationState.outcome = null
    compilationState.lastResponse = null
    compilationState.compilePhase = 'idle'
    apiState.validate.mockResolvedValue({
      status: 'invalid', summary: { error_count: 1, warning_count: 0 }, diagnostics: [diagnostic],
    })
    apiState.compile.mockResolvedValue({
      status: 'failed', request: {},
      outcome: { graph_model: null, compilation_summary: {}, diagnostic_catalog: { entries: [diagnostic] } },
      view: { primary_diagnostic: diagnostic, graph_stats: { node_count: 0 } },
    })
  })

  it('图校验返回错误时写入统一诊断仓', async () => {
    const wrapper = mount(GraphCanvasPanel, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    await wrapper.get('.gcp-actions button').trigger('click')

    expect(diagnosticsState.ingestCatalog).toHaveBeenCalledWith([diagnostic], {
      source: 'compilation', operation: 'graph.validate',
    })
    expect(diagnosticsState.clearGraphDiagnostics).toHaveBeenCalledBefore(diagnosticsState.ingestCatalog)
  })

  it('图编译返回错误时写入统一诊断仓', async () => {
    const wrapper = mount(GraphCanvasPanel, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    await wrapper.get('.gcp-actions button:nth-child(2)').trigger('click')

    expect(diagnosticsState.ingestCatalog).toHaveBeenCalledWith({ entries: [diagnostic] }, {
      source: 'compilation', operation: 'graph.compile',
    })
    expect(diagnosticsState.clearGraphDiagnostics).toHaveBeenCalledBefore(diagnosticsState.ingestCatalog)
  })
})
