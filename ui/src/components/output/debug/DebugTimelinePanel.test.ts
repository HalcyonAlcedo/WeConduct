import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const debugStoreMock = vi.hoisted(() => ({
  events: [] as any[],
  eventsTotal: 0,
  eventsSessionId: 'dbg-1' as string | null,
  activeSession: null as any,
  activeHistorySession: null as any,
  projection: null as any,
  isDebugActive: false,
  loadProjection: vi.fn(),
  clearProjection: vi.fn(),
}))

const dockStoreMock = vi.hoisted(() => ({
  restorePanel: vi.fn(),
  activatePanel: vi.fn(),
}))

vi.mock('@/stores/debugStore', () => ({
  useDebugStore: () => debugStoreMock,
}))
vi.mock('@/stores/dockStore', () => ({
  useDockStore: () => dockStoreMock,
}))

import DebugTimelinePanel from './DebugTimelinePanel.vue'
import { fetchDebugProjection } from '@/services/api'

describe('DebugTimelinePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    debugStoreMock.events = [
      {
        event_id: 'evt-1',
        event_index: 3,
        event_kind: 'breakpoint.hit',
        node_id: 'node-a',
        recorded_at: '2026-07-10T10:00:00Z',
        session_id: 'dbg-1',
        keyframe_id: 'kf-4',
      },
      {
        event_id: 'evt-2',
        event_index: 4,
        event_kind: 'record_frame.hit',
        node_id: 'node-b',
        recorded_at: '2026-07-10T10:00:01Z',
        session_id: 'dbg-1',
        instance_path: ['graph:workspace', 'node-b'],
        iteration_stack: ['node-loop:2'],
      },
    ]
    debugStoreMock.eventsTotal = 2
    debugStoreMock.eventsSessionId = 'dbg-1'
    debugStoreMock.activeSession = {
      network_trace_snapshot: {
        summary: {
          total_operations: 1,
          successful_operations: 1,
          failed_operations: 0,
          cancelled_operations: 2,
          active_connections: 0,
          queue_depth: 0,
          reconnect_count: 3,
          dropped_count: 4,
          recent_errors: [{ trace_id: 'trace-error', operation_id: 'network.http_request', status: 'failed', error_code: 'network.timeout', ended_at: null }],
        },
      },
    }
    debugStoreMock.activeHistorySession = null
    debugStoreMock.projection = null
    debugStoreMock.isDebugActive = false
    debugStoreMock.loadProjection.mockResolvedValue(undefined)
    dockStoreMock.restorePanel.mockReset()
    dockStoreMock.activatePanel.mockReset()
  })

  it('使用 event_id 作为稳定标识，并点击时加载对应历史投影', async () => {
    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    const items = wrapper.findAll('[data-event-id]')
    expect(items).toHaveLength(2)
    expect(items[0].attributes('data-event-id')).toBe('evt-1')
    expect(items[1].attributes('data-event-id')).toBe('evt-2')

    await items[1].trigger('click')
    expect(debugStoreMock.loadProjection).toHaveBeenCalledWith('dbg-1', 'history', 4)
    expect(wrapper.emitted('select-event')).toEqual([[
      4,
    ]])
    expect(wrapper.text()).toContain('node-loop:2')
    expect(wrapper.text()).toContain('关键帧')
    expect(wrapper.text()).toContain('退出历史查看')
    expect(wrapper.text()).toContain('取消 2')
    expect(wrapper.text()).toContain('队列 0')
    expect(wrapper.text()).toContain('重连 3')
    expect(wrapper.text()).toContain('丢弃 4')
    expect(wrapper.text()).toContain('network.timeout')
  })

  it('退出历史查看时，有活动会话恢复 live，否则清空投影回到静态图', async () => {
    debugStoreMock.activeSession = {
      debug_session: { session_id: 'dbg-live-1', status: 'paused' },
    }
    debugStoreMock.isDebugActive = true
    const activeWrapper = mount(DebugTimelinePanel)

    await activeWrapper.findAll('[data-event-id]')[0].trigger('click')
    await activeWrapper.get('[data-action="exit-history"]').trigger('click')

    expect(debugStoreMock.loadProjection).toHaveBeenLastCalledWith('dbg-live-1', 'live')

    debugStoreMock.loadProjection.mockClear()
    debugStoreMock.activeSession = null
    debugStoreMock.isDebugActive = false
    const historyWrapper = mount(DebugTimelinePanel)

    await historyWrapper.findAll('[data-event-id]')[0].trigger('click')
    await historyWrapper.get('[data-action="exit-history"]').trigger('click')

    expect(debugStoreMock.loadProjection).not.toHaveBeenCalledWith(expect.anything(), 'live')
    expect(debugStoreMock.clearProjection).toHaveBeenCalled()
  })

  it('可直接打开网络调试窗口', async () => {
    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    await wrapper.get('[data-action="open-network-debug"]').trigger('click')

    expect(dockStoreMock.restorePanel).toHaveBeenCalledWith('debugNetwork')
    expect(dockStoreMock.activatePanel).toHaveBeenCalledWith('debugNetwork')
  })

  it('历史会话也显示网络概览并可打开网络调试窗口', async () => {
    debugStoreMock.activeSession = null
    debugStoreMock.activeHistorySession = {
      session_id: 'dbg-history-1',
      session: {
        network_trace_snapshot: {
          summary: {
            total_operations: 2,
            successful_operations: 1,
            failed_operations: 1,
            cancelled_operations: 0,
            active_connections: 1,
            queue_depth: 2,
            reconnect_count: 1,
            dropped_count: 0,
            recent_errors: [],
          },
        },
      },
    }

    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    expect(wrapper.text()).toContain('操作 2')
    await wrapper.get('[data-action="open-network-debug"]').trigger('click')
    expect(dockStoreMock.restorePanel).toHaveBeenCalledWith('debugNetwork')
  })

  it('历史投影优先使用历史会话的网络概述', async () => {
    debugStoreMock.projection = { mode: 'history' }
    debugStoreMock.activeSession = {
      network_trace_snapshot: {
        summary: {
          total_operations: 1,
          successful_operations: 1,
          failed_operations: 0,
          cancelled_operations: 0,
          active_connections: 0,
          queue_depth: 0,
          reconnect_count: 0,
          dropped_count: 0,
          recent_errors: [],
        },
      },
    }
    debugStoreMock.activeHistorySession = {
      session_id: 'dbg-history-2',
      session: {
        network_trace_snapshot: {
          summary: {
            total_operations: 9,
            successful_operations: 8,
            failed_operations: 1,
            cancelled_operations: 0,
            active_connections: 2,
            queue_depth: 4,
            reconnect_count: 3,
            dropped_count: 1,
            recent_errors: [],
          },
        },
      },
    }

    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    expect(wrapper.text()).toContain('操作 9')
    expect(wrapper.text()).toContain('连接 2')
    expect(wrapper.text()).not.toContain('操作 1 条')
  })

  it('有 Debug 事件但尚无网络摘要时仍提供网络调试入口', async () => {
    debugStoreMock.activeSession = null
    debugStoreMock.activeHistorySession = null

    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    await wrapper.get('[data-action="open-network-debug"]').trigger('click')
    expect(dockStoreMock.restorePanel).toHaveBeenCalledWith('debugNetwork')
  })

  it('无 Debug 事件且尚无网络摘要时仍提供网络调试入口', async () => {
    debugStoreMock.events = []
    debugStoreMock.eventsTotal = 0
    debugStoreMock.activeSession = null
    debugStoreMock.activeHistorySession = null

    const wrapper = mount(DebugTimelinePanel)
    await nextTick()

    await wrapper.get('[data-action="open-network-debug"]').trigger('click')
    expect(dockStoreMock.restorePanel).toHaveBeenCalledWith('debugNetwork')
  })
})

describe('fetchDebugProjection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'dbg-1',
        source: 'history_store',
        projection: { mode: 'history', node_status_by_id: {}, active_paths: [] },
      }),
    }))
  })

  it('history projection 支持 event_index 查询参数', async () => {
    await fetchDebugProjection('dbg-1', 'history', 7)

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/debug/projection/history/dbg-1?event_index=7',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
})
