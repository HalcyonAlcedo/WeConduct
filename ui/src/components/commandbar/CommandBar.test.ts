import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  postProjectNew: vi.fn(),
  postProjectOpen: vi.fn(),
  postProjectSave: vi.fn(),
  postProjectSaveAs: vi.fn(),
  fetchProject: vi.fn(),
  fetchGraphDocument: vi.fn(),
  fetchRecentProjects: vi.fn().mockResolvedValue({ recent_projects: [] }),
  postRecentProjectRemove: vi.fn(),
  postFileDialog: vi.fn(),
  postReadFile: vi.fn(),
  postGraphUpgradeApply: vi.fn(),
  postGraphUpgradeRecheck: vi.fn(),
  fetchUpdateStatus: vi.fn(),
  postUpdateCheck: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  postProjectNew: apiMocks.postProjectNew,
  postProjectOpen: apiMocks.postProjectOpen,
  postProjectSave: apiMocks.postProjectSave,
  postProjectSaveAs: apiMocks.postProjectSaveAs,
  fetchProject: apiMocks.fetchProject,
  fetchGraphDocument: apiMocks.fetchGraphDocument,
  fetchRecentProjects: apiMocks.fetchRecentProjects,
  postRecentProjectRemove: apiMocks.postRecentProjectRemove,
  postFileDialog: apiMocks.postFileDialog,
  postReadFile: apiMocks.postReadFile,
  postGraphUpgradeApply: apiMocks.postGraphUpgradeApply,
  postGraphUpgradeRecheck: apiMocks.postGraphUpgradeRecheck,
  fetchUpdateStatus: apiMocks.fetchUpdateStatus,
  postUpdateCheck: apiMocks.postUpdateCheck,
}))

import CommandBar from './CommandBar.vue'

describe('CommandBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('帮助菜单显示检查更新入口', async () => {
    const wrapper = mount(CommandBar, {
      global: {
        plugins: [createPinia()],
      },
    })

    await wrapper.find('button.cmd-item').trigger('click')
    await wrapper.findAll('button.cmd-item')[4].trigger('click')

    expect(wrapper.text()).toContain('检查更新')
  })

  it('使用正式发布页作为默认更新链接', async () => {
    const wrapper = mount(CommandBar, {
      global: {
        plugins: [createPinia()],
      },
    })

    expect((wrapper.vm as any).defaultReleaseUrl).toBe('https://github.com/HalcyonAlcedo/WeConduct/releases')
  })
})
