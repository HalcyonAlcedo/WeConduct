import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => ({
  fetchDebugSessions: vi.fn(),
  fetchDebugHistorySessions: vi.fn(),
  fetchDebugSession: vi.fn(),
  fetchDebugHistorySession: vi.fn(),
  fetchDebugProjection: vi.fn(),
  fetchDebugEvents: vi.fn(),
  postDebugPrepare: vi.fn(),
  postDebugStart: vi.fn(),
  postDebugContinue: vi.fn(),
  postDebugStepOver: vi.fn(),
  postDebugStepInto: vi.fn(),
  postDebugStepOut: vi.fn(),
  postDebugPause: vi.fn(),
  postDebugAbort: vi.fn(),
  postDebugVariablesApply: vi.fn(),
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
  postDebugContinue: apiMocks.postDebugContinue,
  postDebugStepOver: apiMocks.postDebugStepOver,
  postDebugStepInto: apiMocks.postDebugStepInto,
  postDebugStepOut: apiMocks.postDebugStepOut,
  postDebugPause: apiMocks.postDebugPause,
  postDebugAbort: apiMocks.postDebugAbort,
  postDebugVariablesApply: apiMocks.postDebugVariablesApply,
}))

import DebugTab from './DebugTab.vue'
import { useDebugStore } from '@/stores/debugStore'
import { useToastStore } from '@/stores/toastStore'
import { useDockStore } from '@/stores/dockStore'
import { useGraphStore } from '@/stores/graphStore'

function makeDetail(sessionId: string, status: string, canStepOut = false) {
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
      can_step_out: canStepOut,
    },
    stage_timeline: [],
    object_index: { graph_model_id: 'graph:workspace', nodes: [], ports: [], edges: [] },
    diagnostic_links: [],
    runtime_preview: { current_node: { node_id: 'node-start' } },
    variable_snapshot: {},
  }
}

function mountDebugTab(pinia = createPinia()) {
  setActivePinia(pinia)
  return mount(DebugTab, {
    global: {
      plugins: [pinia],
      stubs: {
        PlaceholderBanner: {
          template: '<div><slot /></div>',
        },
      },
    },
  })
}

