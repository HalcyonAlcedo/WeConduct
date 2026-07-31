import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchDebugSessions: vi.fn(),
  fetchDebugHistorySessions: vi.fn(),
  fetchDebugSession: vi.fn(),
  fetchDebugHistorySession: vi.fn(),
  fetchDebugProjection: vi.fn(),
  fetchDebugEvents: vi.fn(),
  postDebugPrepare: vi.fn(),
  postDebugStart: vi.fn(),
  postDebugParameterUnlock: vi.fn(),
  postDebugSensitiveValuesReveal: vi.fn(),
  postDebugContinue: vi.fn(),
  postDebugStepOver: vi.fn(),
  postDebugStepInto: vi.fn(),
  postDebugStepOut: vi.fn(),
  postDebugPause: vi.fn(),
  postDebugAbort: vi.fn(),
  postDebugVariablesApply: vi.fn(),
  postDebugNodeDebuggerApply: vi.fn(),
  fetchGraphDocument: vi.fn(),
  putGraphDocument: vi.fn(),
  postSourceProjection: vi.fn(),
  fetchNodeDraft: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchDebugSessions: apiMocks.fetchDebugSessions,
  fetchDebugHistorySessions: apiMocks.fetchDebugHistorySessions,
  fetchDebugSession: apiMocks.fetchDebugSession,
  fetchDebugHistorySession: apiMocks.fetchDebugHistorySession,
  fetchDebugProjection: apiMocks.fetchDebugProjection,
  fetchDebugEvents: apiMocks.fetchDebugEvents,
  postDebugPrepare: apiMocks.postDebugPrepare,
  postDebugStart: apiMocks.postDebugStart,
  postDebugParameterUnlock: apiMocks.postDebugParameterUnlock,
  postDebugSensitiveValuesReveal: apiMocks.postDebugSensitiveValuesReveal,
  postDebugContinue: apiMocks.postDebugContinue,
  postDebugStepOver: apiMocks.postDebugStepOver,
  postDebugStepInto: apiMocks.postDebugStepInto,
  postDebugStepOut: apiMocks.postDebugStepOut,
  postDebugPause: apiMocks.postDebugPause,
  postDebugAbort: apiMocks.postDebugAbort,
  postDebugVariablesApply: apiMocks.postDebugVariablesApply,
  postDebugNodeDebuggerApply: apiMocks.postDebugNodeDebuggerApply,
  fetchGraphDocument: apiMocks.fetchGraphDocument,
  putGraphDocument: apiMocks.putGraphDocument,
  postSourceProjection: apiMocks.postSourceProjection,
  fetchNodeDraft: apiMocks.fetchNodeDraft,
}))

function makeSummary(sessionId: string, status: string) {
  return {
    session_id: sessionId,
    status,
    graph_model_id: 'graph:workspace',
  }
}

