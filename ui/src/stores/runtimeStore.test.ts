import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchRuntimeSessions: vi.fn(),
  fetchRuntimeSession: vi.fn(),
  fetchDebugSessions: vi.fn(),
  fetchDebugSession: vi.fn(),
  postRuntimeStart: vi.fn(),
  postRuntimeRun: vi.fn(),
  postRuntimeAbort: vi.fn(),
  fetchRuntimePendingInput: vi.fn(),
  getRuntimeStreamUrl: vi.fn((sessionId: string) => `/api/workbench/runtime/${sessionId}/stream`),
  buildRuntimeProgressFromSession: vi.fn((detail: any) => {
    const nodeStates = Array.isArray(detail?.node_states) ? detail.node_states : []
    const completed = nodeStates.filter((node: any) => node?.node_status === 'completed').length
    const failed = nodeStates.filter((node: any) => node?.node_status === 'failed').length
    const running = nodeStates.filter((node: any) => node?.node_status === 'running').length
    const pending = nodeStates.filter((node: any) => node?.node_status === 'pending').length
    return {
      session_id: detail?.runtime_session?.session_id ?? '',
      status: detail?.runtime_session?.status ?? detail?.status ?? 'idle',
      total_node_count: nodeStates.length,
      completed_node_count: completed,
      failed_node_count: failed,
      running_node_count: running,
      pending_node_count: pending,
      percent: nodeStates.length > 0 ? Number((((completed + failed) / nodeStates.length) * 100).toFixed(1)) : 0,
      event_count: Array.isArray(detail?.event_log) ? detail.event_log.length : 0,
    }
  }),
}))

vi.mock('@/services/api', () => ({
  fetchRuntimeSessions: apiMocks.fetchRuntimeSessions,
  fetchRuntimeSession: apiMocks.fetchRuntimeSession,
  fetchDebugSessions: apiMocks.fetchDebugSessions,
  fetchDebugSession: apiMocks.fetchDebugSession,
  postRuntimeStart: apiMocks.postRuntimeStart,
  postRuntimeRun: apiMocks.postRuntimeRun,
  postRuntimeAbort: apiMocks.postRuntimeAbort,
  fetchRuntimePendingInput: apiMocks.fetchRuntimePendingInput,
  getRuntimeStreamUrl: apiMocks.getRuntimeStreamUrl,
  buildRuntimeProgressFromSession: apiMocks.buildRuntimeProgressFromSession,
}))

type RuntimeStreamHandler = (event: MessageEvent) => void

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  readonly listeners = new Map<string, RuntimeStreamHandler[]>()
  onerror: ((event: Event) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(eventName: string, handler: RuntimeStreamHandler) {
    const handlers = this.listeners.get(eventName) ?? []
    handlers.push(handler)
    this.listeners.set(eventName, handlers)
  }

  removeEventListener(eventName: string, handler: RuntimeStreamHandler) {
    const handlers = this.listeners.get(eventName) ?? []
    this.listeners.set(
      eventName,
      handlers.filter((item) => item !== handler),
    )
  }

  close() {
    this.closed = true
  }

  emit(eventName: string, payload: unknown) {
    const handlers = this.listeners.get(eventName) ?? []
    const event = { data: JSON.stringify(payload) } as MessageEvent
    handlers.forEach((handler) => handler(event))
  }
}

