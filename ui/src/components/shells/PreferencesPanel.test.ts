import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => ({
  postPreferences: vi.fn(),
  postPreferencesReset: vi.fn(),
  fetchPreferences: vi.fn(),
  postPreferencesPreview: vi.fn(),
  postFileDialog: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  postPreferences: apiMocks.postPreferences,
  postPreferencesReset: apiMocks.postPreferencesReset,
  fetchPreferences: apiMocks.fetchPreferences,
  postPreferencesPreview: apiMocks.postPreferencesPreview,
  postFileDialog: apiMocks.postFileDialog,
}))

import PreferencesPanel from './PreferencesPanel.vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'

function buildSnapshot() {
  return {
    preferences: {
      program_settings: {
        preferences_auto_save: false,
      },
      compile_settings: {},
      security_settings: {
        allow_file_access: true,
        file_access_scope: 'custom_roots',
        file_access_allowed_roots: ['C:\\allowed'],
      },
      python_runtime_settings: {},
      graph_settings: {},
      other_settings: {},
    },
    graph_workspace: {
      preferences_state: {
        security_settings: {
          file_access_allowed_roots: 'active',
        },
      },
    },
  } as any
}

describe('PreferencesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('挂载时不会改写 workspace.snapshot.preferences 原对象', async () => {
    const workspace = useWorkspaceStore()
    const snapshot = buildSnapshot()
    const originalRootsRef = snapshot.preferences.security_settings.file_access_allowed_roots
    workspace.snapshot = snapshot

    mount(PreferencesPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await nextTick()

    const securitySettings = (workspace.snapshot?.preferences as any)?.security_settings
    expect(Array.isArray(securitySettings?.file_access_allowed_roots)).toBe(true)
    expect(securitySettings?.file_access_allowed_roots).toEqual(['C:\\allowed'])
    expect(snapshot.preferences.security_settings.file_access_allowed_roots).toBe(originalRootsRef)
    expect(snapshot.preferences.security_settings.file_access_allowed_roots).toEqual(['C:\\allowed'])
  })
})
