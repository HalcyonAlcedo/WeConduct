import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import DebugSnapshotsPanel from './DebugSnapshotsPanel.vue'
import { useDebugStore } from '@/stores/debugStore'

function makeSnapshot() {
  return {
    snapshot_id: 'snapshot-manual-1',
    session_id: 'debug-session-1',
    event_id: 'event-1',
    event_index: 4,
    keyframe_id: 'keyframe-1',
    frame_identity: 'frame-1',
    event_kind: 'debug.paused',
    reason: 'manual_pause',
    recorded_at: '2026-07-12T20:00:00+00:00',
    graph_model_id: 'graph:workspace',
    graph_revision: 7,
    compilation_id: 'compilation-1',
    node_id: 'node-start',
    node_kind: 'flow.start',
    pause_timing: 'after',
    output_state: 'captured',
    variable_snapshot: {
      count: 3,
      user: { name: 'Alice', roles: ['admin'] },
    },
    variable_descriptors: {
      count: { value_type: 'integer', origin: 'runtime', nullable: false },
      user: { value_type: 'object', origin: 'runtime', nullable: false },
    },
    node_input_snapshot: { seed: 1 },
    node_output_snapshot: { ready: true },
    runtime_preview: { current_node: { node_id: 'node-start' } },
    runtime_preview_summary: {
      current_node_id: 'node-start',
      queued_node_count: 2,
      executed_node_count: 3,
    },
    instance_path: ['graph:workspace', 'node-start'],
    iteration_stack: [{ node_id: 'loop-1', iteration_index: 2 }],
  }
}

describe('DebugSnapshotsPanel', () => {
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    const store = useDebugStore()
    store.activeSession = {
      status: 'paused',
      debug_session: { session_id: 'debug-session-1', status: 'paused' },
      debug_snapshots: [makeSnapshot()],
    } as any
  })

  function mountPanel() {
    return mount(DebugSnapshotsPanel, {
      global: { plugins: [pinia] },
    })
  }

  it('默认显示结构化快照概要而不是 JSON', () => {
    const wrapper = mountPanel()

    expect(wrapper.text()).toContain('手动暂停')
    expect(wrapper.text()).toContain('node-start')
    expect(wrapper.text()).toContain('flow.start')
    expect(wrapper.text()).toContain('已捕获')
    expect(wrapper.find('[data-testid="snapshot-raw-json"]').exists()).toBe(false)
  })

  it('变量页显示变量名称、声明类型和值树', async () => {
    const wrapper = mountPanel()

    await wrapper.get('[data-tab="variables"]').trigger('click')

    expect(wrapper.text()).toContain('count')
    expect(wrapper.text()).toContain('integer')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('user')
    expect(wrapper.text()).toContain('object')
    expect(wrapper.text()).toContain('Alice')
  })

  it('原始 JSON 入口位于追踪页且展开后才序列化显示', async () => {
    const wrapper = mountPanel()

    expect(wrapper.find('[data-testid="snapshot-raw-toggle"]').exists()).toBe(false)
    await wrapper.get('[data-tab="trace"]').trigger('click')
    expect(wrapper.find('[data-testid="snapshot-raw-json"]').exists()).toBe(false)

    await wrapper.get('[data-testid="snapshot-raw-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="snapshot-raw-json"]').text()).toContain('snapshot-manual-1')
  })
})
