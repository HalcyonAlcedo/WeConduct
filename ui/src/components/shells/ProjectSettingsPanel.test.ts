import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const apiMocks = vi.hoisted(() => ({
  fetchProjectSettings: vi.fn(),
  postProjectSettings: vi.fn(),
  postRuntimeDefaults: vi.fn(),
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
  fetchProjectSettings: apiMocks.fetchProjectSettings,
  postProjectSettings: apiMocks.postProjectSettings,
  postRuntimeDefaults: apiMocks.postRuntimeDefaults,
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

function buildProjectSettingsResponse() {
  return {
    project_settings: {
      project_settings_schema_version: 1,
      project_identity: { name: 'demo-project' },
      runtime_defaults: {
        initial_variables: {},
        browser_config: { headless: true, slow_mo_ms: 0 },
        execution_defaults: { default_timeout_ms: 30000, default_retry_count: 0 },
      },
      packaging: { default_output_name: 'demo.wcrun' },
      external_resources: [],
      resource_policy: { embedded_resources: [], external_resource_bindings: [] },
      compile_profile: {
        source_of_truth: 'saved_project_only',
        inject_project_runtime_defaults_into_main_flow_start: true,
      },
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
      debug_profile: {
        history_retention_limit: 10,
      },
    },
    state: {
      loaded: true,
      source: 'project_file',
      project_file_path: 'I:\\demo\\project.weconduct.json',
      session_dir: null,
      project_settings_path: 'I:\\demo\\project-settings.json',
      is_dirty: false,
    },
    python_runtime_summary: {
      enabled: false,
      health_status: 'unknown',
      health_message: null,
      runtime_root: null,
      python_executable: null,
      manifest_hash: null,
      cache_location_mode: null,
      project_cache_mode: null,
      package_embed_mode: null,
    },
    security_requirement_summary: null,
  } as any
}

describe('ProjectSettingsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMocks.fetchProjectSettings.mockResolvedValue(buildProjectSettingsResponse())
  })

  it('显示调试历史保留上限字段', async () => {
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
    } as any

    const wrapper = mount(ProjectSettingsPanel, {
      global: {
        plugins: [createPinia()],
      },
    })

    await nextTick()
    await Promise.resolve()
    await nextTick()
    await wrapper.get('.psp-nav-item:nth-child(4)').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('调试历史保留上限')
  })
})
