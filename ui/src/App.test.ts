import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const registeredShortcuts = vi.hoisted(() => [] as any[])

const workspaceState = vi.hoisted(() => ({
  initialize: vi.fn().mockResolvedValue(undefined),
  reset: vi.fn(),
  connectionState: 'connected' as string,
  initError: null as unknown,
  snapshot: {
    preferences: {
      program_settings: {
        check_updates_on_startup: false,
      },
    },
    project: {
      loaded: false,
    },
  } as any,
}))

const graphWorkspaceState = vi.hoisted(() => ({
  hasGraph: true,
  graphModel: { nodes: [] } as any,
  isDirty: false,
  syncSource: vi.fn(),
  loadGraph: vi.fn(),
  removeNode: vi.fn(),
  pasteNode: vi.fn(),
  undo: vi.fn(),
  redo: vi.fn(),
}))

const graphStoreState = vi.hoisted(() => ({
  selectedNode: 'node-a' as string | null,
  selectNode: vi.fn(),
}))

const compilationState = vi.hoisted(() => ({
  sourceText: '',
  clearSource: vi.fn(),
}))

const runtimeState = vi.hoisted(() => ({
  isRuntimeActive: false,
  startAndRun: vi.fn().mockResolvedValue({ success: true, message: 'ok' }),
  refreshAll: vi.fn(),
}))

const toastState = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

const updateState = vi.hoisted(() => ({
  fetchStatus: vi.fn().mockResolvedValue(undefined),
  checkForUpdates: vi.fn().mockResolvedValue(null),
}))

const startupState = vi.hoisted(() => ({
  hasBlockingError: false,
  phase: 'idle' as string,
  diagnose: vi.fn().mockResolvedValue(undefined),
  reset: vi.fn(),
}))

vi.mock('@/composables/useKeyboard', () => ({
  useKeyboard: (shortcuts: any[]) => {
    registeredShortcuts.splice(0, registeredShortcuts.length, ...shortcuts)
  },
}))
vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: () => workspaceState,
}))
vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphWorkspaceState,
}))
vi.mock('@/stores/graphStore', () => ({
  useGraphStore: () => graphStoreState,
}))
vi.mock('@/stores/compilationStore', () => ({
  useCompilationStore: () => compilationState,
}))
vi.mock('@/stores/runtimeStore', () => ({
  useRuntimeStore: () => runtimeState,
}))
vi.mock('@/stores/toastStore', () => ({
  useToastStore: () => toastState,
}))
vi.mock('@/stores/updateStore', () => ({
  useUpdateStore: () => updateState,
}))
vi.mock('@/stores/startupStore', () => ({
  useStartupStore: () => startupState,
}))
vi.mock('@/stores/themeStore', () => ({
  useThemeStore: () => ({
    mode: 'light',
    preference: 'system',
    toggle: vi.fn(),
    setPreference: vi.fn(),
    initFromConfig: vi.fn(),
  }),
}))
vi.mock('@/stores/fontScaleStore', () => ({
  useFontScaleStore: () => ({
    scale: 1,
    setScale: vi.fn(),
    initFromConfig: vi.fn(),
  }),
}))
vi.mock('@/stores/languageStore', () => ({
  useLanguageStore: () => ({
    locale: 'zh-CN',
    resource: 'zh-CN',
    available: [],
    loading: false,
    refreshAvailable: vi.fn().mockResolvedValue(undefined),
    setLocale: vi.fn().mockResolvedValue(true),
    setResourceLocale: vi.fn().mockResolvedValue(true),
    initFromConfig: vi.fn().mockResolvedValue(undefined),
  }),
}))
vi.mock('@/stores/dockStore', () => ({
  useDockStore: () => ({
    restorePanel: vi.fn(),
  }),
}))
vi.mock('@/components/commandbar/CommandBar.vue', () => ({
  default: defineComponent({ setup() { return () => h('div', 'commandbar') } }),
}))
vi.mock('@/components/common/StatusBar.vue', () => ({
  default: defineComponent({ setup() { return () => h('div', 'statusbar') } }),
}))
vi.mock('@/components/common/ToastContainer.vue', () => ({
  default: defineComponent({ setup() { return () => h('div', 'toast') } }),
}))
vi.mock('@/components/common/StartupErrorScreen.vue', () => ({
  default: defineComponent({ setup() { return () => h('div', 'startup-error') } }),
}))

import App from './App.vue'

describe('App Delete 快捷键', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    registeredShortcuts.splice(0, registeredShortcuts.length)
    ;(workspaceState.snapshot as any).graph_workspace = {
      graph_preferences: {
        confirm_delete_node: false,
      },
    }
    graphStoreState.selectedNode = 'node-a'
  })

  it('confirm_delete_node=false 时 Delete 直接删除，不走确认弹窗', async () => {
    ;(window as any).__openDeleteConfirm = vi.fn()
    mount(App, {
      global: {
        stubs: {
          RouterView: defineComponent({ setup() { return () => h('div', 'router') } }),
        },
      },
    })
    await flushPromises()

    const del = registeredShortcuts.find(item => item.key === 'Delete')
    expect(del).toBeTruthy()
    del.handler(new KeyboardEvent('keydown', { key: 'Delete' }))

    expect((window as any).__openDeleteConfirm).not.toHaveBeenCalled()
    expect(graphWorkspaceState.removeNode).toHaveBeenCalledWith('node-a')
    expect(graphStoreState.selectNode).toHaveBeenCalledWith(null)
  })
})
