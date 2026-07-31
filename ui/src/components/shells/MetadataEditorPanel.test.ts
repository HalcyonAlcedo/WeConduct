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
  it('不在普通节点配置编辑区域显示敏感数据提示', () => {
    const wrapper = mount(MetadataEditorPanel)

    expect(wrapper.find('.npr-notice').exists()).toBe(false)
  })

  it('仅在网络认证配置旁显示敏感数据提示', () => {
    graphWorkspaceState.graphModel.nodes[0] = {
      ...graphWorkspaceState.graphModel.nodes[0],
      node_kind: 'network.http_request',
      node_config: {
        auth: { type: 'bearer', token: 'test-token' },
      },
    }

    const wrapper = mount(MetadataEditorPanel)

    expect(wrapper.get('.npr-notice').text()).toBe('敏感信息建议使用加密参数。')
  })

  it('将待输入字段标为敏感时清除默认值并保留对应输出端口', async () => {
    graphWorkspaceState.updateNode.mockClear()
    graphWorkspaceState.graphModel.nodes[0] = {
      ...graphWorkspaceState.graphModel.nodes[0],
      node_kind: 'input.request',
      node_config: {
        fields: [{
          field_id: 'password', label: '密码', type: 'string', sensitive: false,
          default_value: 'plaintext-default',
        }],
        timeout_seconds: 0,
      },
      ports: [
        { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
        { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
        { port_id: 'timed_out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.timed_out' },
        { port_id: 'out:password', direction: 'output', relation_layer: 'data', semantic_slot: 'out.password' },
      ],
    }

    const wrapper = mount(MetadataEditorPanel)
    const sensitiveCheckbox = wrapper.get('.mep-schema-block input[type="checkbox"]')
    await sensitiveCheckbox.setValue(true)

    expect(graphWorkspaceState.updateNode).toHaveBeenCalledWith('node-a', expect.objectContaining({
      node_config: {
        fields: [{ field_id: 'password', label: '密码', type: 'string', sensitive: true }],
        timeout_seconds: 0,
      },
      ports: expect.arrayContaining([
        expect.objectContaining({ port_id: 'out:password', semantic_slot: 'out.password' }),
      ]),
    }))
  })

  it('允许为 Python 节点显式启用敏感输入读取', async () => {
    graphWorkspaceState.updateNode.mockClear()
    graphWorkspaceState.graphModel.nodes[0] = {
      ...graphWorkspaceState.graphModel.nodes[0],
      node_kind: 'python.run',
      node_config: { code: '', allow_sensitive_values: false },
    }

    const wrapper = mount(MetadataEditorPanel)
    expect(wrapper.text()).toContain('允许 Python 读取敏感输入')
    const sensitiveInputCheckbox = wrapper.get('.mep-cfg-row input[type="checkbox"]')
    await sensitiveInputCheckbox.setValue(true)

    expect(graphWorkspaceState.updateNode).toHaveBeenCalledWith('node-a', {
      node_config: { code: '', allow_sensitive_values: true },
    })
  })

  it('为 Python 节点提供输入、输出和元数据 Schema 编辑器', () => {
    graphWorkspaceState.graphModel.nodes[0] = {
      ...graphWorkspaceState.graphModel.nodes[0],
      node_kind: 'python.run',
      node_config: {
        code: '',
        allow_sensitive_values: false,
        input_schema: {},
        output_schema: {},
        metadata_schema: {},
      },
    }

    const wrapper = mount(MetadataEditorPanel)

    expect(wrapper.text()).toContain('Python 输入字段')
    expect(wrapper.text()).toContain('Python 输出字段')
    expect(wrapper.text()).toContain('Python 元数据字段')
    expect(wrapper.findAll('.mep-om-add')).toHaveLength(3)
  })

  it('为消息节点提供消息文本和严重度配置', () => {
    graphWorkspaceState.graphModel.nodes[0] = {
      ...graphWorkspaceState.graphModel.nodes[0],
      node_kind: 'message.emit',
      node_config: { message: '任务已完成', severity: 'info' },
    }

    const wrapper = mount(MetadataEditorPanel)

    expect(wrapper.text()).toContain('消息')
    expect(wrapper.text()).toContain('等级')
    expect(wrapper.get('.mep-cfg-row select').findAll('option').map(option => option.element.value)).toEqual([
      'info', 'warning', 'error', 'fatal',
    ])
  })
})
