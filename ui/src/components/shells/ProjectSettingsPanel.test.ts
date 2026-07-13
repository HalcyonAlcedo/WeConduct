import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => ({
  fetchConfigValues: vi.fn(),
  patchConfigValues: vi.fn(),
  fetchPythonRuntime: vi.fn(),
  postOpenPath: vi.fn(),
  postFileDialog: vi.fn(),
  postPythonRuntimeHealthCheck: vi.fn(),
  postPythonRuntimePrepare: vi.fn(),
  postPythonRuntimeRebuild: vi.fn(),
  postPythonRuntimeClear: vi.fn(),
  postPythonRuntimeExportBundle: vi.fn(),
  postSecurityEnableRequired: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchConfigValues: apiMocks.fetchConfigValues,
  patchConfigValues: apiMocks.patchConfigValues,
  fetchPythonRuntime: apiMocks.fetchPythonRuntime,
  postOpenPath: apiMocks.postOpenPath,
  postFileDialog: apiMocks.postFileDialog,
  postPythonRuntimeHealthCheck: apiMocks.postPythonRuntimeHealthCheck,
  postPythonRuntimePrepare: apiMocks.postPythonRuntimePrepare,
  postPythonRuntimeRebuild: apiMocks.postPythonRuntimeRebuild,
  postPythonRuntimeClear: apiMocks.postPythonRuntimeClear,
  postPythonRuntimeExportBundle: apiMocks.postPythonRuntimeExportBundle,
  postSecurityEnableRequired: apiMocks.postSecurityEnableRequired,
}))

import ProjectSettingsPanel from './ProjectSettingsPanel.vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'

function buildProjectConfigResponse() {
  return {
    scope: 'project',
    values: {
      identity: { name: 'demo-project' },
      packaging: {
        default_output_name: 'demo.wcrun',
        include_embedded_resources: true,
      },
      resources: {
        external_resources: [],
        embedded_resources: [],
      },
      python_profile: {
        runtime_enabled: false,
        python_version_spec: '3.13',
        interpreter_strategy: 'bundled',
        custom_python_path: null,
        cache_location_mode: 'software_cache',
        project_cache_mode: 'wheelhouse_rebuild',
        requirements_source_mode: 'inline',
        requirements_inline: [],
        requirements_file_path: null,
        lock_file_path: null,
        index_strategy: 'default',
        custom_index_url: null,
        auto_prepare_on_run: true,
        package_embed_mode: 'wheelhouse_rebuild',
        materialized_runtime_hash: null,
        last_health_status: 'unknown',
        last_health_message: null,
      },
      debug: {
        history_retention_limit: 10,
      },
    },
  } as any
}

function buildGraphConfigResponse() {
  return {
    scope: 'graph',
    values: {
      entrypoint_runtime: {
        initial_variables: {},
        browser_config: { headless: true, slow_mo_ms: 0 },
        execution_defaults: { default_timeout_ms: 30000, default_retry_count: 0 },
      },
    },
  } as any
}

function buildPythonRuntimeResponse() {
  return {
    python_runtime_profile: {
      runtime_enabled: false,
      python_version_spec: '3.13',
      interpreter_strategy: 'bundled',
      custom_python_path: null,
      cache_location_mode: 'software_cache',
      project_cache_mode: 'wheelhouse_rebuild',
      requirements_source_mode: 'inline',
      requirements_inline: [],
      requirements_file_path: null,
      lock_file_path: null,
      index_strategy: 'default',
      custom_index_url: null,
      auto_prepare_on_run: true,
      package_embed_mode: 'wheelhouse_rebuild',
      materialized_runtime_hash: null,
      last_health_status: 'unknown',
      last_health_message: null,
    },
    runtime_status: {
      health_status: 'unknown',
      health_message: null,
      runtime_root: null,
      python_executable: null,
      manifest_hash: null,
      cache_location_mode: null,
      project_cache_mode: null,
    },
    diagnostics: [],
  } as any
}

function mountWithWorkspaceSnapshot() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const workspace = useWorkspaceStore()
  workspace.snapshot = {
    project: {
      project_id: 'proj-1',
      project_name: 'demo-project',
    },
      project_settings: {
        source_of_truth: 'project_directory',
        state_source: 'project_settings',
        project_settings_schema_version: 1,
        is_dirty: false,
      },
      security_requirement_summary: {
        ready: false,
        blocked_count: 1,
        blocked_entries: [{ field: 'confirm_high_risk_actions', display_name: '确认高风险操作' }],
      },
    } as any
  workspace.refreshSnapshot = vi.fn().mockResolvedValue(undefined)

  const wrapper = mount(ProjectSettingsPanel, {
    global: {
      plugins: [pinia],
    },
  })

  return { wrapper, workspace }
}

