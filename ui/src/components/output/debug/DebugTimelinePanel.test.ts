import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const debugStoreMock = vi.hoisted(() => ({
  events: [] as any[],
  eventsTotal: 0,
  eventsSessionId: 'dbg-1' as string | null,
  activeSession: null as any,
  isDebugActive: false,
  loadProjection: vi.fn(),
  clearProjection: vi.fn(),
}))

vi.mock('@/stores/debugStore', () => ({
  useDebugStore: () => debugStoreMock,
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
    debugStoreMock.activeSession = null
    debugStoreMock.isDebugActive = false
    debugStoreMock.loadProjection.mockResolvedValue(undefined)
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