function makeDetail(sessionId: string, status: string) {
  return {
    status,
    request: {},
    debug_session: {
      session_id: sessionId,
      status,
      resume_supported: false,
      breakpoint_slots: [],
      step_mode: null,
      paused_reason: null,
      pending_variable_overrides: {},
    },
    stage_timeline: [],
    object_index: { graph_model_id: 'graph:workspace', nodes: [], ports: [], edges: [] },
    diagnostic_links: [],
    runtime_preview: { current_node: { node_id: 'node-start' } },
    variable_snapshot: {},
  }
}

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('debugStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshSessions 遇到 preparing 活动会话时会自动水合 active/projection/events 并开始轮询', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-preparing-1', 'preparing')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: {
        debug_session_count: 1,
        debug_status_counts: { preparing: 1 },
      },
      sessions: [makeSummary('dbg-preparing-1', 'preparing')],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-preparing-1', 'preparing'))
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-preparing-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-preparing-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    await store.refreshSessions()

    expect(store.sessions[0].status).toBe('preparing')
    expect(store.historySessions[0].status).toBe('preparing')
    expect(store.historySummary?.debug_status_counts).toEqual({ preparing: 1 })
    expect(apiMocks.fetchDebugSession).toHaveBeenCalledWith('dbg-preparing-1')
    expect(apiMocks.fetchDebugProjection).toHaveBeenCalledWith('dbg-preparing-1', 'live')
    expect(apiMocks.fetchDebugEvents).toHaveBeenCalledWith('dbg-preparing-1')
    expect(store.activeSession?.debug_session.status).toBe('preparing')
    expect(store.pollingSessionId).toBe('dbg-preparing-1')
    store.stopPolling()
  })

  it('pollOnce 遇到 cancelled 终态会停止轮询、刷新历史并保留最终会话投影', async () => {
    apiMocks.fetchDebugSessions
      .mockResolvedValueOnce({ sessions: [makeSummary('dbg-cancelled-1', 'running')] })
      .mockResolvedValueOnce({ sessions: [] })
    apiMocks.fetchDebugHistorySessions
      .mockResolvedValueOnce({
        summary: { debug_session_count: 0, debug_status_counts: {} },
        sessions: [],
      })
      .mockResolvedValueOnce({
        summary: { debug_session_count: 1, debug_status_counts: { cancelled: 1 } },
        sessions: [makeSummary('dbg-cancelled-1', 'cancelled')],
      })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-cancelled-1', 'cancelled'))
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-cancelled-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-cancelled-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    await store.refreshSessions()
    expect(store.pollingSessionId).toBe('dbg-cancelled-1')

    await store.pollOnce('dbg-cancelled-1')

    expect(store.pollingSessionId).toBe(null)
    expect(store.sessions).toEqual([])
    expect(store.historySessions).toHaveLength(1)
    expect(store.historySessions[0].status).toBe('cancelled')
    expect(store.activeSession?.debug_session.status).toBe('cancelled')
    expect(store.projection?.mode).toBe('live')
    expect(apiMocks.fetchDebugHistorySessions).toHaveBeenCalledTimes(2)
  })

  it('hydrated active session 会驱动画布锁定', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-paused-1', 'paused')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 1, debug_status_counts: { paused: 1 } },
      sessions: [makeSummary('dbg-paused-1', 'paused')],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-paused-1', 'paused'))
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-paused-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: 'node-start',
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-paused-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })

    const [{ useDebugStore }, { useGraphWorkspaceStore }] = await Promise.all([
      import('./debugStore'),
      import('./graphWorkspaceStore'),
    ])
    const debugStore = useDebugStore()
    const graphWs = useGraphWorkspaceStore()

    expect(graphWs.isGraphEditable).toBe(true)

    await debugStore.refreshSessions()

    expect(debugStore.activeSession?.debug_session.status).toBe('paused')
    expect(graphWs.isGraphEditable).toBe(false)
    debugStore.stopPolling()
  })

  it('暂停态节点 debugger 更新只写活动 session 覆盖，不修改项目节点配置', async () => {
    const projectNodeConfig = {
      debugger: {
        breakpoint: { enabled: false, pause_timing: 'before' },
        record_frame: { enabled: false },
      },
    }
    apiMocks.postDebugNodeDebuggerApply.mockResolvedValue({
      ...makeDetail('dbg-hot-config-1', 'paused'),
      status: 'updated',
      node_id: 'node-next',
      debugger: {
        breakpoint: { enabled: true, pause_timing: 'before' },
        record_frame: { enabled: true },
      },
      runtime_plan: {
        executable_nodes: [{
          node_id: 'node-next',
          node_config: {
            debugger: {
              breakpoint: { enabled: true, pause_timing: 'before' },
              record_frame: { enabled: true },
            },
          },
        }],
      },
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    store.activeSession = makeDetail('dbg-hot-config-1', 'paused') as any

    await store.applyNodeDebuggerConfig('node-next', {
      breakpoint: { enabled: true, pause_timing: 'before' },
      record_frame: { enabled: true },
    })

    expect(apiMocks.postDebugNodeDebuggerApply).toHaveBeenCalledWith(
      'dbg-hot-config-1',
      'node-next',
      {
        breakpoint: { enabled: true, pause_timing: 'before' },
        record_frame: { enabled: true },
      },
    )
    expect(store.hasBreakpoint(projectNodeConfig, 'node-next')).toBe(true)
    expect(store.hasRecordFrame(projectNodeConfig, 'node-next')).toBe(true)
    expect(projectNodeConfig.debugger.breakpoint.enabled).toBe(false)
    expect(projectNodeConfig.debugger.record_frame.enabled).toBe(false)
  })

  it('切换到新 Debug session 时清理上一会话的临时节点配置', async () => {
    apiMocks.postDebugNodeDebuggerApply.mockResolvedValue({
      ...makeDetail('dbg-old', 'paused'),
      status: 'updated',
      node_id: 'node-next',
      debugger: { breakpoint: { enabled: true } },
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-new', 'paused'))

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    store.activeSession = makeDetail('dbg-old', 'paused') as any
    await store.applyNodeDebuggerConfig('node-next', { breakpoint: { enabled: true } })

    await store.loadActiveSession('dbg-new')

    expect(store.hasBreakpoint({}, 'node-next')).toBe(false)
  })

  it('Debug session 进入终态时清理临时节点配置', async () => {
    apiMocks.postDebugNodeDebuggerApply.mockResolvedValue({
      ...makeDetail('dbg-terminal', 'paused'),
      status: 'updated',
      node_id: 'node-next',
      debugger: { breakpoint: { enabled: true } },
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-terminal', 'completed'))

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    store.activeSession = makeDetail('dbg-terminal', 'paused') as any
    await store.applyNodeDebuggerConfig('node-next', { breakpoint: { enabled: true } })

    await store.loadActiveSession('dbg-terminal')

    expect(store.hasBreakpoint({}, 'node-next')).toBe(false)
  })

  it('重新水合暂停会话时从 runtime plan 恢复节点调试配置', async () => {
    apiMocks.fetchDebugSession.mockResolvedValue({
      ...makeDetail('dbg-rehydrate', 'paused'),
      runtime_plan: {
        executable_nodes: [{
          node_id: 'node-next',
          node_config: {
            debugger: {
              breakpoint: { enabled: true, pause_timing: 'after' },
              record_frame: { enabled: true },
            },
          },
        }],
      },
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    await store.loadActiveSession('dbg-rehydrate')

    expect(store.hasBreakpoint({}, 'node-next')).toBe(true)
    expect(store.hasRecordFrame({}, 'node-next')).toBe(true)
    expect(store.getEffectiveDebuggerConfig({}, 'node-next')).toMatchObject({
      breakpoint: { pause_timing: 'after' },
    })
  })

  it('prepareDebugSession 只执行预检，不创建或水合 debug session', async () => {
    apiMocks.postDebugPrepare.mockResolvedValue({
      status: 'ready',
      request: {},
      stage_timeline: [],
      object_index: null,
      diagnostic_links: [],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    const graphBody = { graph_document: { graph_model_id: 'graph:workspace' } }

    const result = await store.prepareDebugSession(graphBody)

    expect(apiMocks.postDebugPrepare).toHaveBeenCalledWith(graphBody)
    expect(result).toEqual({ phase: 'ready' })
    expect(apiMocks.fetchDebugSessions).not.toHaveBeenCalled()
    expect(apiMocks.fetchDebugSession).not.toHaveBeenCalled()
    expect(store.activeSession).toBeNull()
  })

  it('loadProjection 将历史事件索引传给 API，并记录事件所属会话', async () => {
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-history-1',
      source: 'history_store',
      projection: {
        mode: 'history',
        node_status_by_id: { 'node-a': 'completed' },
        active_paths: [],
      },
      variable_snapshot: { username: 'history-user' },
      runtime_preview: { current_node: { node_id: 'node-history' } },
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-history-1',
      source: 'history_store',
      total_count: 1,
      events: [{ event_id: 'evt-1', event_index: 7, event_kind: 'breakpoint.hit' }],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    await store.loadEvents('dbg-history-1')
    await store.loadProjection('dbg-history-1', 'history', 7)

    expect(store.eventsSessionId).toBe('dbg-history-1')
    expect(apiMocks.fetchDebugProjection).toHaveBeenCalledWith('dbg-history-1', 'history', 7)
    expect(store.projection?.mode).toBe('history')
    expect(store.projectionVariableSnapshot).toEqual({ username: 'history-user' })
    expect(store.projectionRuntimePreview).toEqual({ current_node: { node_id: 'node-history' } })
  })

  it('pollOnce 在历史查看期间保留历史投影，退出后恢复实时投影', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-history-live-1', 'running')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 1, debug_status_counts: { running: 1 } },
      sessions: [makeSummary('dbg-history-live-1', 'running')],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-history-live-1', 'running'))
    apiMocks.fetchDebugEvents.mockImplementation(async (sessionId: string) => ({
      session_id: sessionId,
      source: 'history_store',
      total_count: 1,
      events: [{
        event_id: sessionId === 'dbg-selected-history-1' ? 'evt-history' : 'evt-live',
        event_index: 7,
        event_kind: 'debug.paused',
      }],
    }))
    apiMocks.fetchDebugProjection.mockImplementation(async (_sessionId: string, mode: 'live' | 'history') => ({
      session_id: 'dbg-history-live-1',
      source: mode === 'history' ? 'history_store' : 'active_session',
      projection: {
        mode,
        node_status_by_id: mode === 'history' ? { 'node-history': 'paused' } : { 'node-live': 'running' },
        active_paths: [],
        paused_node_id: mode === 'history' ? 'node-history' : null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    }))

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    await store.loadEvents('dbg-selected-history-1')
    await store.loadProjection('dbg-history-live-1', 'history', 7)
    apiMocks.fetchDebugProjection.mockClear()

    await store.pollOnce('dbg-history-live-1')

    expect(apiMocks.fetchDebugProjection).not.toHaveBeenCalledWith('dbg-history-live-1', 'live')
    expect(store.projection?.mode).toBe('history')
    expect(store.eventsSessionId).toBe('dbg-selected-history-1')
    expect(store.events[0]?.event_id).toBe('evt-history')

    store.clearProjection()
    apiMocks.fetchDebugProjection.mockClear()
    await store.pollOnce('dbg-history-live-1')

    expect(apiMocks.fetchDebugProjection).toHaveBeenCalledWith('dbg-history-live-1', 'live')
    expect(store.projection?.mode).toBe('live')
    store.stopPolling()
  })

  it('pollOnce 同 session 并发调用时复用同一轮请求，不重复调用 active artifacts API', async () => {
    const detailDeferred = createDeferred<ReturnType<typeof makeDetail>>()
    const eventsDeferred = createDeferred<{
      session_id: string
      source: string
      total_count: number
      events: never[]
    }>()
    const projectionDeferred = createDeferred<{
      session_id: string
      source: string
      projection: {
        mode: 'live'
        node_status_by_id: Record<string, never>
        active_paths: never[]
        paused_node_id: null
        record_frame_node_ids: never[]
        skipped_node_ids: never[]
      }
    }>()
    apiMocks.fetchDebugSession.mockReturnValue(detailDeferred.promise)
    apiMocks.fetchDebugEvents.mockReturnValue(eventsDeferred.promise)
    apiMocks.fetchDebugProjection.mockReturnValue(projectionDeferred.promise)
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-concurrent-1', 'running')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 0, debug_status_counts: {} },
      sessions: [],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    const firstPoll = store.pollOnce('dbg-concurrent-1')
    const secondPoll = store.pollOnce('dbg-concurrent-1')

    await vi.advanceTimersByTimeAsync(10)

    expect(apiMocks.fetchDebugSession).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugEvents).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugProjection).toHaveBeenCalledTimes(1)

    detailDeferred.resolve(makeDetail('dbg-concurrent-1', 'running'))
    eventsDeferred.resolve({
      session_id: 'dbg-concurrent-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })
    projectionDeferred.resolve({
      session_id: 'dbg-concurrent-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })

    await Promise.all([firstPoll, secondPoll])
  })

  it('pollOnce 单轮 active poll 只请求 detail/events/projection，不刷新 sessions/history', async () => {
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-single-hydrate-1', 'running'))
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-single-hydrate-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-single-hydrate-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-single-hydrate-1', 'running')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 1, debug_status_counts: { running: 1 } },
      sessions: [makeSummary('dbg-single-hydrate-1', 'running')],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    await store.pollOnce('dbg-single-hydrate-1')

    expect(apiMocks.fetchDebugSession).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugEvents).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugProjection).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugSessions).not.toHaveBeenCalled()
    expect(apiMocks.fetchDebugHistorySessions).not.toHaveBeenCalled()
    store.stopPolling()
  })

  it('startPolling 同 session 重入时不重置已有 timer，且未完成前不会并发下一轮 poll', async () => {
    const detailDeferred = createDeferred<ReturnType<typeof makeDetail>>()
    apiMocks.fetchDebugSession.mockReturnValue(detailDeferred.promise)
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-timer-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-timer-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-timer-1', 'running')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 1, debug_status_counts: { running: 1 } },
      sessions: [makeSummary('dbg-timer-1', 'running')],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    store.startPolling('dbg-timer-1')
    store.startPolling('dbg-timer-1')
    await vi.advanceTimersByTimeAsync(400)
    await vi.advanceTimersByTimeAsync(1200)

    expect(apiMocks.fetchDebugSession).toHaveBeenCalledTimes(1)

    detailDeferred.resolve(makeDetail('dbg-timer-1', 'running'))
    await Promise.resolve()
    await Promise.resolve()

    store.stopPolling()
  })

  it('切换轮询 session 后丢弃旧 session 的迟到结果且不会停止新 session', async () => {
    const oldDetail = createDeferred<ReturnType<typeof makeDetail>>()
    const oldEvents = createDeferred<any>()
    const oldProjection = createDeferred<any>()
    apiMocks.fetchDebugSession.mockImplementation((sessionId: string) => (
      sessionId === 'dbg-old-1'
        ? oldDetail.promise
        : Promise.resolve(makeDetail('dbg-current-1', 'running'))
    ))
    apiMocks.fetchDebugEvents.mockImplementation((sessionId: string) => (
      sessionId === 'dbg-old-1'
        ? oldEvents.promise
        : Promise.resolve({
            session_id: 'dbg-current-1',
            source: 'history_store',
            total_count: 1,
            events: [{ event_id: 'current-event' }],
          })
    ))
    apiMocks.fetchDebugProjection.mockImplementation((sessionId: string) => (
      sessionId === 'dbg-old-1'
        ? oldProjection.promise
        : Promise.resolve({
            session_id: 'dbg-current-1',
            source: 'active_session',
            projection: {
              mode: 'live',
              node_status_by_id: {},
              active_paths: [],
              paused_node_id: null,
              record_frame_node_ids: [],
              skipped_node_ids: [],
            },
          })
    ))
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [makeSummary('dbg-current-1', 'running')],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 1, debug_status_counts: { running: 1 } },
      sessions: [makeSummary('dbg-current-1', 'running')],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()
    store.startPolling('dbg-old-1')
    const stalePoll = store.pollOnce('dbg-old-1')
    store.startPolling('dbg-current-1')
    await store.pollOnce('dbg-current-1')

    oldDetail.resolve(makeDetail('dbg-old-1', 'cancelled'))
    oldEvents.resolve({
      session_id: 'dbg-old-1',
      source: 'history_store',
      total_count: 1,
      events: [{ event_id: 'old-event' }],
    })
    oldProjection.resolve({
      session_id: 'dbg-old-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    await stalePoll

    expect(store.pollingSessionId).toBe('dbg-current-1')
    expect(store.activeSession?.debug_session?.session_id).toBe('dbg-current-1')
    expect(store.eventsSessionId).toBe('dbg-current-1')
    expect(store.events[0]?.event_id).toBe('current-event')
    store.stopPolling()
  })

  it('startDebugSession returns started and starts polling after successful hydration', async () => {
    apiMocks.postDebugStart.mockResolvedValue({
      status: 'started',
      request: {},
      debug_session: {
        session_id: 'dbg-started-1',
        status: 'running',
        resume_supported: false,
        breakpoint_slots: [],
      },
      stage_timeline: [],
      object_index: null,
      diagnostic_links: [],
      runtime_preview: { current_node: { node_id: 'node-start' } },
    })
    apiMocks.fetchDebugSessions.mockResolvedValue({ sessions: [makeSummary('dbg-started-1', 'running')] })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({ summary: { debug_session_count: 0, debug_status_counts: {} }, sessions: [] })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-started-1', 'running'))
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-started-1',
      source: 'active_session',
      projection: {
        mode: 'live',
        node_status_by_id: {},
        active_paths: [],
        paused_node_id: null,
        record_frame_node_ids: [],
        skipped_node_ids: [],
      },
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-started-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    const result = await store.startDebugSession({ graph_document: { graph_model_id: 'graph:workspace' } })

    expect(result).toEqual({ phase: 'started', sessionId: 'dbg-started-1' })
    expect(store.pollingSessionId).toBe('dbg-started-1')
    store.stopPolling()
  })

  it('startDebugSession returns started_with_sync_warning when projection hydration fails and prefers primary diagnostic message', async () => {
    apiMocks.postDebugStart.mockResolvedValue({
      status: 'started',
      request: {},
      debug_session: {
        session_id: 'dbg-syncwarn-1',
        status: 'running',
        resume_supported: false,
        breakpoint_slots: [],
      },
      stage_timeline: [],
      object_index: null,
      diagnostic_links: [],
      runtime_preview: { current_node: { node_id: 'node-start' } },
    })
    apiMocks.fetchDebugSessions.mockResolvedValue({ sessions: [makeSummary('dbg-syncwarn-1', 'running')] })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({ summary: { debug_session_count: 0, debug_status_counts: {} }, sessions: [] })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-syncwarn-1', 'running'))
    apiMocks.fetchDebugProjection.mockRejectedValue({
      body: {
        details: {
          primary_diagnostic: {
            message: 'projection backend unavailable',
          },
        },
      },
      message: 'HTTP 500',
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    const result = await store.startDebugSession({ graph_document: { graph_model_id: 'graph:workspace' } })

    expect(result).toEqual({
      phase: 'started_with_sync_warning',
      sessionId: 'dbg-syncwarn-1',
      syncError: 'projection backend unavailable',
    })
    expect(store.pollingSessionId).toBe(null)
  })

  it('图编译失败且未创建会话时写入返回的诊断并显示具体错误', async () => {
    apiMocks.postDebugStart.mockResolvedValue({
      status: 'failed',
      message: '图校验失败',
      request: {},
      stage_timeline: [],
      object_index: null,
      diagnostic_links: [
        {
          diagnostic_id: 'graph-edge-invalid',
          stage: 'validate',
          severity: 'error',
          category: 'graph.edge.relation_layer_mismatch',
          message: '边 edge-a 的 relation_layer 不匹配',
          object_ref: 'edge-a',
          graph_ref: { edge_id: 'edge-a' },
        },
      ],
    })

    const { useDebugStore } = await import('./debugStore')
    const { useProjectDiagnosticsStore } = await import('./projectDiagnosticsStore')
    const store = useDebugStore()

    const result = await store.startDebugSession({ graph_document: { graph_model_id: 'graph:workspace' } })

    expect(result).toEqual({
      phase: 'failed',
      startError: '图校验失败',
    })
    expect(useProjectDiagnosticsStore().visibleEntries).toEqual([
      expect.objectContaining({
        diagnostic_id: 'graph-edge-invalid',
        source: 'debug',
        operation: 'debug.start',
        object_ref: 'edge-a',
      }),
    ])
  })

  it('startDebugSession ignores parse.completed fallback text and prefers meaningful diagnostic link', async () => {
    apiMocks.postDebugStart.mockRejectedValue({
      body: {
        message: 'parsed source document',
        diagnostic_links: [
          {
            category: 'parse.completed',
            severity: 'info',
            message: 'parsed source document',
          },
          {
            category: 'graph.binding.invalid_reference',
            severity: 'error',
            message: 'binding failed on node-start',
          },
        ],
      },
      message: 'HTTP 400',
    })

    const { useDebugStore } = await import('./debugStore')
    const { useProjectDiagnosticsStore } = await import('./projectDiagnosticsStore')
    const store = useDebugStore()

    const result = await store.startDebugSession({ graph_document: { graph_model_id: 'graph:workspace' } })

    expect(result).toEqual({
      phase: 'failed',
      startError: 'binding failed on node-start',
    })
    expect(useProjectDiagnosticsStore().visibleEntries).toEqual([
      expect.objectContaining({
        category: 'graph.binding.invalid_reference',
        message: 'binding failed on node-start',
        source: 'debug',
        operation: 'debug.start',
      }),
    ])
  })

  it('startDebugSession 不把任意 completed 信息诊断当作启动错误', async () => {
    apiMocks.postDebugStart.mockRejectedValue({
      body: {
        message: 'validated bound source',
        diagnostic_links: [
          { category: 'parse.completed', severity: 'info', message: 'parsed source document' },
          { category: 'validate.completed', severity: 'info', message: 'validated bound source' },
          { category: 'emit.completed', severity: 'info', message: 'emitted graph model' },
        ],
      },
      message: 'HTTP 400',
    })

    const { useDebugStore } = await import('./debugStore')
    const store = useDebugStore()

    const result = await store.startDebugSession({ graph_document: { graph_model_id: 'graph:workspace' } })

    expect(result).toEqual({
      phase: 'failed',
      startError: 'HTTP 400',
    })
  })
})
