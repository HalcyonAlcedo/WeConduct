import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const graphWorkspaceState = vi.hoisted(() => ({
  viewport: { zoom: 1 },
  isGraphEditable: true,
  graphModel: {
    nodes: [
      {
        node_id: 'node-a',
        node_kind: 'control.jump_to_step',
        node_config: {
          retries: 2,
        },
        ports: [],
      },
    ],
    edges: [],
  } as any,
  parameterSchemas: {},
  updateNode: vi.fn(),
}))

const workspaceSnapshotState = vi.hoisted(() => ({
  snapshot: {
    graph_workspace: {
      graph_preferences: {
        show_node_id_on_node: false,
        show_disabled_resource_badge: false,
        show_inline_config_summary: false,
      },
    },
  } as any,
}))

const resourceState = vi.hoisted(() => ({
  getResourceEnabledState: vi.fn(() => false),
}))

const debugState = vi.hoisted(() => ({
  projection: null as any,
  hasBreakpoint: vi.fn(() => false),
  hasRecordFrame: vi.fn(() => false),
}))

vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphWorkspaceState,
}))
vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: () => workspaceSnapshotState,
}))
vi.mock('@/stores/resourceStore', () => ({
  useResourceStore: () => resourceState,
}))
vi.mock('@/stores/debugStore', () => ({
  useDebugStore: () => debugState,
}))
vi.mock('@/stores/toastStore', () => ({
  useToastStore: () => ({
    info: vi.fn(),
    error: vi.fn(),
  }),
}))
vi.mock('@/services/api', () => ({
  postFileDialog: vi.fn(),
  postGraphNormalize: vi.fn(),
}))
vi.mock('@/config/fieldTemplates', () => ({
  PARAM_TEMPLATES: {},
}))
vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({ setup() { return () => h('div') } }),
  Position: { Left: 'left', Right: 'right' },
}))

import BaseNode from './BaseNode.vue'

describe('BaseNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    workspaceSnapshotState.snapshot.graph_workspace.graph_preferences = {
      show_node_id_on_node: false,
      show_disabled_resource_badge: false,
      show_inline_config_summary: false,
    }
  })

  it('节点图视觉偏好关闭时隐藏节点 ID、禁用徽章和内联配置摘要', () => {
    const wrapper = mount(BaseNode, {
      props: {
        id: 'node-a',
        data: {
          label: '节点A',
          nodeId: 'node-a',
          kind: 'control',
          expansionRole: 'main',
          nodeKind: 'control.jump_to_step',
          ports: [],
        },
      },
    })

    expect(wrapper.find('.vf-node-id').exists()).toBe(false)
    expect(wrapper.find('.vf-disabled-badge').exists()).toBe(false)
    expect(wrapper.find('.vf-config').exists()).toBe(false)
  })

  it('显示内联节点配置时不重复显示敏感数据提示', () => {
    workspaceSnapshotState.snapshot.graph_workspace.graph_preferences.show_inline_config_summary = true

    const wrapper = mount(BaseNode, {
      props: {
        id: 'node-a',
        data: {
          label: '节点A',
          nodeId: 'node-a',
          kind: 'control',
          expansionRole: 'main',
          nodeKind: 'control.jump_to_step',
          ports: [],
        },
      },
    })

    expect(wrapper.find('.node-plaintext-risk-notice').exists()).toBe(false)
  })
})
