import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({
  postResourceEnabled: vi.fn(),
  postResourceTags: vi.fn(),
  postCreateEmptyCustomComponent: vi.fn(),
  postResourceDelete: vi.fn(),
  postResourceMetadata: vi.fn(),
  postFileDialog: vi.fn(),
  postSubgraphAssetExport: vi.fn(),
  postSubgraphAssetImportPreflight: vi.fn(),
  postSubgraphAssetImportCommit: vi.fn(),
}))

const resourceState = vi.hoisted(() => ({
  resources: [] as any[],
  resourceFacets: null as any,
  refreshAll: vi.fn(),
}))

const graphWorkspaceState = vi.hoisted(() => ({
  loadGraph: vi.fn(),
  syncSource: vi.fn(),
  refreshGraphDocuments: vi.fn(),
}))

const toastState = vi.hoisted(() => ({
  info: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/services/api', () => apiMocks)
vi.mock('@/stores/resourceStore', () => ({ useResourceStore: () => resourceState }))
vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphWorkspaceState,
}))
vi.mock('@/stores/toastStore', () => ({ useToastStore: () => toastState }))
vi.mock('@/i18n', () => ({ t: (_key: string, fallback: string) => fallback }))

import ResourceManagerPanel from './ResourceManagerPanel.vue'

const customResource = {
  resource_id: 'custom_node_graph:demo',
  resource_key: 'custom_node_graph:demo',
  resource_type: 'custom_node_graph',
  display_name: '可共享子图',
  enabled: true,
  origin: 'project',
}

function preflight(overrides: Record<string, unknown> = {}) {
  return {
    status: 'preflight',
    can_import: true,
    root_resource: customResource,
    dependency_count: 0,
    builtin_component_dependencies: [],
    embedded_resources: [],
    graph_compatibility: [],
    conflicts: [],
    diagnostics: [],
    ...overrides,
  }
}

function findButton(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find((button) => button.text() === text)
}

function mountPanel() {
  return mount(ResourceManagerPanel, {
    global: {
      stubs: { Teleport: true },
    },
  })
}

describe('ResourceManagerPanel subgraph assets', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resourceState.resources = [customResource]
    resourceState.resourceFacets = null
    resourceState.refreshAll.mockResolvedValue(undefined)
    graphWorkspaceState.refreshGraphDocuments.mockResolvedValue(undefined)
    apiMocks.postFileDialog.mockResolvedValue({ status: 'cancelled', mode: 'open_file', paths: [] })
  })

  it('从用户组件行选择路径并导出 .wcsubgraph 资源包', async () => {
    apiMocks.postFileDialog.mockResolvedValue({
      status: 'selected',
      mode: 'save_file',
      paths: ['C:\\exports\\shared.wcsubgraph'],
    })
    apiMocks.postSubgraphAssetExport.mockResolvedValue({
      status: 'exported',
      resource: customResource,
      output_path: 'C:\\exports\\shared.wcsubgraph',
    })
    const wrapper = mountPanel()
    await flushPromises()

    const exportButton = findButton(wrapper, '导出')
    expect(exportButton).toBeTruthy()
    await exportButton!.trigger('click')
    await flushPromises()

    expect(apiMocks.postFileDialog).toHaveBeenCalledWith({
      mode: 'save_file',
      title: '导出子图资源包',
      default_path: '可共享子图.wcsubgraph',
      file_types: ['WeConduct 子图资源包 (*.wcsubgraph)'],
    })
    expect(apiMocks.postSubgraphAssetExport).toHaveBeenCalledWith({
      resource_id: customResource.resource_id,
      output_path: 'C:\\exports\\shared.wcsubgraph',
    })
  })

  it('预检通过后确认导入并刷新资源与组件库', async () => {
    apiMocks.postFileDialog.mockResolvedValue({
      status: 'selected',
      mode: 'open_file',
      paths: ['C:\\imports\\shared.wcsubgraph'],
    })
    apiMocks.postSubgraphAssetImportPreflight.mockResolvedValue(preflight({
      builtin_component_dependencies: [{
        resource_id: 'builtin:python.run',
        resource_key: 'python.run',
        resource_type: 'builtin_component',
      }],
      graph_compatibility: [{
        resource_id: customResource.resource_id,
        from_version: '0.5.2',
        to_version: '0.9.0',
        status: 'upgrade_available',
        upgraded: true,
      }],
    }))
    apiMocks.postSubgraphAssetImportCommit.mockResolvedValue({
      status: 'imported',
      resource: customResource,
      registry_revision: 3,
      conflict_policy: 'abort',
      resource_id_map: {},
      embedded_resources: [],
    })
    const wrapper = mountPanel()
    await flushPromises()

    const importButton = findButton(wrapper, '导入子图')
    expect(importButton).toBeTruthy()
    await importButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('子图导入预检')
    expect(wrapper.text()).toContain('可共享子图')
    expect(wrapper.text()).toContain('内置依赖')
    expect(wrapper.text()).toContain('已升级图')
    await wrapper.get('.rmp-subgraph-commit').trigger('click')
    await flushPromises()

    expect(apiMocks.postSubgraphAssetImportCommit).toHaveBeenCalledWith({
      import_path: 'C:\\imports\\shared.wcsubgraph',
      conflict_policy: 'abort',
    })
    expect(resourceState.refreshAll).toHaveBeenCalled()
    expect(graphWorkspaceState.refreshGraphDocuments).toHaveBeenCalled()
  })

  it('冲突时要求明确选择重命名或替换策略后才能提交', async () => {
    apiMocks.postFileDialog.mockResolvedValue({
      status: 'selected',
      mode: 'open_file',
      paths: ['C:\\imports\\conflicted.wcsubgraph'],
    })
    apiMocks.postSubgraphAssetImportPreflight.mockResolvedValue(preflight({
      can_import: false,
      conflicts: [{
        resource_id: customResource.resource_id,
        resource_key: customResource.resource_key,
        resource_type: 'custom_node_graph',
      }],
    }))
    apiMocks.postSubgraphAssetImportCommit.mockResolvedValue({
      status: 'imported',
      resource: customResource,
      registry_revision: 3,
      conflict_policy: 'rename',
      resource_id_map: {},
      embedded_resources: [],
    })
    const wrapper = mountPanel()
    await flushPromises()

    await findButton(wrapper, '导入子图')!.trigger('click')
    await flushPromises()

    expect((wrapper.get('.rmp-subgraph-commit').element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get('.rmp-subgraph-policy').setValue('rename')
    const commitButton = wrapper.get('.rmp-subgraph-commit')
    expect((commitButton.element as HTMLButtonElement).disabled).toBe(false)
    await commitButton.trigger('click')
    await flushPromises()

    expect(apiMocks.postSubgraphAssetImportCommit).toHaveBeenCalledWith({
      import_path: 'C:\\imports\\conflicted.wcsubgraph',
      conflict_policy: 'rename',
    })
  })
})
