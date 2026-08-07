import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  fetchSnapshot: vi.fn(),
  consumeSse: vi.fn(),
}))

const diagnosticsState = vi.hoisted(() => ({
  switchProject: vi.fn(),
  ingestApiError: vi.fn(),
}))

const graphState = vi.hoisted(() => ({
  isDirty: false,
  isLoaded: true,
  saveRevision: 1,
  currentDocumentId: undefined as string | undefined,
  loadGraph: vi.fn(),
  refreshGraphDocuments: vi.fn(),
  markExternalGraphConflict: vi.fn(),
  reset: vi.fn(),
}))

const runtimeState = vi.hoisted(() => ({
  handleWorkbenchSessionEvent: vi.fn(),
  recoverActiveSession: vi.fn(),
}))

const toastState = vi.hoisted(() => ({
  warning: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchHealth: apiMocks.fetchHealth,
  fetchSnapshot: apiMocks.fetchSnapshot,
  consumeSse: apiMocks.consumeSse,
}))

vi.mock('./projectDiagnosticsStore', () => ({
  useProjectDiagnosticsStore: () => diagnosticsState,
}))

vi.mock('./graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphState,
}))

vi.mock('./runtimeStore', () => ({
  useRuntimeStore: () => runtimeState,
}))

vi.mock('./toastStore', () => ({
  useToastStore: () => toastState,
}))

function snapshot(projectName = 'initial-project', loaded = true, revision = 1) {
  return {
    workbench: { compile_counter: 0 },
    project: {
      loaded,
      project_id: loaded ? `project-${projectName}` : 'workspace',
      project_name: projectName,
      project_status: loaded ? 'loaded' : 'empty',
    },
    graph_workspace: {
      graph_document_save_revision: revision,
    },
    capabilities: { compiler_available: true, runtime_available: true, debug_available: true },
    entrypoints: {},
    compiler: { available_source_kinds: [], default_source_kind: 'native_flow', supported_stage_names: [], compile_statuses: [], source_templates: {}, compile_history_limit: 10, diagnostic_severities: [] },
    last_compile: null,
    compile_history: [],
    ui_hosting: { ui_hosted: true, ui_dist_available: true, ui_dist_path: '', ui_entrypoint: null },
  }
}

