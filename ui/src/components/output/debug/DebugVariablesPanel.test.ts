import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const debugStoreMock = vi.hoisted(() => ({
  activeSession: null as any,
  activeHistorySession: null as any,
  projection: null as any,
  projectionVariableSnapshot: null as any,
  applyVariables: vi.fn(),
  loadActiveSession: vi.fn(),
}))
vi.mock('@/stores/debugStore', () => ({ useDebugStore: () => debugStoreMock }))
vi.mock('@/stores/toastStore', () => ({ useToastStore: () => ({ success: vi.fn(), error: vi.fn() }) }))
import DebugVariablesPanel from './DebugVariablesPanel.vue'

describe('DebugVariablesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    debugStoreMock.projection = null
    debugStoreMock.activeSession = {
      debug_session: { session_id: 'dbg-1', status: 'paused', variable_apply_mode: 'immediate' },
      variable_snapshot: { username: 'alice', retry_count: 3, enabled: true },
      variable_descriptors: {
        username: { value_type: 'string', scope: 'global' },
        retry_count: { value_type: 'integer', scope: 'global' },
        enabled: { value_type: 'boolean', scope: 'dynamic' },
      },
      variable_changes: { username: { pending: false } },
    }
  })

  it('renders typed inline rows and commits on enter', async () => {
    debugStoreMock.applyVariables.mockResolvedValue({})
    const wrapper = mount(DebugVariablesPanel)
    await nextTick()
    expect(wrapper.text()).toContain('变量名')
    expect(wrapper.text()).toContain('string')
    expect(wrapper.text()).toContain('dynamic')
    expect(wrapper.text()).toContain('已修改')
    const input = wrapper.findAll('input').find(item => (item.element as HTMLInputElement).value === 'alice')!
    await input.setValue('bob')
    await input.trigger('keydown.enter')
    expect(debugStoreMock.applyVariables).toHaveBeenCalledWith('dbg-1', { username: 'bob' }, 'immediate')
  })

  it('keeps history rows read only', async () => {
    debugStoreMock.projection = { mode: 'history' }
    debugStoreMock.projectionVariableSnapshot = { username: 'history' }
    debugStoreMock.activeHistorySession = { session: { variable_descriptors: { username: { value_type: 'string', scope: 'global' } } } }
    const wrapper = mount(DebugVariablesPanel)
    await nextTick()
    expect(wrapper.text()).toContain('历史快照只读')
    expect(wrapper.get('input').attributes('disabled')).toBe('')
  })
})