describe('ProjectSettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchConfigValues.mockImplementation(async (scope: string) => {
      if (scope === 'project') {
        return buildProjectConfigResponse()
      }
      if (scope === 'graph') {
        return buildGraphConfigResponse()
      }
      throw new Error(`unexpected scope: ${scope}`)
    })
    apiMocks.fetchPythonRuntime.mockResolvedValue(buildPythonRuntimeResponse())
    apiMocks.patchConfigValues.mockImplementation(async ({ scope }: { scope: string }) => (
      scope === 'project' ? buildProjectConfigResponse() : buildGraphConfigResponse()
    ))
  })

  it('显示调试历史保留上限字段', async () => {
    const { wrapper } = mountWithWorkspaceSnapshot()

    await nextTick()
    await Promise.resolve()
    await nextTick()
    await wrapper.get('.psp-nav-item:nth-child(4)').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('调试历史保留上限')
    expect(wrapper.text()).toContain('确认高风险操作')
  })

  it('保存全部设置时分别提交 project scope 和 graph scope，并只提交 entrypoint_runtime 允许字段', async () => {
    const { wrapper } = mountWithWorkspaceSnapshot()

    await nextTick()
    await Promise.resolve()
    await nextTick()

    const nameInput = wrapper.findAll('input.psp-input')[0]
    await nameInput.setValue('renamed-project')

    await wrapper.get('.psp-nav-item:nth-child(2)').trigger('click')
    await nextTick()
    await wrapper.get('.psp-add').trigger('click')
    await nextTick()

    const runtimeInputs = wrapper.findAll('.psp-var-row input.psp-input')
    await runtimeInputs[0].setValue('token')
    await runtimeInputs[1].setValue('abc')
    await runtimeInputs[0].trigger('change')
    await runtimeInputs[1].trigger('change')

    const runtimeCheckbox = wrapper.get('input[type="checkbox"]')
    await runtimeCheckbox.setValue(false)
    const runtimeNumbers = wrapper.findAll('input[type="number"]')
    await runtimeNumbers[0].setValue('125')

    await wrapper.get('.psp-ft .psp-btn-save').trigger('click')

    expect(apiMocks.patchConfigValues).toHaveBeenCalledTimes(2)
    expect(apiMocks.patchConfigValues).toHaveBeenNthCalledWith(1, expect.objectContaining({
      scope: 'project',
      operations: expect.arrayContaining([
        { op: 'replace', path: '/identity/name', value: 'renamed-project' },
        { op: 'replace', path: '/debug/history_retention_limit', value: 10 },
        { op: 'replace', path: '/resources/external_resources', value: [] },
        { op: 'replace', path: '/resources/embedded_resources', value: [] },
        { op: 'replace', path: '/packaging/default_output_name', value: 'demo.wcrun' },
        { op: 'replace', path: '/packaging/include_embedded_resources', value: true },
        { op: 'replace', path: '/python_profile/python_version_spec', value: '3.13' },
      ]),
      confirm_high_risk: false,
    }))
    expect(apiMocks.patchConfigValues).toHaveBeenNthCalledWith(2, {
      scope: 'graph',
      operations: [
        {
          op: 'replace',
          path: '/entrypoint_runtime/initial_variables',
          value: { token: 'abc' },
        },
        {
          op: 'replace',
          path: '/entrypoint_runtime/browser_config',
          value: { headless: false, slow_mo_ms: 125 },
        },
      ],
      confirm_high_risk: false,
    })
    expect(apiMocks.fetchPythonRuntime).toHaveBeenCalledTimes(1)
  })

  it('未注册控件保持禁用显示', async () => {
    const { wrapper } = mountWithWorkspaceSnapshot()

    await nextTick()
    await Promise.resolve()
    await nextTick()

    await wrapper.get('.psp-nav-item:nth-child(2)').trigger('click')
    await nextTick()
    const runtimeNumbers = wrapper.findAll('input[type="number"]')
    expect(runtimeNumbers[1].attributes('disabled')).toBeDefined()
    expect(runtimeNumbers[2].attributes('disabled')).toBeDefined()

    await wrapper.get('.psp-nav-item:nth-child(4)').trigger('click')
    await nextTick()
    const compileCheckbox = wrapper.get('.psp-field input[type="checkbox"]')
    expect(compileCheckbox.attributes('disabled')).toBeDefined()
  })
})
