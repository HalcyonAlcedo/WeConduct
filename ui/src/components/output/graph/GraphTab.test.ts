import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const graphWorkspaceState = vi.hoisted(() => ({
  isLoaded: true,
  loadState: 'loaded',
  saveState: 'idle',
  graphModel: { graph_model_id: 'graph:workspace', nodes: [], edges: [] } as any,
  saveRevision: 1,
  lastCompileMatches: true,
  view: null as any,
  loadGraph: vi.fn(),
  saveGraph: vi.fn(),
}))

const graphStoreState = vi.hoisted(() => ({
  selectedNode: null as string | null,
  selectNode: vi.fn(),
  selectGraphModel: vi.fn(({ workspaceModel }: any) => ({ model: workspaceModel, source: 'workspace' })),
}))

const compilationState = vi.hoisted(() => ({
  graphStats: null as any,
  outcome: null as any,
  isCompiling: false,
  compilePhase: 'idle',
  compileError: null as string | null,
  lastResponse: null as any,
}))

const diagnosticsState = vi.hoisted(() => ({ ingestCatalog: vi.fn(), ingestApiError: vi.fn(), clearGraphDiagnostics: vi.fn() }))
const apiState = vi.hoisted(() => ({ validate: vi.fn(), compile: vi.fn() }))

vi.mock('@/stores/graphWorkspaceStore', () => ({ useGraphWorkspaceStore: () => graphWorkspaceState }))
vi.mock('@/stores/graphStore', () => ({ useGraphStore: () => graphStoreState }))
vi.mock('@/stores/compilationStore', () => ({ useCompilationStore: () => compilationState }))
vi.mock('@/stores/projectDiagnosticsStore', () => ({ useProjectDiagnosticsStore: () => diagnosticsState }))
vi.mock('@/stores/toastStore', () => ({ useToastStore: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('@/services/api', () => ({
  postGraphValidate: (...args: unknown[]) => apiState.validate(...args),
  postGraphCompile: (...args: unknown[]) => apiState.compile(...args),
}))

import GraphTab from './GraphTab.vue'

const diagnostic = {
  diagnostic_id: 'graph-validate-1', stage: 'validate', severity: 'fatal',
  category: 'graph.edge.relation_layer_mismatch', message: 'edge relation_layer mismatch',
  object_ref: 'edge-1', trace_ref: null, stage_extension: {}, degraded_extension: null,
}

describe('GraphTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    const wrapper = mount(GraphTab, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    await wrapper.get('.gt-actions button').trigger('click')

    expect(diagnosticsState.ingestCatalog).toHaveBeenCalledWith([diagnostic], {
      source: 'compilation', operation: 'graph.validate',
    })
    expect(diagnosticsState.clearGraphDiagnostics).toHaveBeenCalledBefore(diagnosticsState.ingestCatalog)
  })

  it('图编译返回错误时写入统一诊断仓', async () => {
    const wrapper = mount(GraphTab, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    await wrapper.get('.gt-actions button:nth-child(2)').trigger('click')

    expect(diagnosticsState.ingestCatalog).toHaveBeenCalledWith({ entries: [diagnostic] }, {
      source: 'compilation', operation: 'graph.compile',
    })
    expect(diagnosticsState.clearGraphDiagnostics).toHaveBeenCalledBefore(diagnosticsState.ingestCatalog)
  })
})