describe('runtimeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    MockEventSource.instances = []
    vi.clearAllMocks()
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource)
    apiMocks.fetchRuntimeSessions.mockResolvedValue({ sessions: [] })
    apiMocks.fetchDebugSessions.mockResolvedValue({ sessions: [] })
    apiMocks.fetchRuntimePendingInput.mockResolvedValue({
      execution_id: null,
      request_id: null,
      status: 'none',
      fields: [],
      timeout_seconds: null,
    })
    apiMocks.fetchRuntimePendingInput.mockResolvedValue({
      execution_id: null,
      request_id: null,
      status: 'none',
      fields: [],
      timeout_seconds: null,
    })
  })

  it('hydrates a waiting input request when subscribing after the request event', async () => {
    apiMocks.fetchRuntimePendingInput.mockResolvedValue({
      execution_id: 'rt-pending-input',
      request_id: 'rt-pending-input:node-input:1',
      status: 'waiting',
      fields: [{ field_id: 'token', label: 'Token', value_type: 'string', sensitive: true, required: true }],
      timeout_seconds: 0,
    })

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    store.subscribeRuntimeSession('rt-pending-input')

    await vi.waitFor(() => {
      expect(store.pendingRuntimeInput).toMatchObject({
        execution_id: 'rt-pending-input',
        request_id: 'rt-pending-input:node-input:1',
        status: 'waiting',
      })
    })
  })

  it('hydrates a waiting input request when subscribing after the request event', async () => {
    apiMocks.fetchRuntimePendingInput.mockResolvedValue({
      execution_id: 'rt-pending-input',
      request_id: 'rt-pending-input:node-input:1',
      status: 'waiting',
      fields: [{ field_id: 'token', label: 'Token', value_type: 'string', sensitive: true, required: true }],
      timeout_seconds: 0,
    })

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    store.subscribeRuntimeSession('rt-pending-input')

    await vi.waitFor(() => {
      expect(store.pendingRuntimeInput).toMatchObject({
        execution_id: 'rt-pending-input',
        request_id: 'rt-pending-input:node-input:1',
        status: 'waiting',
      })
    })
  })

  it('subscribes to runtime SSE after accepted run and resolves on completed event', async () => {
    const startedSession = {
      status: 'started',
      request: { request_origin: 'memory_graph_document' },
      runtime_session: {
        session_id: 'rt-1',
        status: 'started',
        execution_supported: true,
      },
      runtime_plan: {
        graph_model_id: 'graph:workspace',
        compilation_id: 'comp-1',
        node_count: 2,
        edge_count: 1,
        start_node_ids: ['node-start'],
        terminal_node_ids: ['node-end'],
        executable_nodes: [],
        relation_edges: [],
        viewport: null,
      },
      node_states: [],
      event_log: [],
      result: null,
      diagnostics: { total_count: 0, highest_severity: null, entries: [] },
    }
    const acceptedSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: {
        ...startedSession.runtime_session,
        status: 'running',
      },
    }
    const completedSnapshot = {
      ...startedSession,
      status: 'completed',
      runtime_session: {
        ...startedSession.runtime_session,
        status: 'completed',
      },
      node_states: [
        { node_id: 'node-start', node_status: 'completed' },
        { node_id: 'node-end', node_status: 'completed' },
      ],
      event_log: [
        { event_kind: 'node.started', node_id: 'node-start' },
        { event_kind: 'node.completed', node_id: 'node-end' },
      ],
      execution_summary: {
        status: 'completed',
        completed_node_count: 2,
        failed_node_count: 0,
        event_count: 2,
        diagnostic_event_count: 0,
        node_status_counts: { completed: 2 },
        latest_event_kind: 'node.completed',
      },
      result: { status: 'completed', outputs: {} },
    }

    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockResolvedValue(acceptedSession)
    apiMocks.fetchRuntimeSession.mockResolvedValue(completedSnapshot)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()

    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => {
      expect(apiMocks.postRuntimeStart).toHaveBeenCalledTimes(1)
    })

    const earlyResult = await Promise.race([
      runPromise,
      new Promise<'pending'>((resolve) => setTimeout(() => resolve('pending'), 20)),
    ])

    expect(earlyResult).toBe('pending')
    expect(store.runtimeLiveStatus).toBe('connecting')

    await vi.waitFor(() => {
      expect(apiMocks.postRuntimeRun).toHaveBeenCalledTimes(1)
    })

    await vi.waitFor(() => {
      expect(MockEventSource.instances).toHaveLength(1)
    })
    expect(MockEventSource.instances[0].url).toBe('/api/workbench/runtime/rt-1/stream')

    MockEventSource.instances[0].emit('runtime.summary', {
      session_id: 'rt-1',
      status: 'running',
      total_node_count: 2,
      completed_node_count: 1,
      failed_node_count: 0,
      running_node_count: 1,
      pending_node_count: 0,
      percent: 50,
      event_count: 1,
    })

    expect(store.runtimeProgress?.percent).toBe(50)
    expect(store.runtimeLiveStatus).toBe('streaming')
    expect(store.runtimeLiveConnected).toBe(true)

    MockEventSource.instances[0].emit('runtime.completed', completedSnapshot)

    const result = await runPromise

    expect(result).toEqual({ success: true, message: '2 节点完成' })
    expect(apiMocks.fetchRuntimeSession).toHaveBeenCalledWith('rt-1')
    expect(store.activeRt?.status).toBe('completed')
    expect(store.runtimeProgress?.percent).toBe(100)
    expect(store.runtimeLiveStatus).toBe('completed')
    expect(MockEventSource.instances[0].closed).toBe(true)
  })

  it('resolves a run from the nested terminal status after the SSE connection closes', async () => {
    const startedSession = {
      status: 'started',
      request: {},
      runtime_session: { session_id: 'rt-eof-1', status: 'ready', execution_supported: true },
      runtime_plan: null,
      node_states: [],
      event_log: [],
      result: null,
    }
    const acceptedSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: { ...startedSession.runtime_session, status: 'running' },
    }
    const completedDetail = {
      request: {},
      runtime_session: { ...startedSession.runtime_session, status: 'completed' },
      runtime_plan: null,
      node_states: [
        { node_id: 'node-start', node_status: 'completed' },
        { node_id: 'node-end', node_status: 'completed' },
      ],
      event_log: [{ event_kind: 'session.completed' }],
      result: { status: 'succeeded' },
    }
    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockResolvedValue(acceptedSession)
    apiMocks.fetchRuntimeSession.mockResolvedValue(completedDetail)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    await vi.waitFor(() => expect(apiMocks.postRuntimeRun).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await MockEventSource.instances[0].onerror?.(new Event('error'))

    const result = await Promise.race([
      runPromise,
      new Promise<'timeout'>((resolve) => setTimeout(() => resolve('timeout'), 50)),
    ])

    expect(result).toEqual({ success: true, message: '2 节点完成' })
    expect(store.activeRt?.runtime_session.status).toBe('completed')
    expect(store.runtimeLiveStatus).toBe('completed')
  })

  it('keeps a run pending when the stream disconnects before the backend reaches a terminal state', async () => {
    const startedSession = {
      status: 'started', request: {},
      runtime_session: { session_id: 'rt-reconnect-1', status: 'ready', execution_supported: true },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    }
    const runningSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: { ...startedSession.runtime_session, status: 'running' },
    }
    const completedSnapshot = {
      ...runningSession,
      status: 'completed',
      session_id: 'rt-reconnect-1',
      runtime_session: { ...runningSession.runtime_session, status: 'completed' },
      node_states: [{ node_id: 'node-a', node_status: 'completed' }],
      result: { status: 'succeeded' },
    }
    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockResolvedValue(runningSession)
    apiMocks.fetchRuntimeSession.mockResolvedValue(runningSession)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    await MockEventSource.instances[0].onerror?.(new Event('error'))

    const disconnectedResult = await Promise.race([
      runPromise,
      new Promise<'pending'>((resolve) => setTimeout(() => resolve('pending'), 30)),
    ])
    expect(disconnectedResult).toBe('pending')
    expect(store.runtimeLiveStatus).toBe('disconnected')

    apiMocks.fetchRuntimeSession.mockResolvedValue(completedSnapshot)
    MockEventSource.instances[0].emit('runtime.completed', completedSnapshot)
    await expect(runPromise).resolves.toEqual({ success: true, message: '1 节点完成' })
  })

  it('reconciles a stale local failed status with the completed backend detail', async () => {
    const startedSession = {
      status: 'started', request: {},
      runtime_session: { session_id: 'rt-stale-failed', status: 'ready', execution_supported: true },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    }
    const runningSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: { ...startedSession.runtime_session, status: 'running' },
    }
    const completedDetail = {
      request: {},
      runtime_session: { ...runningSession.runtime_session, status: 'completed' },
      runtime_plan: null,
      node_states: [{ node_id: 'node-a', node_status: 'completed' }],
      event_log: [{ event_kind: 'session.completed' }],
      result: { status: 'succeeded' },
    }
    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockResolvedValue(runningSession)
    apiMocks.fetchRuntimeSession.mockResolvedValue(completedDetail)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    MockEventSource.instances[0].emit('runtime.summary', {
      session_id: 'rt-stale-failed', status: 'failed', total_node_count: 1,
      completed_node_count: 0, failed_node_count: 1, running_node_count: 0,
      pending_node_count: 0, percent: 100, event_count: 1,
    })
    await MockEventSource.instances[0].onerror?.(new Event('error'))

    await expect(runPromise).resolves.toEqual({ success: true, message: '1 节点完成' })
    expect(store.runtimeLiveStatus).toBe('completed')
    expect(store.activeRt?.runtime_session.status).toBe('completed')
  })

  it('uses the backend detail instead of a failed terminal SSE payload', async () => {
    const startedSession = {
      status: 'started', request: {},
      runtime_session: { session_id: 'rt-terminal-authority', status: 'ready', execution_supported: true },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    }
    const runningSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: { ...startedSession.runtime_session, status: 'running' },
    }
    const completedDetail = {
      request: {},
      runtime_session: { ...runningSession.runtime_session, status: 'completed' },
      runtime_plan: null,
      node_states: [{ node_id: 'node-a', node_status: 'completed' }],
      event_log: [{ event_kind: 'session.completed' }],
      result: { status: 'succeeded' },
    }
    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockResolvedValue(runningSession)
    apiMocks.fetchRuntimeSession.mockResolvedValue(completedDetail)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    MockEventSource.instances[0].emit('runtime.failed', {
      status: 'failed', session_id: 'rt-terminal-authority', request: {},
      runtime_session: { ...runningSession.runtime_session, status: 'failed' },
      runtime_plan: null,
      node_states: [{ node_id: 'node-a', node_status: 'failed' }],
      event_log: [{ event_kind: 'session.failed' }],
      result: { status: 'failed', failure_reason: 'stale-stream-payload' },
    })

    await expect(runPromise).resolves.toEqual({ success: true, message: '1 节点完成' })
    expect(apiMocks.fetchRuntimeSession).toHaveBeenCalledWith('rt-terminal-authority')
    expect(store.runtimeLiveStatus).toBe('completed')
  })

  it('locks runtime commands while the start request is in flight', async () => {
    let resolveStart!: (value: unknown) => void
    apiMocks.postRuntimeStart.mockReturnValue(new Promise((resolve) => { resolveStart = resolve }))

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    void store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    expect(store.isRunStarting).toBe(true)
    expect(store.canAbortRuntime).toBe(false)
    const duplicate = await store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    expect(duplicate).toEqual({ success: false, message: '运行正在启动，请稍候' })
    expect(apiMocks.postRuntimeStart).toHaveBeenCalledTimes(1)
    expect(apiMocks.postRuntimeAbort).not.toHaveBeenCalled()
    resolveStart({
      status: 'diagnostic_blocked', request: {},
      runtime_session: { session_id: null, status: 'failed', execution_supported: false },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    })
  })

  it('retains a backend terminal result that arrives before the run response', async () => {
    const startedSession = {
      status: 'started', request: {},
      runtime_session: { session_id: 'rt-early-terminal', status: 'ready', execution_supported: true },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    }
    const runningSession = {
      ...startedSession,
      status: 'accepted',
      runtime_session: { ...startedSession.runtime_session, status: 'running' },
    }
    const completedDetail = {
      request: {},
      runtime_session: { ...runningSession.runtime_session, status: 'completed' },
      runtime_plan: null,
      node_states: [{ node_id: 'node-a', node_status: 'completed' }],
      event_log: [{ event_kind: 'session.completed' }],
      result: { status: 'succeeded' },
    }
    let resolveRun!: (value: unknown) => void
    apiMocks.postRuntimeStart.mockResolvedValue(startedSession)
    apiMocks.postRuntimeRun.mockReturnValue(new Promise((resolve) => { resolveRun = resolve }))
    apiMocks.fetchRuntimeSession.mockResolvedValue(completedDetail)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    const runPromise = store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    await vi.waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    MockEventSource.instances[0].emit('runtime.completed', {
      ...completedDetail,
      session_id: 'rt-early-terminal',
      status: 'completed',
    })
    await vi.waitFor(() => expect(apiMocks.fetchRuntimeSession).toHaveBeenCalledWith('rt-early-terminal'))
    resolveRun(runningSession)

    const result = await Promise.race([
      runPromise,
      new Promise<'timeout'>((resolve) => setTimeout(() => resolve('timeout'), 50)),
    ])
    expect(result).toEqual({ success: true, message: '1 节点完成' })
  })

  it('ignores terminal events emitted by a superseded runtime stream', async () => {
    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()

    store.subscribeRuntimeSession('rt-old')
    store.subscribeRuntimeSession('rt-current')
    const [oldStream, currentStream] = MockEventSource.instances

    oldStream.emit('runtime.failed', {
      status: 'failed',
      session_id: 'rt-old',
      request: {},
      runtime_session: { session_id: 'rt-old', status: 'failed', execution_supported: true },
      runtime_plan: null,
      node_states: [{ node_id: 'node-old', node_status: 'failed' }],
      event_log: [{ event_kind: 'session.failed' }],
      result: { status: 'failed' },
    })

    expect(store.runtimeLiveStatus).toBe('connecting')
    expect(store.activeRt).toBeNull()
    expect(currentStream.closed).toBe(false)
  })

  it('aborts the active runtime session and exposes stable active states', async () => {
    const runningSession = {
      status: 'accepted',
      request: {},
      runtime_session: { session_id: 'rt-abort-1', status: 'running', execution_supported: true },
      runtime_plan: null,
      node_states: [{ node_id: 'node-a', node_status: 'running' }],
      event_log: [],
      result: null,
    }
    const abortedSession = {
      ...runningSession,
      status: 'aborted',
      runtime_session: {
        ...runningSession.runtime_session,
        status: 'aborted',
        abort_reason: 'user_abort',
        aborted_at: '2026-07-11T00:00:00+00:00',
      },
      node_states: [{ node_id: 'node-a', node_status: 'aborted' }],
    }
    apiMocks.postRuntimeAbort.mockResolvedValue(abortedSession)

    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    store.setActiveRt(runningSession as any)

    expect(store.isRuntimeActive).toBe(true)
    expect(store.canAbortRuntime).toBe(true)

    const result = await store.abortActiveRun()

    expect(apiMocks.postRuntimeAbort).toHaveBeenCalledWith('rt-abort-1', 'user_abort')
    expect(result).toEqual({ success: true, message: '运行已终止' })
    expect(store.runtimeLiveStatus).toBe('aborted')
    expect(store.isRuntimeActive).toBe(false)
    expect(store.canAbortRuntime).toBe(false)
  })

  it('rejects duplicate start while a runtime session is active', async () => {
    const { useRuntimeStore } = await import('./runtimeStore')
    const store = useRuntimeStore()
    store.setActiveRt({
      status: 'accepted', request: {},
      runtime_session: { session_id: 'rt-active', status: 'running', execution_supported: true },
      runtime_plan: null, node_states: [], event_log: [], result: null,
    } as any)

    const result = await store.startAndRun({ graph_model_id: 'graph:workspace' }, true)

    expect(result.success).toBe(false)
    expect(result.message).toContain('已有运行中的任务')
    expect(apiMocks.postRuntimeStart).not.toHaveBeenCalled()
  })
})
