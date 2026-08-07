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
  externalGraphConflict: null as any,
  externalGraphConflictNoticeVisible: false,
  loadGraph: vi.fn(),
  loadRemoteGraph: vi.fn(),
  dismissExternalGraphConflictNotice: vi.fn(),
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
    graphWorkspaceState.externalGraphConflict = null
    graphWorkspaceState.externalGraphConflictNoticeVisible = false
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

  it('存在外部修订冲突时显示基准和远端版本，并允许保留本地草稿', async () => {
    graphWorkspaceState.externalGraphConflict = {
      documentId: undefined, baseRevision: 2, remoteRevision: 5, detectedAt: '2026-08-03T00:00:00.000Z',
    }
    graphWorkspaceState.externalGraphConflictNoticeVisible = true
    const wrapper = mount(GraphCanvasPanel, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    expect(wrapper.get('[data-testid="graph-conflict"]').text()).toContain('2')
    expect(wrapper.get('[data-testid="graph-conflict"]').text()).toContain('5')
    await wrapper.get('[data-testid="keep-local-draft"]').trigger('click')
    expect(graphWorkspaceState.dismissExternalGraphConflictNotice).toHaveBeenCalled()
    expect(graphWorkspaceState.externalGraphConflict).not.toBeNull()
  })

  it('加载远端图前要求确认，确认后调用强制刷新动作', async () => {
    graphWorkspaceState.externalGraphConflict = {
      documentId: undefined, baseRevision: 2, remoteRevision: 5, detectedAt: '2026-08-03T00:00:00.000Z',
    }
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const wrapper = mount(GraphCanvasPanel, {
      global: { stubs: { VueFlowGraph: defineComponent({ template: '<div />' }) } },
    })

    await wrapper.get('[data-testid="load-remote-graph"]').trigger('click')
    expect(window.confirm).toHaveBeenCalled()
    expect(graphWorkspaceState.loadRemoteGraph).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