describe('workspaceStore external event synchronization', () => {
  let sseOptions: { lastEventId?: number | string | null; onEvent: (event: any) => void | Promise<void> } | null

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    graphState.isDirty = false
    graphState.isLoaded = true
    graphState.saveRevision = 1
    graphState.currentDocumentId = undefined
    graphState.markExternalGraphConflict.mockReturnValue(true)
    sseOptions = null
    apiMocks.fetchHealth.mockResolvedValue({ status: 'ok', capabilities: {} })
    apiMocks.fetchSnapshot.mockResolvedValue(snapshot())
    apiMocks.consumeSse.mockImplementation(async (_path: string, options: typeof sseOptions) => {
      sseOptions = options
      await new Promise<void>(() => {})
    })
  })

  it('订阅工作台 SSE 后应用外部快照、项目和图变更', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()

    await vi.waitFor(() => expect(sseOptions).not.toBeNull())
    await sseOptions!.onEvent({ event: 'workbench.snapshot', id: '4', data: JSON.stringify(snapshot('external-project')) })
    expect(store.projectName).toBe('external-project')
    expect(store.workbenchEventLastId).toBe(4)

    await sseOptions!.onEvent({
      event: 'workspace.project_changed',
      id: '5',
      data: JSON.stringify({ project_id: 'project-next', project_name: 'next', loaded: true, reason: 'opened' }),
    })
    expect(apiMocks.fetchSnapshot).toHaveBeenCalledTimes(2)

    await sseOptions!.onEvent({
      event: 'workspace.graph_changed',
      id: '6',
      data: JSON.stringify({ document_id: 'graph:workspace', revision: 2, reason: 'saved' }),
    })
    expect(graphState.loadGraph).toHaveBeenCalledWith(undefined, { forceRefresh: true })
  })

  it('本地图稿有未保存修改时不被外部图事件覆盖，而是标记冲突', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    graphState.isDirty = true
    await sseOptions!.onEvent({
      event: 'workspace.graph_changed',
      id: '7',
      data: JSON.stringify({ document_id: 'graph:workspace', revision: 3, reason: 'external_save' }),
    })

    expect(graphState.markExternalGraphConflict).toHaveBeenCalledWith({
      documentId: undefined, baseRevision: 1, remoteRevision: 3,
    })
    expect(graphState.loadGraph).not.toHaveBeenCalled()
  })

  it('重复 graph_changed 修订只提示一次并保留最初本地基准', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    graphState.isDirty = true
    graphState.markExternalGraphConflict.mockReturnValueOnce(true).mockReturnValue(false)
    const first = { event: 'workspace.graph_changed', id: '11', data: JSON.stringify({ document_id: 'graph:workspace', revision: 3 }) }
    const second = { event: 'workspace.graph_changed', id: '12', data: JSON.stringify({ document_id: 'graph:workspace', revision: 5 }) }
    await sseOptions!.onEvent(first)
    await sseOptions!.onEvent(second)

    expect(graphState.markExternalGraphConflict).toHaveBeenNthCalledWith(1, {
      documentId: undefined, baseRevision: 1, remoteRevision: 3,
    })
    expect(graphState.markExternalGraphConflict).toHaveBeenNthCalledWith(2, {
      documentId: undefined, baseRevision: 1, remoteRevision: 5,
    })
    expect(toastState.warning).toHaveBeenCalledTimes(1)
  })

  it('外部运行会话事件交给 runtime store 收敛', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    await sseOptions!.onEvent({
      event: 'runtime.session_changed',
      id: '8',
      data: JSON.stringify({ session_id: 'external-runtime-1', status: 'running', reason: 'execution_started' }),
    })

    expect(runtimeState.handleWorkbenchSessionEvent).toHaveBeenCalledWith({
      session_id: 'external-runtime-1', status: 'running', reason: 'execution_started',
    })
  })

  it('工作台事件游标过期时清零游标并重新从全量快照收敛', async () => {
    vi.useFakeTimers()
    const calls: Array<{ lastEventId?: number | string | null }> = []
    apiMocks.consumeSse.mockImplementation(async (_path: string, options: any) => {
      calls.push(options)
      if (calls.length === 1) {
        throw { status: 409, body: { error: 'workbench.event_cursor_expired' } }
      }
      await new Promise<void>(() => {})
    })

    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.workbenchEventLastId = 99
    store.startEventStream()
    await Promise.resolve()
    await Promise.resolve()
    expect(calls[0].lastEventId).toBe(99)

    await vi.advanceTimersByTimeAsync(500)
    expect(calls[1].lastEventId).toBeNull()
    store.stopEventStream()
    vi.useRealTimers()
  })

  it('工作台快照发现外部图修订变化时刷新干净图稿并恢复活动会话', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    await sseOptions!.onEvent({
      event: 'workbench.snapshot',
      id: '9',
      data: JSON.stringify(snapshot('initial-project', true, 2)),
    })

    expect(graphState.loadGraph).toHaveBeenCalledWith(undefined, { forceRefresh: true })
    expect(runtimeState.recoverActiveSession).toHaveBeenCalledTimes(1)
  })

  it('查看组件子图时工作台快照只刷新当前组件子图', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    graphState.currentDocumentId = 'custom_node_graph:component-a'
    await sseOptions!.onEvent({
      event: 'workbench.snapshot',
      id: '9b',
      data: JSON.stringify(snapshot('initial-project', true, 2)),
    })

    expect(graphState.loadGraph).toHaveBeenCalledWith('custom_node_graph:component-a', { forceRefresh: true })
  })

  it('查看脏的组件子图时主图快照修订不产生子图冲突', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    graphState.currentDocumentId = 'custom_node_graph:component-a'
    graphState.isDirty = true
    await sseOptions!.onEvent({
      event: 'workbench.snapshot',
      id: '9c',
      data: JSON.stringify(snapshot('initial-project', true, 2)),
    })

    expect(graphState.markExternalGraphConflict).not.toHaveBeenCalled()
    expect(graphState.loadGraph).not.toHaveBeenCalled()
  })

  it('工作台快照发现外部图修订变化时保留脏图并记录冲突', async () => {
    const { useWorkspaceStore } = await import('./workspaceStore')
    const store = useWorkspaceStore()
    await store.initialize()
    store.startEventStream()
    await vi.waitFor(() => expect(sseOptions).not.toBeNull())

    graphState.isDirty = true
    await sseOptions!.onEvent({
      event: 'workbench.snapshot',
      id: '10',
      data: JSON.stringify(snapshot('initial-project', true, 3)),
    })

    expect(graphState.markExternalGraphConflict).toHaveBeenCalledWith({
      documentId: undefined, baseRevision: 1, remoteRevision: 3,
    })
    expect(graphState.loadGraph).not.toHaveBeenCalled()
  })
})
