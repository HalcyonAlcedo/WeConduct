import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const startupState = vi.hoisted(() => ({
  severity: 'fault' as string,
  phase: 'blocked' as string,
  report: {
    generated_at: '2026-07-15T00:00:00Z',
    overall_severity: 'fault',
    recoverable_targets: ['workspace_state'],
    subsystems: [],
  } as any,
  triggerError: { message: 'workspace state missing required key: security_settings', status: 500, code: 'workspace_state_invalid' } as any,
  recoverResults: [] as any[],
  recoverError: null as string | null,
  problemSubsystems: [
    {
      subsystem: 'workspace_state',
      label: '工作区状态',
      location: 'C:/Users/x/AppData/Local/WeConduct/workspace-state.json',
      status: 'invalid',
      severity: 'fault',
      error_code: 'workspace_state_invalid',
      message: 'workspace state missing required key: security_settings',
      recoverable: true,
      recovery_target: 'workspace_state',
    },
  ] as any[],
  recoverableTargets: ['workspace_state'],
  canRecover: true,
  canForceStart: false,
  recover: vi.fn().mockResolvedValue(true),
}))

vi.mock('@/stores/startupStore', () => ({
  useStartupStore: () => startupState,
}))

import StartupErrorScreen from './StartupErrorScreen.vue'

describe('StartupErrorScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    })
  })

  it('renders severity, location and message for a fault', () => {
    const wrapper = mount(StartupErrorScreen)
    expect(wrapper.find('.se-badge').text()).toBe('故障')
    expect(wrapper.text()).toContain('workspace-state.json')
    expect(wrapper.text()).toContain('workspace_state_invalid')
    expect(wrapper.text()).toContain('security_settings')
  })

  it('shows the recovery action for a recoverable fault and emits restart after recovery', async () => {
    const wrapper = mount(StartupErrorScreen)
    const primary = wrapper.find('.se-btn-primary')
    expect(primary.text()).toContain('用默认配置强行启动')

    await primary.trigger('click')
    await flushPromises()

    expect(startupState.recover).toHaveBeenCalled()
    expect(wrapper.emitted('restart')).toBeTruthy()
  })

  it('copies a full structured report to the clipboard', async () => {
    const wrapper = mount(StartupErrorScreen)
    await wrapper.find('.se-copy-all').trigger('click')

    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1)
    const copied = (navigator.clipboard.writeText as any).mock.calls[0][0] as string
    expect(copied).toContain('WeConduct 启动错误报告')
    expect(copied).toContain('工作区状态')
    expect(copied).toContain('workspace_state_invalid')
    expect(copied).toContain('C:/Users/x/AppData/Local/WeConduct/workspace-state.json')
  })

  it('exposes 强行启动 only for anomalies', async () => {
    startupState.severity = 'anomaly'
    startupState.canForceStart = true
    startupState.canRecover = false
    const wrapper = mount(StartupErrorScreen)

    const forceBtn = wrapper.findAll('.se-btn-primary').find(b => b.text().includes('强行启动'))
    expect(forceBtn).toBeTruthy()
    await forceBtn!.trigger('click')
    expect(wrapper.emitted('forceStart')).toBeTruthy()

    // restore for other tests
    startupState.severity = 'fault'
    startupState.canForceStart = false
    startupState.canRecover = true
  })
})
