import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchDebugSessionNetworkSummary: vi.fn(),
  fetchDebugSessionNetwork: vi.fn(),
  fetchDebugSessionNetworkTrace: vi.fn(),
  fetchDebugSessionNetworkTraceBody: vi.fn(),
  fetchDebugHistorySessionNetworkSummary: vi.fn(),
  fetchDebugHistorySessionNetwork: vi.fn(),
  fetchDebugHistorySessionNetworkTrace: vi.fn(),
  fetchDebugHistorySessionNetworkTraceBody: vi.fn(),
}))

vi.mock('@/services/api', async () => {
  const actual = await vi.importActual<typeof import('@/services/api')>('@/services/api')
  return {
    ...actual,
    fetchDebugSessionNetworkSummary: apiMocks.fetchDebugSessionNetworkSummary,
    fetchDebugSessionNetwork: apiMocks.fetchDebugSessionNetwork,
    fetchDebugSessionNetworkTrace: apiMocks.fetchDebugSessionNetworkTrace,
    fetchDebugSessionNetworkTraceBody: apiMocks.fetchDebugSessionNetworkTraceBody,
    fetchDebugHistorySessionNetworkSummary: apiMocks.fetchDebugHistorySessionNetworkSummary,
    fetchDebugHistorySessionNetwork: apiMocks.fetchDebugHistorySessionNetwork,
    fetchDebugHistorySessionNetworkTrace: apiMocks.fetchDebugHistorySessionNetworkTrace,
    fetchDebugHistorySessionNetworkTraceBody: apiMocks.fetchDebugHistorySessionNetworkTraceBody,
  }
})

const navigationMocks = vi.hoisted(() => ({
  locateGraphNode: vi.fn(),
}))

vi.mock('@/services/graphNodeNavigation', () => navigationMocks)

const dockMocks = vi.hoisted(() => ({
  restorePanel: vi.fn(),
  activatePanel: vi.fn(),
}))

vi.mock('@/stores/dockStore', () => ({
  useDockStore: () => dockMocks,
}))

import DebugNetworkPanel from './DebugNetworkPanel.vue'
import { useDebugStore } from '@/stores/debugStore'

function makeLiveTrace(traceId: string, status: string, url: string) {
  return {
    trace_id: traceId,
    debug_session_id: 'dbg-1',
    runtime_session_id: 'dbg-1',
    node_id: 'node-http',
    operation_id: 'network.http_request',
    started_at: '2026-08-29T10:00:00Z',
    ended_at: '2026-08-29T10:00:01Z',
    duration_ms: 12.3,
    status,
    error_code: null,
    debug_event_index: null,
    operation: {
      trace_id: traceId,
      debug_session_id: 'dbg-1',
      runtime_session_id: 'dbg-1',
      node_id: 'node-http',
      operation_id: 'network.http_request',
      started_at: '2026-08-29T10:00:00Z',
      ended_at: '2026-08-29T10:00:01Z',
      duration_ms: 12.3,
      status,
      error_code: null,
      method: 'POST',
      url,
      request_headers: { 'content-type': 'application/json' },
      request_query: {},
      request_body: null,
      response_status: 200,
      response_headers: { 'content-type': 'application/json' },
      response_body: null,
      retry_attempt: 0,
    },
    connections: [],
    messages: [],
  }
}

function makeSummary(totalOperations: number) {
  return {
    total_operations: totalOperations,
    successful_operations: totalOperations,
    failed_operations: 0,
    cancelled_operations: 0,
    active_connections: 0,
    queue_depth: 0,
    reconnect_count: 0,
    dropped_count: 0,
    recent_errors: [],
  }
}

