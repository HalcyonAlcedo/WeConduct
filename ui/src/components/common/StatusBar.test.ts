import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const workspaceState = vi.hoisted(() => ({
  isConnected: true,
  workbenchEventConnected: false,
  workbenchEventError: '401 Unauthorized',
  projectName: 'test-project',
  compileCounter: 0,
  lastCompileTime: null as string | null,
  isLimitedBrowser: false,
}))

const compilationState = vi.hoisted(() => ({
  isCompiling: false,
  compilePhase: 'idle',
  view: null,
  sourceText: '',
}))

vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: () => workspaceState,
}))

vi.mock('@/stores/compilationStore', () => ({
  useCompilationStore: () => compilationState,
}))

import StatusBar from './StatusBar.vue'

describe('StatusBar', () => {
  beforeEach(() => {
    workspaceState.isConnected = true
    workspaceState.workbenchEventConnected = false
    workspaceState.workbenchEventError = '401 Unauthorized'
  })

  it('工作台事件流断开时显示实时同步故障', () => {
    const wrapper = mount(StatusBar)

    expect(wrapper.text()).toContain('实时同步已断开')
    expect(wrapper.get('.status-sync').attributes('title')).toBe('401 Unauthorized')
  })
})
