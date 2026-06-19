import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchRuntimeSessions: vi.fn(),
  fetchRuntimeSession: vi.fn(),
  fetchDebugSessions: vi.fn(),
  fetchDebugSession: vi.fn(),
  postRuntimeStart: vi.fn(),
  postRuntimeRun: vi.fn(),
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
    expect(store.activeRt?.status).toBe('completed')
    expect(store.runtimeProgress?.percent).toBe(100)
    expect(store.runtimeLiveStatus).toBe('completed')
    expect(MockEventSource.instances[0].closed).toBe(true)
  })
})
