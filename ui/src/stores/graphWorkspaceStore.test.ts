import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchGraphDocument: vi.fn(),
  putGraphDocument: vi.fn(),
  postSourceProjection: vi.fn(),
  fetchNodeDraft: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchGraphDocument: apiMocks.fetchGraphDocument,
  putGraphDocument: apiMocks.putGraphDocument,
  postSourceProjection: apiMocks.postSourceProjection,
  fetchNodeDraft: apiMocks.fetchNodeDraft,
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
})
