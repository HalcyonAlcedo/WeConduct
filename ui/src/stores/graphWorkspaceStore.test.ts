import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchGraphDocument: vi.fn(),
  putGraphDocument: vi.fn(),
  postSourceProjection: vi.fn(),
  fetchNodeDraft: vi.fn(),
}))

const diagnosticsState = vi.hoisted(() => ({
  clearGraphObjectDiagnostics: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchGraphDocument: apiMocks.fetchGraphDocument,
  putGraphDocument: apiMocks.putGraphDocument,
  postSourceProjection: apiMocks.postSourceProjection,
  fetchNodeDraft: apiMocks.fetchNodeDraft,
}))

vi.mock('./projectDiagnosticsStore', () => ({
  useProjectDiagnosticsStore: () => diagnosticsState,
}))

const emptyModel = () => ({
  graph_model_id: 'graph:workspace', compilation_id: null, graph_schema_version: 'graph-v1',
  nodes: [], edges: [], graph_effective_diagnostic_anchor_refs: [],
}) as any

const editableView = () => ({ graph_document_save_revision: 1, is_editable: true, last_compile_matches_saved_graph: true } as any)
const readonlyView = () => ({ graph_document_save_revision: 1, is_editable: false, last_compile_matches_saved_graph: true } as any)

describe('graphWorkspaceStore', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('在只读图稿下拒绝 addNode', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = readonlyView(); store.graphModel = emptyModel()
    const result = await store.addNode({ resource_key: 'flow.start', display_name: '流程入口' })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('在只读图稿下拒绝 pasteNode', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = readonlyView(); store.graphModel = emptyModel()
    const result = await store.pasteNode({ node_kind: 'flow.start', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('forceRefresh 时跳过本地草稿直接调 API', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    apiMocks.fetchGraphDocument.mockResolvedValue({ graph_model: emptyModel(), view: editableView() })
    // Prime draft cache
    store.currentDocumentId = undefined
    store.view = editableView(); store.graphModel = emptyModel(); store.isDirty = true
    store.saveCurrentDraft()
    // forceRefresh should bypass draft cache
    await store.loadGraph(undefined, { forceRefresh: true })
    expect(apiMocks.fetchGraphDocument).toHaveBeenCalledWith(undefined)
    expect(store.isDirty).toBe(false) // refreshed from API
  })

  it('切换文档时恢复对应本地草稿', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    // Simulate main graph loaded
    store.view = editableView(); store.graphModel = { ...emptyModel(), nodes: [{ node_id: 'n1', node_kind: 'flow.start', display_name: 'main', lowered_kind: 'control', source_anchor_ref: 'n1', expansion_role: 'flow:start' }] as any }
    // Save draft
    store.saveCurrentDraft()
    // Switch to subgraph
    store.draftsByDocumentId.set('custom_node_graph:x', {
      document: null, graphModel: { ...emptyModel(), nodes: [{ node_id: 'n2', node_kind: 'browser.click', display_name: 'click', lowered_kind: 'execution', source_anchor_ref: 'n2', expansion_role: 'browser:click' }] as any },
      view: editableView(), isDirty: true, changeRevision: 5, undoStack: [], redoStack: [],
    })
    // Switching should restore subgraph draft without API call
    await store.loadGraph('custom_node_graph:x')
    expect(apiMocks.fetchGraphDocument).not.toHaveBeenCalled()
    expect(store.graphModel?.nodes?.[0]?.display_name).toBe('click')
  })

  it('clearAllDrafts 后 loadGraph 不走草稿恢复', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    apiMocks.fetchGraphDocument.mockResolvedValue({ graph_model: emptyModel(), view: editableView() })
    store.view = editableView(); store.graphModel = emptyModel(); store.isDirty = true
    store.saveCurrentDraft()
    store.clearAllDrafts()
    await store.loadGraph(undefined)
    expect(apiMocks.fetchGraphDocument).toHaveBeenCalled() // draft cleared, must fetch
  })

  it('主图已有 flow.start 时 pasteNode 被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = undefined
    store.graphModel = { ...emptyModel(), nodes: [{ node_id: 'n1', node_kind: 'flow.start', display_name: 'start', lowered_kind: 'control', source_anchor_ref: 'n1', expansion_role: 'flow:start' }] as any }
    const result = await store.pasteNode({ node_kind: 'flow.start', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('子图中 pasteNode(flow.start) 被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = 'custom_node_graph:x'
    store.graphModel = { ...emptyModel(), nodes: [] as any }
    const result = await store.pasteNode({ node_kind: 'flow.start', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('主图中 pasteNode(component.input) 被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = undefined; store.graphModel = emptyModel()
    const result = await store.pasteNode({ node_kind: 'component.input', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('主图中 pasteNode(component.output) 被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = undefined; store.graphModel = emptyModel()
    const result = await store.pasteNode({ node_kind: 'component.output', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('子图已有 component.output 时再次粘贴被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = 'custom_node_graph:x'
    store.graphModel = { ...emptyModel(), nodes: [{ node_id: 'n1', node_kind: 'component.output', display_name: 'out', lowered_kind: 'control', source_anchor_ref: 'n1', expansion_role: 'component:output' }] as any }
    const result = await store.pasteNode({ node_kind: 'component.output', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('子图已有 component.input 时再次粘贴被拒绝', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.currentDocumentId = 'custom_node_graph:x'
    store.graphModel = { ...emptyModel(), nodes: [{ node_id: 'n1', node_kind: 'component.input', display_name: 'in', lowered_kind: 'control', source_anchor_ref: 'n1', expansion_role: 'component:input' }] as any }
    const result = await store.pasteNode({ node_kind: 'component.input', display_name: 'x', node_config: {}, position: { x: 10, y: 20 } })
    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
  })

  it('粘贴节点使用视口位置而非源节点偏移', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView(); store.graphModel = emptyModel()
    store.updateViewport({ x: 400, y: 300, zoom: 1 })
    apiMocks.fetchNodeDraft.mockResolvedValue({
      resource: { resource_key: 'flow.start', display_name: 'x', resource_id: 'r1', resource_type: 'builtin' },
      node: { node_id: 'nn', lowered_kind: 'control', source_anchor_ref: 'nn', expansion_role: 'flow:start', display_name: 'x', node_kind: 'flow.start', ports: [], node_config: {} },
    })
    await store.pasteNode({ node_kind: 'flow.start', display_name: 'x', position: { x: 10, y: 20 } })
    // Should use viewport center (~400, 300) + small offset, not source + 40
    const callArgs = apiMocks.fetchNodeDraft.mock.calls[0][0]
    expect(callArgs.x).toBeGreaterThanOrEqual(390)
    expect(callArgs.y).toBeGreaterThanOrEqual(290)
    expect(callArgs.x).toBeLessThan(500)
    expect(callArgs.y).toBeLessThan(400)
  })

  it('更新动态端口时仅移除引用已删除端口的边', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView()
    store.graphModel = {
      ...emptyModel(),
      nodes: [
        {
          node_id: 'input', node_kind: 'input.request', display_name: '请求输入',
          lowered_kind: 'execution', source_anchor_ref: 'input', expansion_role: 'input:request',
          node_config: {},
          ports: [
            { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
            { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
            { port_id: 'out:kept', direction: 'output', relation_layer: 'data', semantic_slot: 'out.kept' },
            { port_id: 'out:removed', direction: 'output', relation_layer: 'data', semantic_slot: 'out.removed' },
          ],
        },
        {
          node_id: 'sink', node_kind: 'data.set_variable', display_name: '接收',
          lowered_kind: 'execution', source_anchor_ref: 'sink', expansion_role: 'data:set_variable',
          node_config: {}, ports: [],
        },
      ] as any,
      edges: [
        { edge_id: 'keep', relation_layer: 'data', from_node_id: 'input', from_port_id: 'out:kept', to_node_id: 'sink', to_port_id: 'value' },
        { edge_id: 'remove', relation_layer: 'data', from_node_id: 'input', from_port_id: 'out:removed', to_node_id: 'sink', to_port_id: 'value' },
        { edge_id: 'unrelated', relation_layer: 'data', from_node_id: 'sink', from_port_id: 'out', to_node_id: 'other', to_port_id: 'in' },
      ],
    }

    store.updateNode('input', {
      ports: [
        { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
        { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
        { port_id: 'out:kept', direction: 'output', relation_layer: 'data', semantic_slot: 'out.kept' },
      ] as any,
    })

    expect(store.graphModel?.edges.map(edge => edge.edge_id)).toEqual(['keep', 'unrelated'])
  })

  it('更新节点时清除该节点及因端口变更被移除边的高亮诊断', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView()
    store.graphModel = {
      ...emptyModel(),
      nodes: [{ node_id: 'node-a', node_kind: 'input.request', ports: [{ port_id: 'kept' }, { port_id: 'removed' }] }],
      edges: [{ edge_id: 'edge-removed', from_node_id: 'node-a', from_port_id: 'removed', to_node_id: 'node-b', to_port_id: 'value' }],
    } as any

    store.updateNode('node-a', { ports: [{ port_id: 'kept' }] as any })

    expect(diagnosticsState.clearGraphObjectDiagnostics).toHaveBeenCalledWith({
      nodeIds: ['node-a'], edgeIds: ['edge-removed'],
    })
  })

  it('修改或删除边时清除该边的高亮诊断', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = editableView()
    store.graphModel = {
      ...emptyModel(),
      edges: [{ edge_id: 'edge-a', relation_layer: 'control', from_node_id: 'node-a', to_node_id: 'node-b' }],
    } as any

    store.updateEdgeRelation('edge-a', 'data')
    store.removeEdge('edge-a')

    expect(diagnosticsState.clearGraphObjectDiagnostics).toHaveBeenNthCalledWith(1, { edgeIds: ['edge-a'] })
    expect(diagnosticsState.clearGraphObjectDiagnostics).toHaveBeenNthCalledWith(2, { edgeIds: ['edge-a'] })
  })

  it('记录外部图稿变更时保留本地草稿并暴露基准和远端修订', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()

    store.currentDocumentId = undefined
    store.graphModel = emptyModel()
    store.isDirty = true
    const created = store.markExternalGraphConflict({ documentId: undefined, baseRevision: 1, remoteRevision: 9 })

    expect(created).toBe(true)
    expect(store.externalGraphConflict).toMatchObject({
      documentId: undefined,
      baseRevision: 1,
      remoteRevision: 9,
    })
    expect(store.externalGraphConflict?.detectedAt).toEqual(expect.any(String))
    expect(store.isDirty).toBe(true)

    store.dismissExternalGraphConflictNotice()
    expect(store.externalGraphConflict).not.toBeNull()
    expect(store.externalGraphConflictNoticeVisible).toBe(false)
    store.clearExternalGraphConflict()
    expect(store.externalGraphConflict).toBeNull()
  })

  it('重复外部修订只更新远端版本并保持初始基准', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()

    store.currentDocumentId = undefined
    expect(store.markExternalGraphConflict({ documentId: undefined, baseRevision: 2, remoteRevision: 5 })).toBe(true)
    expect(store.markExternalGraphConflict({ documentId: undefined, baseRevision: 2, remoteRevision: 5 })).toBe(false)
    expect(store.markExternalGraphConflict({ documentId: undefined, baseRevision: 2, remoteRevision: 7 })).toBe(false)

    expect(store.externalGraphConflict).toMatchObject({ baseRevision: 2, remoteRevision: 7 })
  })

  it('主图和组件子图的冲突状态按文档隔离', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()

    store.currentDocumentId = undefined
    store.markExternalGraphConflict({ documentId: undefined, baseRevision: 1, remoteRevision: 3 })
    store.currentDocumentId = 'custom_node_graph:component-a'
    store.markExternalGraphConflict({ documentId: 'custom_node_graph:component-a', baseRevision: 4, remoteRevision: 8 })

    expect(store.externalGraphConflict).toMatchObject({ documentId: 'custom_node_graph:component-a', baseRevision: 4, remoteRevision: 8 })
    store.currentDocumentId = undefined
    expect(store.externalGraphConflict).toMatchObject({ documentId: undefined, baseRevision: 1, remoteRevision: 3 })
  })

  it('确认加载远端图后才丢弃本地草稿并清除冲突', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    apiMocks.fetchGraphDocument.mockResolvedValue({ graph_model: emptyModel(), view: editableView() })
    store.currentDocumentId = undefined
    store.graphModel = { ...emptyModel(), nodes: [{ node_id: 'local-node' }] } as any
    store.isDirty = true
    store.markExternalGraphConflict({ documentId: undefined, baseRevision: 1, remoteRevision: 2 })

    await store.loadRemoteGraph()

    expect(apiMocks.fetchGraphDocument).toHaveBeenCalledWith(undefined)
    expect(store.isDirty).toBe(false)
    expect(store.externalGraphConflict).toBeNull()
  })

  it('保存返回旧 revision 冲突时保留本地图并记录远端修订', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    const localModel = { ...emptyModel(), nodes: [{ node_id: 'local-node' }] } as any
    store.currentDocumentId = undefined
    store.view = editableView()
    store.graphModel = localModel
    store.isDirty = true
    store.markExternalGraphConflict({ documentId: undefined, baseRevision: 1, remoteRevision: 5 })
    apiMocks.putGraphDocument.mockRejectedValue({
      status: 409,
      body: { error: 'graph_revision_conflict', current_revision: 6 },
    })

    await store.saveGraph(localModel)

    expect(apiMocks.putGraphDocument).toHaveBeenCalledWith(localModel, 1, undefined, true)
    expect(store.graphModel).toEqual(localModel)
    expect(store.isDirty).toBe(true)
    expect(store.externalGraphConflict).toMatchObject({ baseRevision: 1, remoteRevision: 6 })
  })
})
