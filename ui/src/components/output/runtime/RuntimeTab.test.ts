import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import RuntimeTab from './RuntimeTab.vue'
import { useRuntimeStore } from '@/stores/runtimeStore'

describe('RuntimeTab', () => {
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
  })

  it('执行进度显示真实计数而不是命名占位符', () => {
    const runtime = useRuntimeStore()
    runtime.activeRt = {
      status: 'running',
      runtime_session: { session_id: 'runtime-session-1' },
      request: {},
      node_states: [],
      event_log: [],
    } as any
    runtime.runtimeProgress = {
      session_id: 'runtime-session-1',
      status: 'running',
      total_node_count: 5,
      completed_node_count: 3,
      failed_node_count: 0,
      running_node_count: 2,
      pending_node_count: 0,
      event_count: 8,
      percent: 60,
    }

    const wrapper = mount(RuntimeTab, {
      global: { plugins: [pinia] },
    })

    expect(wrapper.text()).toContain('完成 3')
    expect(wrapper.text()).toContain('运行中 2')
    expect(wrapper.text()).toContain('事件 8')
    expect(wrapper.text()).not.toContain('{n}')
  })
})
