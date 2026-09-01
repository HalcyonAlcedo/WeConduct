import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const dockMock = vi.hoisted(() => ({
  register: vi.fn(),
  setPanelTitle: vi.fn(),
  zones: {
    center: { panels: [] as Array<{ id: string }>, activePanelId: null as string | null },
  },
  addToZone: vi.fn(),
}))

vi.mock('@/stores/dockStore', () => ({ useDockStore: () => dockMock }))
vi.mock('@/stores/resourceStore', () => ({ useResourceStore: () => ({ refreshAll: vi.fn() }) }))
vi.mock('@/i18n', () => ({ t: (_key: string, fallback: string) => fallback }))
vi.mock('@/components/panels/DockLayout.vue', () => ({ default: { template: '<div><slot /></div>' } }))
vi.mock('@/components/input/SourceInputPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/output/OutputPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/ComponentLibraryPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/MetadataEditorPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/ResourceManagerPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/TaskExecutionPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/output/graph/GraphCanvasPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/PreferencesPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/ProjectSettingsPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shells/PackagePanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/output/debug/DebugVariablesPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/output/debug/DebugTimelinePanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/output/debug/DebugSnapshotsPanel.vue', () => ({ default: { template: '<div />' } }))

import WorkbenchView from './WorkbenchView.vue'

describe('WorkbenchView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('注册 debugNetwork 面板并写入工作台插槽', async () => {
    mount(WorkbenchView, {
      global: { plugins: [createPinia()] },
    })

    expect(dockMock.register).toHaveBeenCalledWith(expect.objectContaining({ id: 'debugNetwork' }))
    expect(dockMock.register).toHaveBeenCalledWith(expect.objectContaining({ id: 'debugTimeline' }))
  })
})
