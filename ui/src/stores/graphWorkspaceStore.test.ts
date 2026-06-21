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

describe('graphWorkspaceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('在只读图稿下拒绝 addNode', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = {
      graph_document_save_revision: 1,
      is_editable: false,
      last_compile_matches_saved_graph: true,
    } as any
    store.graphModel = {
      graph_model_id: 'graph:workspace',
      compilation_id: null,
      graph_schema_version: 'graph-v1',
      nodes: [],
      edges: [],
      graph_effective_diagnostic_anchor_refs: [],
    } as any

    const result = await store.addNode({
      resource_key: 'flow.start',
      display_name: '流程入口',
    })

    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
    expect(store.graphModel?.nodes).toHaveLength(0)
  })

  it('在只读图稿下拒绝 pasteNode', async () => {
    const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
    const store = useGraphWorkspaceStore()
    store.view = {
      graph_document_save_revision: 1,
      is_editable: false,
      last_compile_matches_saved_graph: true,
    } as any
    store.graphModel = {
      graph_model_id: 'graph:workspace',
      compilation_id: null,
      graph_schema_version: 'graph-v1',
      nodes: [],
      edges: [],
      graph_effective_diagnostic_anchor_refs: [],
    } as any

    const result = await store.pasteNode({
      node_kind: 'flow.start',
      display_name: '流程入口',
      node_config: {},
      position: { x: 10, y: 20 },
    })

    expect(result).toBeNull()
    expect(apiMocks.fetchNodeDraft).not.toHaveBeenCalled()
    expect(store.graphModel?.nodes).toHaveLength(0)
  })
})