describe('DebugNetworkPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    apiMocks.fetchDebugSessionNetworkSummary.mockResolvedValue({ summary: makeSummary(2) })
    apiMocks.fetchDebugSessionNetwork.mockResolvedValue({
      summary: makeSummary(2),
      traces: [
        makeLiveTrace('trace-1', 'succeeded', 'https://example.test/api'),
        makeLiveTrace('trace-2', 'failed', 'https://example.test/socket'),
      ],
    })
    apiMocks.fetchDebugSessionNetworkTrace.mockResolvedValue({
      trace: {
        ...makeLiveTrace('trace-1', 'succeeded', 'https://example.test/api'),
        messages: [{ event_kind: 'sse.message', sequence_id: 1, connection_id: 'conn-1' }],
      },
    })
    apiMocks.fetchDebugSessionNetworkTraceBody.mockResolvedValue({
      request_body: { encoding: 'text', value: '{"name":"item"}', text: '{"name":"item"}' },
      response_body: { encoding: 'text', value: '{"created":true}', text: '{"created":true}' },
      messages: [{ event_kind: 'sse.message', sequence_id: 1, connection_id: 'conn-1', payload: 'stream-event' }],
    })
    apiMocks.fetchDebugHistorySessionNetworkSummary.mockResolvedValue({ summary: makeSummary(1) })
    apiMocks.fetchDebugHistorySessionNetwork.mockResolvedValue({
      summary: makeSummary(1),
      traces: [makeLiveTrace('trace-h-1', 'succeeded', 'https://history.example.test/api')],
    })
    apiMocks.fetchDebugHistorySessionNetworkTrace.mockResolvedValue({
      trace: makeLiveTrace('trace-h-1', 'succeeded', 'https://history.example.test/api'),
    })
    apiMocks.fetchDebugHistorySessionNetworkTraceBody.mockResolvedValue({
      request_body: { encoding: 'text', value: '{"history":true}', text: '{"history":true}' },
      response_body: { encoding: 'text', value: '{"ok":true}', text: '{"ok":true}' },
    })
  })

  it('history 模式请求 history network API', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = { debug_session: { session_id: 'dbg-live-1', status: 'paused' } } as any
    store.activeHistorySession = { session_id: 'dbg-history-1', session: {} } as any
    store.projection = { mode: 'history', node_status_by_id: {}, active_paths: [] } as any

    mount(DebugNetworkPanel, {
      global: { plugins: [pinia] },
    })
    await nextTick()
    await nextTick()

    expect(apiMocks.fetchDebugHistorySessionNetworkSummary).toHaveBeenCalledWith('dbg-history-1')
    expect(apiMocks.fetchDebugHistorySessionNetwork).toHaveBeenCalledWith('dbg-history-1')
    expect(apiMocks.fetchDebugSessionNetworkSummary).not.toHaveBeenCalled()
    expect(apiMocks.fetchDebugSessionNetwork).not.toHaveBeenCalled()
  })

  it('历史投影但没有 activeHistorySession 时仍使用 activeSession 的会话 ID 读取历史网络', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = { debug_session: { session_id: 'dbg-live-1', status: 'paused' } } as any
    store.activeHistorySession = null
    store.projection = { mode: 'history', node_status_by_id: {}, active_paths: [] } as any

    mount(DebugNetworkPanel, {
      global: { plugins: [pinia] },
    })
    await nextTick()
    await nextTick()

    expect(apiMocks.fetchDebugHistorySessionNetworkSummary).toHaveBeenCalledWith('dbg-live-1')
    expect(apiMocks.fetchDebugHistorySessionNetwork).toHaveBeenCalledWith('dbg-live-1')
    expect(apiMocks.fetchDebugSessionNetworkSummary).not.toHaveBeenCalled()
    expect(apiMocks.fetchDebugSessionNetwork).not.toHaveBeenCalled()
  })

  it('live 模式跟随 debugStore 轮询快照增量刷新', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-1'],
        traces: { 'trace-1': makeLiveTrace('trace-1', 'succeeded', 'https://example.test/api') },
        summary: makeSummary(1),
      },
    } as any

    const wrapper = mount(DebugNetworkPanel, {
      global: { plugins: [pinia] },
    })
    await nextTick()

    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(1)
    expect(apiMocks.fetchDebugSessionNetworkSummary).not.toHaveBeenCalled()
    expect(apiMocks.fetchDebugSessionNetwork).not.toHaveBeenCalled()

    store.activeSession = {
      ...store.activeSession,
      network_trace_snapshot: {
        trace_order: ['trace-1', 'trace-2'],
        traces: {
          'trace-1': makeLiveTrace('trace-1', 'succeeded', 'https://example.test/api'),
          'trace-2': makeLiveTrace('trace-2', 'succeeded', 'https://example.test/next'),
        },
        summary: makeSummary(2),
      },
    } as any
    await nextTick()

    const rows = wrapper.findAll('[data-trace-id]')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('操作 2')
  })

  it('live 模式在同一条记录的队列状态变化时刷新', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    const firstTrace = makeLiveTrace('trace-1', 'running', 'https://example.test/stream')
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-1'],
        traces: { 'trace-1': { ...firstTrace, connections: [{ connection_id: 'conn-1', connection_state: 'connected', queue_depth: 0 }] } },
        summary: { ...makeSummary(1), queue_depth: 0 },
      },
    } as any

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    expect(wrapper.text()).toContain('队列 0')

    const secondTrace = makeLiveTrace('trace-1', 'running', 'https://example.test/stream')
    store.activeSession = {
      ...store.activeSession,
      network_trace_snapshot: {
        trace_order: ['trace-1'],
        traces: { 'trace-1': { ...secondTrace, connections: [{ connection_id: 'conn-1', connection_state: 'connected', queue_depth: 3 }] } },
        summary: { ...makeSummary(1), queue_depth: 3 },
      },
    } as any
    await nextTick()

    expect(wrapper.text()).toContain('队列 3')
  })

  it('切换 Debug 会话后清空上一会话的详情和正文', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    const traceA = makeLiveTrace('trace-a', 'succeeded', 'https://a.example.test/items')
    const traceB = makeLiveTrace('trace-b', 'succeeded', 'https://b.example.test/items')
    store.activeSession = {
      debug_session: { session_id: 'dbg-a', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-a'],
        traces: { 'trace-a': traceA },
        summary: makeSummary(1),
      },
    } as any

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await wrapper.get('[data-trace-id="trace-a"]').trigger('click')
    await wrapper.get('[data-action="toggle-request-body"]').trigger('click')
    expect(wrapper.get('[data-testid="trace-request-body"]').text()).toContain('name')

    store.activeSession = {
      debug_session: { session_id: 'dbg-b', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-b'],
        traces: { 'trace-b': traceB },
        summary: makeSummary(1),
      },
    } as any
    await nextTick()
    await nextTick()

    expect(wrapper.find('[data-testid="trace-request-body"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('选择网络记录查看详情')
  })

  it('live 模式在同长度错误内容变化时刷新', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    const trace = makeLiveTrace('trace-error-live', 'failed', 'https://example.test/error')
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-error-live'],
        traces: { 'trace-error-live': trace },
        summary: {
          ...makeSummary(1),
          failed_operations: 1,
          recent_errors: [{ trace_id: 'trace-error-live', error_code: 'network.timeout' }],
        },
      },
    } as any
    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    expect(wrapper.text()).toContain('network.timeout')

    store.activeSession = {
      ...store.activeSession,
      network_trace_snapshot: {
        trace_order: ['trace-error-live'],
        traces: { 'trace-error-live': trace },
        summary: {
          ...makeSummary(1),
          failed_operations: 1,
          recent_errors: [{ trace_id: 'trace-error-live', error_code: 'network.connection_reset' }],
        },
      },
    } as any
    await nextTick()
    expect(wrapper.text()).toContain('network.connection_reset')
  })

  it('live 模式在同长度消息内容变化时刷新', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    const firstTrace: any = makeLiveTrace('trace-message-live', 'running', 'https://example.test/stream')
    firstTrace.messages = [{
      event_kind: 'sse.message.first',
      sequence_id: 1,
      connection_epoch: 1,
      recorded_at: '2026-08-29T10:00:01Z',
    }]
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-message-live'],
        traces: { 'trace-message-live': firstTrace },
        summary: makeSummary(1),
      },
    } as any
    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    expect(wrapper.text()).toContain('sse.message.first')

    const secondTrace: any = makeLiveTrace('trace-message-live', 'running', 'https://example.test/stream')
    secondTrace.messages = [{
      event_kind: 'sse.message.updated',
      sequence_id: 1,
      connection_epoch: 1,
      recorded_at: '2026-08-29T10:00:01Z',
    }]
    store.activeSession = {
      ...store.activeSession,
      network_trace_snapshot: {
        trace_order: ['trace-message-live'],
        traces: { 'trace-message-live': secondTrace },
        summary: makeSummary(1),
      },
    } as any
    await nextTick()
    expect(wrapper.text()).toContain('sse.message.updated')
  })

  it('动态消息正文默认折叠并按需读取', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any

    const wrapper = mount(DebugNetworkPanel, {
      global: { plugins: [pinia] },
    })
    await nextTick()
    await nextTick()

    await wrapper.get('[data-trace-id="trace-1"]').trigger('click')
    expect(wrapper.find('[data-testid="trace-message-body"]').exists()).toBe(false)

    await wrapper.get('[data-action="toggle-messages"]').trigger('click')
    expect(apiMocks.fetchDebugSessionNetworkTraceBody).toHaveBeenCalledWith('dbg-1', 'trace-1', 'messages')
    expect(wrapper.get('[data-testid="trace-message-body"]').text()).toContain('stream-event')
  })

  it('请求体和响应体分别按需读取，不互相预取', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any

    apiMocks.fetchDebugSessionNetworkTraceBody
      .mockResolvedValueOnce({
        request_body: { encoding: 'text', value: 'request-only' },
      })
      .mockResolvedValueOnce({
        response_body: { encoding: 'text', value: 'response-only' },
      })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    await wrapper.get('[data-trace-id="trace-1"]').trigger('click')

    await wrapper.get('[data-action="toggle-request-body"]').trigger('click')
    expect(apiMocks.fetchDebugSessionNetworkTraceBody).toHaveBeenLastCalledWith('dbg-1', 'trace-1', 'request')
    expect(wrapper.get('[data-testid="trace-request-body"]').text()).toContain('request-only')

    await wrapper.get('[data-action="toggle-response-body"]').trigger('click')
    expect(apiMocks.fetchDebugSessionNetworkTraceBody).toHaveBeenLastCalledWith('dbg-1', 'trace-1', 'response')
    expect(wrapper.get('[data-testid="trace-response-body"]').text()).toContain('response-only')
  })

  it('支持节点、操作、连接、epoch、序号和事件类型筛选', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any

    const trace: any = makeLiveTrace('trace-1', 'running', 'https://example.test/stream')
    trace.connections = [{
      connection_id: 'conn-1',
      connection_epoch: 3,
      connection_state: 'connected',
      protocol: 'sse',
    }]
    trace.messages = [{
      event_kind: 'sse.message',
      connection_id: 'conn-1',
      sequence_id: 7,
      connection_epoch: 3,
    }]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(1),
      traces: [trace],
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()

    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(3)
    await wrapper.get('[data-testid="network-node-filter"]').setValue('node-http')
    await wrapper.get('[data-testid="network-operation-filter"]').setValue('network.http_request')
    await wrapper.get('[data-testid="network-connection-filter"]').setValue('conn-1')
    await wrapper.get('[data-testid="network-epoch-filter"]').setValue('3')
    await wrapper.get('[data-testid="network-sequence-filter"]').setValue('7')
    await wrapper.get('[data-testid="network-event-kind-filter"]').setValue('sse.message')

    const rows = wrapper.findAll('[data-trace-id]')
    expect(rows).toHaveLength(1)
    expect(rows[0].attributes('data-trace-id')).toBe('trace-1')
    expect(rows[0].text()).toContain('sse.message')
  })

  it('支持仅错误、活跃连接和执行激活事件筛选', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any

    const failed = makeLiveTrace('trace-failed', 'failed', 'https://example.test/fail')
    const active: any = makeLiveTrace('trace-active', 'running', 'https://example.test/active')
    active.connections = [{ connection_id: 'conn-active', connection_state: 'connected', protocol: 'websocket' }]
    active.messages = [{ event_kind: 'execution.activation', connection_id: 'conn-active', sequence_id: 2 }]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(2),
      traces: [failed, active],
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()

    await wrapper.get('[data-testid="network-only-errors"]').setValue(true)
    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(1)
    expect(wrapper.get('[data-trace-id="trace-failed"]')).toBeTruthy()

    await wrapper.get('[data-testid="network-only-errors"]').setValue(false)
    await wrapper.get('[data-testid="network-only-active"]').setValue(true)
    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(1)
    expect(wrapper.get('[data-trace-id="trace-active"]')).toBeTruthy()

    await wrapper.get('[data-testid="network-only-active"]').setValue(false)
    await wrapper.get('[data-testid="network-only-activation"]').setValue(true)
    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(1)
    expect(wrapper.get('[data-trace-id="trace-active"]')).toBeTruthy()
  })

  it('支持按连接状态筛选网络记录', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const trace: any = makeLiveTrace('trace-connected', 'succeeded', 'https://example.test/stream')
    trace.connections = [{
      connection_id: 'conn-connected',
      connection_state: 'connected',
      protocol: 'sse',
    }]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(1),
      traces: [trace],
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()

    await wrapper.get('[data-testid="network-status-filter"]').setValue('connected')
    const rows = wrapper.findAll('[data-trace-id]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('connected')
  })

  it('展示队列丢弃事件摘要并在实时快照变化时刷新', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    const firstSummary = {
      ...makeSummary(1),
      dropped_count: 1,
      queue_events: [{ event_kind: 'network.queue_message_dropped', dropped_count: 1 }],
    }
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
      network_trace_snapshot: {
        trace_order: ['trace-1'],
        traces: { 'trace-1': makeLiveTrace('trace-1', 'running', 'https://example.test/stream') },
        summary: firstSummary,
      },
    } as any

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    expect(wrapper.text()).toContain('丢弃 1')
    expect(wrapper.text()).toContain('队列事件 1')

    store.activeSession = {
      ...store.activeSession,
      network_trace_snapshot: {
        trace_order: ['trace-1'],
        traces: { 'trace-1': makeLiveTrace('trace-1', 'running', 'https://example.test/stream') },
        summary: {
          ...firstSummary,
          queue_events: [
            ...firstSummary.queue_events,
            { event_kind: 'network.queue_message_dropped', dropped_count: 1 },
          ],
        },
      },
    } as any
    await nextTick()
    expect(wrapper.text()).toContain('队列事件 2')
  })

  it('详情可将网络记录定位到图节点', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    await wrapper.get('[data-trace-id="trace-1"]').trigger('click')
    await wrapper.get('[data-action="locate-network-node"]').trigger('click')

    expect(navigationMocks.locateGraphNode).toHaveBeenCalledWith('node-http')
  })

  it('详情可反向定位关联 Debug 事件', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const trace: any = makeLiveTrace('trace-debug-event', 'succeeded', 'https://example.test/event')
    trace.debug_event_index = 7
    trace.operation.debug_event_index = 7
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({ summary: makeSummary(1), traces: [trace] })
    apiMocks.fetchDebugSessionNetworkTrace.mockResolvedValueOnce({ trace })
    store.loadProjection = vi.fn().mockResolvedValue(undefined)

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    await wrapper.get('[data-trace-id="trace-debug-event"]').trigger('click')
    await wrapper.get('[data-action="locate-debug-event"]').trigger('click')

    expect(store.loadProjection).toHaveBeenCalledWith('dbg-1', 'history', 7)
    expect(dockMocks.restorePanel).toHaveBeenCalledWith('debugTimeline')
    expect(dockMocks.activatePanel).toHaveBeenCalledWith('debugTimeline')
  })

  it('点击同一 Trace 的具体消息行后定位该消息的 Debug 事件', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const trace: any = makeLiveTrace('trace-message-rows', 'succeeded', 'https://example.test/stream')
    trace.debug_event_index = null
    trace.operation.debug_event_index = null
    trace.messages = [
      {
        event_kind: 'sse.message',
        connection_id: 'conn-1',
        sequence_id: 1,
        debug_event_index: 2,
        payload: 'first',
      },
      {
        event_kind: 'sse.message',
        connection_id: 'conn-1',
        sequence_id: 2,
        debug_event_index: 9,
        payload: 'second',
      },
    ]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(1),
      traces: [trace],
    })
    apiMocks.fetchDebugSessionNetworkTrace.mockResolvedValueOnce({ trace })
    store.loadProjection = vi.fn().mockResolvedValue(undefined)

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    const rows = wrapper.findAll('[data-trace-id="trace-message-rows"]')
    expect(rows).toHaveLength(3)
    await rows[2].trigger('click')
    await wrapper.get('[data-action="locate-debug-event"]').trigger('click')

    expect(store.loadProjection).toHaveBeenCalledWith('dbg-1', 'history', 9)
  })

  it('详情展示请求响应元数据、重试重定向以及传输配置', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const trace: any = makeLiveTrace('trace-transport-ui', 'succeeded', 'https://example.test/final')
    trace.operation = {
      ...trace.operation,
      request_headers: { authorization: 'Bearer debug-token', 'content-type': 'application/json' },
      request_query: { page: '2' },
      response_headers: { 'content-type': 'application/json', 'x-request-id': 'req-1' },
      final_url: 'https://example.test/final',
      redirects: [{ status_code: 302, from_url: 'https://example.test/start', to_url: 'https://example.test/final' }],
      retry_attempt: 2,
      proxy: { mode: 'manual', url: 'http://proxy.example.test:8080' },
      tls: { verify: 'system', certificate_pins: ['sha256/test'] },
    }
    trace.connections = [{
      connection_id: 'conn-transport-ui',
      connection_epoch: 3,
      connection_state: 'connected',
      message_count: 4,
      reconnect_count: 2,
      reconnect_reason: 'network.websocket_peer_closed',
      queue_depth: 2,
      dropped_count: 1,
      activation_queue_depth: 1,
      activation_dropped_count: 0,
      backpressure_policy: 'drop_oldest',
      debug_event_index: 17,
    }]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(1),
      traces: [trace],
    })
    apiMocks.fetchDebugSessionNetworkTrace.mockResolvedValueOnce({ trace })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    await wrapper.get('[data-trace-id="trace-transport-ui"]').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('请求头')
    expect(wrapper.text()).toContain('authorization')
    expect(wrapper.text()).toContain('查询参数')
    expect(wrapper.text()).toContain('响应头')
    expect(wrapper.text()).toContain('重试2')
    expect(wrapper.text()).toContain('重定向1')
    expect(wrapper.text()).toContain('代理')
    expect(wrapper.text()).toContain('TLS')
    expect(wrapper.text()).toContain('激活队列 1')
    expect(wrapper.text()).toContain('Debug 事件索引')
    expect(wrapper.text()).toContain('17')
    expect(wrapper.get('[data-testid="connection-reconnect-reason"]').text()).toContain('network.websocket_peer_closed')
  })

  it('二进制正文先显示资源摘要，展开后才显示内容', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    apiMocks.fetchDebugSessionNetworkTraceBody.mockResolvedValueOnce({
      request_body: {
        encoding: 'base64',
        value: 'AAE=',
        resource_kind: 'session_temp',
        resource_id: 'body-abc',
        size_bytes: 2,
        content_type: 'application/octet-stream',
        sha256: 'checksum-1',
      },
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()
    await wrapper.get('[data-trace-id="trace-1"]').trigger('click')
    await wrapper.get('[data-action="toggle-request-body"]').trigger('click')

    const summary = wrapper.get('[data-testid="trace-request-body-summary"]')
    expect(summary.text()).toContain('2 bytes')
    expect(summary.text()).toContain('application/octet-stream')
    expect(summary.text()).toContain('checksum-1')
    expect(summary.text()).toContain('session_temp')
    expect(wrapper.get('[data-testid="trace-request-body"]').text()).toContain('AAE=')
  })

  it('协议筛选包含浏览器动态监听', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const browserTrace: any = makeLiveTrace(
      'trace-browser-listener',
      'succeeded',
      'https://example.test/items',
    )
    browserTrace.protocol = 'browser'
    browserTrace.operation.protocol = 'browser'
    browserTrace.operation.method = 'WAIT_FOR_REQUEST'
    browserTrace.messages = [{ event_kind: 'browser.request_observed', payload: { post_data: 'body' } }]
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(1),
      traces: [browserTrace],
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()

    const protocolSelect = wrapper.get('[data-testid="network-protocol-filter"]')
    expect(protocolSelect.find('option[value="browser"]').exists()).toBe(true)
    await protocolSelect.setValue('browser')
    expect(wrapper.findAll('[data-trace-id]')).toHaveLength(2)
  })

  it('支持按 Debug 会话 ID 筛选网络记录', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'running' },
    } as any
    const firstTrace: any = makeLiveTrace('trace-session-a', 'succeeded', 'https://example.test/a')
    firstTrace.debug_session_id = 'dbg-1'
    const secondTrace: any = makeLiveTrace('trace-session-b', 'succeeded', 'https://example.test/b')
    secondTrace.debug_session_id = 'dbg-2'
    apiMocks.fetchDebugSessionNetwork.mockResolvedValueOnce({
      summary: makeSummary(2),
      traces: [firstTrace, secondTrace],
    })

    const wrapper = mount(DebugNetworkPanel, { global: { plugins: [pinia] } })
    await nextTick()
    await nextTick()

    await wrapper.get('[data-testid="network-session-filter"]').setValue('dbg-2')
    const rows = wrapper.findAll('[data-trace-id]')
    expect(rows).toHaveLength(1)
    expect(rows[0].attributes('data-trace-id')).toBe('trace-session-b')
  })
})
