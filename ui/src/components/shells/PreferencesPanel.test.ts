import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number
    body: unknown
    constructor(status: number, body: unknown) { super('mock'); this.status = status; this.body = body }
  }
  return {
    postPreferences: vi.fn(),
    postPreferencesReset: vi.fn(),
    fetchPreferences: vi.fn(),
    postPreferencesPreview: vi.fn(),
    postFileDialog: vi.fn(),
    fetchConfigValues: vi.fn(),
    patchConfigValues: vi.fn(),
    resetConfigValues: vi.fn(),
    fetchExternalApiPreferences: vi.fn(),
    postExternalApiPreferences: vi.fn(),
    fetchLanguages: vi.fn(),
    fetchLanguagePack: vi.fn(),
    ApiError: MockApiError,
  }
})

vi.mock('@/services/api', () => ({
  postPreferences: apiMocks.postPreferences,
  postPreferencesReset: apiMocks.postPreferencesReset,
  fetchPreferences: apiMocks.fetchPreferences,
  postPreferencesPreview: apiMocks.postPreferencesPreview,
  postFileDialog: apiMocks.postFileDialog,
  fetchConfigValues: apiMocks.fetchConfigValues,
  patchConfigValues: apiMocks.patchConfigValues,
  resetConfigValues: apiMocks.resetConfigValues,
  fetchExternalApiPreferences: apiMocks.fetchExternalApiPreferences,
  postExternalApiPreferences: apiMocks.postExternalApiPreferences,
  fetchLanguages: apiMocks.fetchLanguages,
  fetchLanguagePack: apiMocks.fetchLanguagePack,
  ApiError: apiMocks.ApiError,
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
      graph_preferences: {
        show_node_id_on_node: false,
        show_disabled_resource_badge: true,
        snap_to_grid: false,
        grid_enabled: true,
        auto_open_node_on_drop: true,
        confirm_delete_node: true,
        show_inline_config_summary: false,
      },
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
    apiMocks.fetchConfigValues.mockResolvedValue({
      scope: 'graph',
      values: {},
    })
    apiMocks.patchConfigValues.mockResolvedValue({
      scope: 'graph',
      values: {},
    })
    apiMocks.fetchLanguages.mockResolvedValue({ languages: [] })
    apiMocks.fetchLanguagePack.mockResolvedValue({ locale: 'zh-CN', messages: {} })
    apiMocks.fetchExternalApiPreferences.mockResolvedValue({ enabled: false, token: null, token_configured: false, external_api_port: 0, project_allowed_roots: [] })
    try { localStorage.clear() } catch { /* jsdom */ }
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

  it('显示启动时检查更新字段', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: {
          language: 'zh-CN',
          resource_language: 'zh-CN',
          theme: 'light',
          default_window_size: { width: 1440, height: 900 },
          startup_action: 'restore_last_workspace',
          default_project_directory: null,
          recent_project_limit: 10,
          preferences_auto_save: false,
          check_updates_on_startup: false,
          font_scale: 100,
        },
        compile_settings: {},
        security_settings: {},
        python_runtime_settings: {},
        graph_settings: {},
        other_settings: {},
      },
      graph_workspace: {
        preferences_state: {},
      },
    } as any

    const wrapper = mount(PreferencesPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await nextTick()

    expect(wrapper.text()).toContain('启动时检查更新')
  })

  it('显示调试变量应用策略字段', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: {
          language: 'zh-CN',
          resource_language: 'zh-CN',
          theme: 'light',
          default_window_size: { width: 1440, height: 900 },
          startup_action: 'restore_last_workspace',
          default_project_directory: null,
          recent_project_limit: 10,
          preferences_auto_save: false,
          check_updates_on_startup: false,
          font_scale: 100,
        },
        compile_settings: {},
        security_settings: {},
        python_runtime_settings: {},
        graph_settings: {},
        other_settings: {},
      },
      graph_workspace: {
        preferences_state: {},
      },
    } as any

    const wrapper = mount(PreferencesPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await nextTick()
    // Nav order after governance cleanup: 程序设置 / 安全设置 / Python 运行时设置 / 节点图设置.
    await wrapper.get('.pref-nav-item:nth-child(3)').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('调试变量应用策略')
    const select = wrapper.findAll('select').find((item) =>
      item.findAll('option').some((option) => option.text() === 'staged'),
    )
    expect(select).toBeTruthy()
    expect(select?.findAll('option').map((option) => option.text())).toEqual(['staged', 'immediate'])
    expect(wrapper.text()).not.toContain('manual_apply')
  })

  it('安全设置直接显示专用接口返回的外部 API Token', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: { preferences_auto_save: false },
        compile_settings: {},
        security_settings: {
          external_api_enabled: true,
          external_api_token_configured: true,
          external_api_project_allowed_roots: ['C:\\projects'],
          encrypted_parameter_unlock_policy: 'always_prompt',
        },
        python_runtime_settings: {},
        graph_settings: {},
        other_settings: {},
      },
      graph_workspace: { preferences_state: {} },
    } as any

    apiMocks.fetchExternalApiPreferences.mockResolvedValue({
      enabled: true,
      token: 'visible-external-token',
      token_configured: true,
      external_api_port: 0,
      project_allowed_roots: ['C:\\projects'],
    })
    const wrapper = mount(PreferencesPanel, { global: { plugins: [createPinia()] } })
    await flushPromises()
    await wrapper.get('.pref-nav-item:nth-child(2)').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('外部 API')
    expect(wrapper.text()).toContain('设为 0 自动分配')
    expect(wrapper.text()).toContain('加密参数解锁策略')
    const tokenField = wrapper.findAll('.pref-field').find((item) => item.text().includes('外部 API Token'))
    const token = tokenField?.find('input')
    expect(token?.exists()).toBe(true)
    expect(token?.attributes('type')).toBe('password')
    expect((token?.element as HTMLInputElement).value).toBe('visible-external-token')

    workspace.snapshot = {
      ...(workspace.snapshot as any),
      preferences: {
        ...(workspace.snapshot as any).preferences,
        security_settings: {
          external_api_enabled: true,
          external_api_token_configured: true,
          external_api_project_allowed_roots: ['C:\\projects'],
        },
      },
    } as any
    await nextTick()
    expect((token?.element as HTMLInputElement).value).toBe('visible-external-token')
  })

  it('安全设置显示不安全 TLS 的高风险开关和说明', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: { preferences_auto_save: false },
        compile_settings: {},
        security_settings: { allow_insecure_tls: true },
        python_runtime_settings: {},
        graph_settings: {},
        other_settings: {},
      },
      graph_workspace: { preferences_state: {} },
    } as any

    const wrapper = mount(PreferencesPanel, { global: { plugins: [pinia] } })
    await flushPromises()
    await wrapper.get('.pref-nav-item:nth-child(2)').trigger('click')
    await nextTick()

    const field = wrapper.findAll('.pref-field').find((item) => item.text().includes('允许不安全 TLS'))
    expect(field?.text()).toContain('高风险')
    expect(field?.text()).toContain('跳过 HTTPS 证书校验')
    expect((field?.find('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('清除外部 API Token 时不同时提交已回填的 Token', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: { preferences_auto_save: false },
        compile_settings: {},
        security_settings: {
          external_api_enabled: true,
          external_api_token_configured: true,
          external_api_project_allowed_roots: [],
        },
        python_runtime_settings: {},
        graph_settings: {},
        other_settings: {},
      },
      graph_workspace: { preferences_state: {} },
    } as any
    apiMocks.fetchExternalApiPreferences.mockResolvedValue({
      enabled: true,
      token: 'visible-external-token',
      token_configured: true,
      external_api_port: 0,
      project_allowed_roots: [],
    })
    apiMocks.postExternalApiPreferences.mockResolvedValue({
      enabled: false,
      token: null,
      token_configured: false,
      external_api_port: 0,
      project_allowed_roots: [],
    })
    apiMocks.postPreferences.mockResolvedValue({ preferences: { security_settings: {} } })
    workspace.refreshSnapshot = vi.fn().mockResolvedValue(undefined)

    const wrapper = mount(PreferencesPanel, { global: { plugins: [createPinia()] } })
    await flushPromises()
    await wrapper.get('.pref-nav-item:nth-child(2)').trigger('click')
    await nextTick()

    const clearField = wrapper.findAll('.pref-field').find((item) => item.text().includes('清除外部 API Token'))
    const clearCheckbox = clearField?.find('input[type="checkbox"]')
    expect(clearCheckbox?.exists()).toBe(true)
    await clearCheckbox?.setValue(true)
    await wrapper.get('.pref-btn-save').trigger('click')
    await flushPromises()

    const requestBody = apiMocks.postExternalApiPreferences.mock.calls[0][0]
    expect(requestBody.clear_token).toBe(true)
    expect(requestBody.token).toBeUndefined()
    const tokenField = wrapper.findAll('.pref-field').find((item) => item.text().includes('外部 API Token'))
    expect((tokenField?.find('input').element as HTMLInputElement).value).toBe('')
  })

  it('自动保存后不会用缺失字段覆盖尚未裁决的表单值', async () => {
    vi.useFakeTimers()
    const workspace = useWorkspaceStore()
    workspace.snapshot = {
      preferences: {
        program_settings: {
          language: 'zh-CN', theme: 'light', preferences_auto_save: true,
          resource_language: 'zh-CN', default_window_size: { width: 1440, height: 900 },
        }, compile_settings: {}, security_settings: {}, python_runtime_settings: {}, graph_settings: {}, other_settings: {},
      }, graph_workspace: { preferences_state: {} },
    } as any
    workspace.refreshSnapshot = vi.fn().mockResolvedValue(undefined)
    apiMocks.postPreferences.mockResolvedValue({ preferences: { program_settings: { preferences_auto_save: true, resource_language: 'zh-CN' } } })
    apiMocks.fetchPreferences.mockResolvedValue({ preferences: { program_settings: { preferences_auto_save: true, resource_language: 'zh-CN' } } })

    const wrapper = mount(PreferencesPanel, { global: { plugins: [createPinia()] } })
    await nextTick()
    const themeSelect = wrapper.findAll('select').find((item) => item.findAll('option').some((option) => option.text() === 'system'))
    await themeSelect?.setValue('dark')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(themeSelect?.element.value).toBe('dark')
    vi.useRealTimers()
  })

  it('恢复节点图设置导航，并优先显示 snapshot 中的 graph_preferences', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = buildSnapshot()

    const wrapper = mount(PreferencesPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await flushPromises()
    await nextTick()

    const nodegraphNav = wrapper.findAll('.pref-nav-item')
      .find(item => item.text().includes('节点图设置'))
    expect(nodegraphNav).toBeTruthy()

    await nodegraphNav!.trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('显示节点 ID')
    const snapToGridCheckbox = wrapper.findAll('.pref-field input[type="checkbox"]').find((item) => {
      const label = item.element.closest('.pref-field')?.querySelector('.pref-field-label')?.textContent
      return label?.includes('吸附网格')
    })
    expect((snapToGridCheckbox?.element as HTMLInputElement).checked).toBe(false)
  })

  it('保存节点图设置时走 graph scope，并写入 /editor_preferences/<field>', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = buildSnapshot()
    workspace.refreshSnapshot = vi.fn().mockResolvedValue(undefined)
    apiMocks.fetchConfigValues.mockResolvedValue({
      scope: 'graph',
      values: {
        editor_preferences: {
          snap_to_grid: true,
          grid_enabled: false,
        },
      },
    })
    apiMocks.patchConfigValues.mockResolvedValue({
      scope: 'graph',
      values: {
        editor_preferences: {
          show_node_id_on_node: true,
        },
      },
    })

    const wrapper = mount(PreferencesPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await flushPromises()
    await nextTick()

    const nodegraphNav = wrapper.findAll('.pref-nav-item')
      .find(item => item.text().includes('节点图设置'))
    await nodegraphNav!.trigger('click')
    await nextTick()

    const nodeIdCheckbox = wrapper.findAll('.pref-field input[type="checkbox"]').find((item) => {
      const label = item.element.closest('.pref-field')?.querySelector('.pref-field-label')?.textContent
      return label?.includes('显示节点 ID')
    })
    expect(nodeIdCheckbox).toBeTruthy()
    await nodeIdCheckbox!.setValue(true)
    await wrapper.get('.pref-btn-save').trigger('click')

    expect(apiMocks.patchConfigValues).toHaveBeenCalledWith({
      scope: 'graph',
      operations: expect.arrayContaining([
        {
          op: 'replace',
          path: '/editor_preferences/show_node_id_on_node',
          value: true,
        },
      ]),
      confirm_high_risk: false,
    })
  })

  it('重置节点图设置时只重置 graph scope', async () => {
    const workspace = useWorkspaceStore()
    workspace.snapshot = buildSnapshot()
    workspace.refreshSnapshot = vi.fn().mockResolvedValue(undefined)
    apiMocks.fetchConfigValues.mockResolvedValue({
      scope: 'graph',
      values: { editor_preferences: { snap_to_grid: false } },
    })
    apiMocks.resetConfigValues.mockResolvedValue({
      scope: 'graph',
      values: { editor_preferences: { snap_to_grid: true } },
    })

    const wrapper = mount(PreferencesPanel, {
      global: { plugins: [createPinia()] },
    })
    await flushPromises()
    const nodegraphNav = wrapper.findAll('.pref-nav-item')
      .find(item => item.text().includes('节点图设置'))
    await nodegraphNav!.trigger('click')
    await wrapper.get('.pref-btn-reset-all').trigger('click')
    await flushPromises()

    expect(apiMocks.resetConfigValues).toHaveBeenCalledWith('graph')
    expect(apiMocks.postPreferencesReset).not.toHaveBeenCalled()
  })
})
