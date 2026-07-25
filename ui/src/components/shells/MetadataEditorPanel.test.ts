import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const graphWorkspaceState = vi.hoisted(() => ({
  isGraphEditable: true,
  graphModel: {
    nodes: [
      {
        node_id: 'node-a',
        node_kind: 'control.jump_to_step',
        lowered_kind: 'control',
        display_name: '节点A',
        source_anchor_ref: 'node-a',
        expansion_role: 'main',
        node_config: { retries: 2 },
        ports: [],
      },
    ],
    edges: [],
  } as any,
  parameterSchemas: {},
  updateNode: vi.fn(),
}))

const graphStoreState = vi.hoisted(() => ({
  selectedNode: 'node-a',
  selectNode: vi.fn(),
  selectGraphModel: vi.fn(({ workspaceModel }: { workspaceModel: object }) => ({
    model: workspaceModel,
  })),
}))

vi.mock('@/stores/graphStore', () => ({
  useGraphStore: () => graphStoreState,
}))
vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphWorkspaceState,
}))
vi.mock('@/stores/compilationStore', () => ({
  useCompilationStore: () => ({ outcome: null }),
}))
vi.mock('@/stores/resourceStore', () => ({
  useResourceStore: () => ({ resources: [] }),
}))
vi.mock('@/stores/toastStore', () => ({
  useToastStore: () => ({ info: vi.fn(), error: vi.fn() }),
}))
vi.mock('@/services/api', () => ({
  postFileDialog: vi.fn(),
  postGraphNormalize: vi.fn(),
}))
vi.mock('@/i18n', () => ({
  t: (_key: string, fallback: string) => fallback,
  tr: (_key: string, fallback: string) => fallback,
}))
vi.mock('@/components/common/PlaceholderBanner.vue', () => ({
  default: defineComponent({ setup: () => () => h('div') }),
}))
vi.mock('@/components/input/MonacoEditor.vue', () => ({
  default: defineComponent({ setup: () => () => h('div') }),
}))

import MetadataEditorPanel from './MetadataEditorPanel.vue'

describe('MetadataEditorPanel', () => {
  it('在节点配置编辑区域持续显示明文敏感数据风险提示', () => {
    const wrapper = mount(MetadataEditorPanel)

    expect(wrapper.get('.node-plaintext-risk-notice').text()).toContain('节点配置会随项目保存')
  })
})