async function flushMount() {
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('DebugTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    apiMocks.fetchDebugSessions.mockResolvedValue({ sessions: [] })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: {
        debug_session_count: 0,
        debug_status_counts: {},
      },
      sessions: [],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-active-1', 'paused'))
    apiMocks.fetchDebugProjection.mockResolvedValue({
      session_id: 'dbg-active-1',
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
      session_id: 'dbg-active-1',
      source: 'history_store',
      total_count: 0,
      events: [],
    })
    apiMocks.postDebugPrepare.mockResolvedValue({
      status: 'ready',
      request: {},
      stage_timeline: [],
      object_index: null,
      diagnostic_links: [],
    })
  })

  it('挂载时刷新正式状态的 debug sessions/history', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [
        {
          session_id: 'dbg-active-1',
          status: 'preparing',
          graph_model_id: 'graph:workspace',
        },
      ],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: {
        debug_session_count: 2,
        debug_status_counts: { preparing: 1, failed: 1 },
      },
      sessions: [
        {
          session_id: 'dbg-active-1',
          status: 'preparing',
          graph_model_id: 'graph:workspace',
        },
        {
          session_id: 'dbg-history-1',
          status: 'failed',
          graph_model_id: 'graph:workspace',
        },
      ],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-active-1', 'preparing'))

    const pinia = createPinia()
    setActivePinia(pinia)
    const debugStore = useDebugStore()
    const wrapper = mountDebugTab(pinia)

    await flushMount()

    expect(apiMocks.fetchDebugSessions).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchDebugHistorySessions).toHaveBeenCalledTimes(1)
    expect(debugStore.sessions).toHaveLength(1)
    expect(debugStore.historySessions).toHaveLength(2)
    expect(debugStore.activeSession?.debug_session.status).toBe('preparing')
    expect(wrapper.text()).toContain('活动会话 (1)')
    expect(wrapper.text()).toContain('历史会话 (2)')
    expect(wrapper.text()).toContain('准备中')
    expect(wrapper.text()).toContain('失败')
  })

  it('事件列表使用 event_id，且不再提供旧的任意变量名覆盖入口', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [{ session_id: 'dbg-active-1', status: 'paused', graph_model_id: 'graph:workspace' }],
    })
    apiMocks.fetchDebugHistorySessions.mockResolvedValue({
      summary: { debug_session_count: 0, debug_status_counts: {} },
      sessions: [],
    })
    apiMocks.fetchDebugEvents.mockResolvedValue({
      session_id: 'dbg-active-1',
      source: 'history_store',
      total_count: 1,
      events: [{ event_id: 'evt-stable-1', event_index: 1, event_kind: 'breakpoint.hit' }],
    })

    const wrapper = mountDebugTab()
    await flushMount()

    expect(wrapper.get('[data-event-id="evt-stable-1"]').attributes('data-event-id')).toBe('evt-stable-1')
    expect(wrapper.find('input[placeholder="变量名"]').exists()).toBe(false)
  })

  it('定位当前节点时选中节点并恢复节点图面板', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [{ session_id: 'dbg-active-1', status: 'paused', graph_model_id: 'graph:workspace' }],
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const dock = useDockStore()
    const graph = useGraphStore()
    dock.register({ id: 'graph', title: '节点图编辑器' })

    const wrapper = mountDebugTab(pinia)
    await flushMount()
    await wrapper.get('button[title="定位到当前运行节点"]').trigger('click')

    expect(graph.selectedNode).toBe('node-start')
    expect(dock.isPanelVisible('graph')).toBe(true)
  })

  it('按钮矩阵收口到 paused/running/stepping/preparing 规则', async () => {
    const assertButtons = async (
      status: string,
      expectation: Record<string, boolean>,
    ) => {
      apiMocks.fetchDebugSessions.mockResolvedValue({
        sessions: [{ session_id: 'dbg-active-1', status, graph_model_id: 'graph:workspace' }],
      })
      apiMocks.fetchDebugHistorySessions.mockResolvedValue({
        summary: { debug_session_count: 1, debug_status_counts: { [status]: 1 } },
        sessions: [{ session_id: 'dbg-active-1', status, graph_model_id: 'graph:workspace' }],
      })
      apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-active-1', status))

      const pinia = createPinia()
      setActivePinia(pinia)
      const wrapper = mountDebugTab(pinia)
      await flushMount()

      const getButton = (label: string) => wrapper.findAll('button').find((button) => button.text() === label)
      for (const [label, enabled] of Object.entries(expectation)) {
        const button = getButton(label)
        expect(button?.exists()).toBe(true)
        expect(button?.attributes('disabled'), label).toBe(enabled ? undefined : '')
      }
    }

    await assertButtons('preparing', {
      '▶ 继续': false,
      '⤵ 单步跳过': false,
      '↓ 单步进入': false,
      '↑ 单步跳出': false,
      '⏸ 暂停': false,
      '✕ 中止': true,
    })

    await assertButtons('paused', {
      '▶ 继续': true,
      '⤵ 单步跳过': true,
      '↓ 单步进入': true,
      '↑ 单步跳出': false,
      '⏸ 暂停': false,
      '✕ 中止': true,
    })

    await assertButtons('running', {
      '▶ 继续': false,
      '⤵ 单步跳过': false,
      '↓ 单步进入': false,
      '↑ 单步跳出': false,
      '⏸ 暂停': true,
      '✕ 中止': true,
    })
  })

  it('仅在子图暂停时启用单步跳出', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [{ session_id: 'dbg-active-1', status: 'paused', graph_model_id: 'graph:workspace' }],
    })
    apiMocks.fetchDebugSession.mockResolvedValue(makeDetail('dbg-active-1', 'paused', true))

    const wrapper = mountDebugTab()
    await flushMount()

    const button = wrapper.findAll('button').find((item) => item.text() === '↑ 单步跳出')
    expect(button?.attributes('disabled')).toBeUndefined()
  })

  it('控制成功后刷新失败只报面板同步失败', async () => {
    apiMocks.fetchDebugSessions.mockResolvedValue({
      sessions: [{ session_id: 'dbg-active-1', status: 'paused', graph_model_id: 'graph:workspace' }],
    })
    apiMocks.postDebugContinue.mockResolvedValue({
      status: 'completed',
      debug_session: { ...makeDetail('dbg-active-1', 'completed').debug_session },
    })

    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mountDebugTab(pinia)
    await flushMount()
    apiMocks.fetchDebugSession.mockResolvedValueOnce(makeDetail('dbg-active-1', 'completed'))
    apiMocks.fetchDebugSessions.mockRejectedValueOnce(new Error('sync unavailable'))

    const button = wrapper.findAll('button').find((item) => item.text() === '▶ 继续')
    await button?.trigger('click')
    await flushMount()

    const toast = useToastStore()
    await vi.waitFor(() => {
      expect(toast.toasts.some((item) => item.title === '面板同步失败')).toBe(true)
    })
    expect(toast.toasts.some((item) => item.title === '继续')).toBe(true)
    expect(toast.toasts.some((item) => item.title === '继续失败')).toBe(false)
  })
})
