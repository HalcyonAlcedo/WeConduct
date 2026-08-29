import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

const workspaceSnapshotState = vi.hoisted(() => ({
  snapshot: {
    graph_workspace: {
      graph_preferences: {
        snap_to_grid: false,
        grid_enabled: false,
        auto_open_node_on_drop: false,
        confirm_delete_node: true,
      },
    },
  } as any,
}))

const compilationState = vi.hoisted(() => ({
  outcome: null as any,
}))

const debugState = vi.hoisted(() => ({
  activeSession: null as any,
  hasBreakpoint: vi.fn(() => false),
  hasRecordFrame: vi.fn(() => false),
  getEffectiveDebuggerConfig: vi.fn(() => ({})),
  getDebuggerConfig: vi.fn(() => ({})),
  toggleBreakpointConfig: vi.fn((cfg: any) => cfg),
  setBreakpointPauseTiming: vi.fn((cfg: any) => cfg),
  toggleRecordFrameConfig: vi.fn((cfg: any) => cfg),
  applyNodeDebuggerConfig: vi.fn(),
}))

const graphWorkspaceState = vi.hoisted(() => ({
  isGraphEditable: true,
  isLoaded: true,
  graphModel: {
    nodes: [
      {
        node_id: 'node-a',
        display_name: '节点A',
        node_kind: 'data.set_variable',
        node_config: {},
        position: { x: 100, y: 100 },
        ports: [],
      },
    ],
    edges: [],
  } as any,
  addNode: vi.fn(),
  removeNode: vi.fn(),
  removeEdge: vi.fn(),
  updateEdgeRelation: vi.fn(),
  updateViewport: vi.fn(),
  updateNodePosition: vi.fn(),
  addEdge: vi.fn(),
  pasteNode: vi.fn(),
  pushUndo: vi.fn(),
  markChanged: vi.fn(),
  rawViewport: null as { x: number; y: number; zoom: number } | null,
  setRawViewport: vi.fn(),
}))

const graphStoreState = vi.hoisted(() => ({
  selectGraphModel: vi.fn(({ workspaceModel }: any) => ({ model: workspaceModel })),
  toVueFlow: vi.fn(() => ({
    nodes: [
      {
        id: 'node-a',
        position: { x: 0, y: 0 },
        data: { label: '节点A', nodeId: 'node-a', kind: 'execution', expansionRole: 'x', ports: [] },
      },
    ],
    edges: [],
  })),
  selectNode: vi.fn(),
}))

const dockState = vi.hoisted(() => ({
  isPanelVisible: vi.fn(() => true),
  restorePanel: vi.fn(),
}))

const toastState = vi.hoisted(() => ({
  info: vi.fn(),
  error: vi.fn(),
}))

const diagnosticsState = vi.hoisted(() => ({
  visibleEntries: [] as any[],
}))

const vueFlowState = vi.hoisted(() => ({
  props: null as Record<string, unknown> | null,
  nodes: [] as any[],
  updateNode: vi.fn(),
  emitNodesInitialized: null as (() => void) | null,
}))

const backgroundState = vi.hoisted(() => ({
  props: null as Record<string, unknown> | null,
}))

vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: () => workspaceSnapshotState,
}))
vi.mock('@/stores/compilationStore', () => ({
  useCompilationStore: () => compilationState,
}))
vi.mock('@/stores/debugStore', () => ({
  useDebugStore: () => debugState,
}))
vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => graphWorkspaceState,
}))
vi.mock('@/stores/graphStore', () => ({
  useGraphStore: () => graphStoreState,
}))
vi.mock('@/stores/dockStore', () => ({
  useDockStore: () => dockState,
}))
vi.mock('@/stores/toastStore', () => ({
  useToastStore: () => toastState,
}))
vi.mock('@/stores/projectDiagnosticsStore', () => ({
  useProjectDiagnosticsStore: () => diagnosticsState,
}))
vi.mock('@vue-flow/core', () => ({
  VueFlow: defineComponent({
    props: ['snapToGrid', 'snapGrid', 'defaultViewport', 'fitViewOnInit'],
    emits: ['node-context-menu', 'viewport-change', 'connect', 'nodes-initialized', 'node-drag-stop'],
    setup(props, { emit, slots }) {
      vueFlowState.props = props as Record<string, unknown>
      vueFlowState.emitNodesInitialized = () => emit('nodes-initialized')
      return () => h('div', [
        h('button', {
          class: 'emit-node-context-menu',
          onClick: () => emit('node-context-menu', {
            node: { id: 'node-a' },
            event: { preventDefault() {}, clientX: 10, clientY: 20 },
          }),
        }),
        h('button', {
          class: 'emit-viewport-change',
          onClick: () => emit('viewport-change', { x: 12, y: 34, zoom: 1.7 }),
        }),
        h('button', {
          class: 'emit-data-connect',
          onClick: () => emit('connect', {
            source: 'node-a',
            target: 'node-b',
            sourceHandle: 'out:value',
            targetHandle: 'in:value',
          }),
        }),
        h('button', {
          class: 'emit-nodes-initialized',
          onClick: () => emit('nodes-initialized'),
        }),
        h('button', {
          class: 'emit-node-drag-stop',
          onClick: () => emit('node-drag-stop', {
            node: { id: 'node-a', position: { x: 30, y: 40 }, dimensions: { width: 220, height: 120 } },
          }),
        }),
        h('button', {
          class: 'emit-mismatched-connect',
          onClick: () => emit('connect', {
            source: 'node-a',
            target: 'node-b',
            sourceHandle: 'out:value',
            targetHandle: 'in:control',
          }),
        }),
        slots.default?.(),
      ])
    },
  }),
  Handle: defineComponent({ setup() { return () => h('div') } }),
  Position: { Left: 'left', Right: 'right' },
  useVueFlow: () => ({
    setCenter: vi.fn(),
    getNodes: { value: vueFlowState.nodes },
    updateNode: vueFlowState.updateNode,
  }),
}))
vi.mock('@vue-flow/background', () => ({
  Background: defineComponent({
    props: ['gap', 'size', 'patternColor'],
    setup(props) {
      backgroundState.props = props as Record<string, unknown>
      return () => h('div', { class: 'vf-bg-stub' })
    },
  }),
}))
vi.mock('@vue-flow/controls', () => ({
  Controls: defineComponent({ setup() { return () => h('div') } }),
}))
vi.mock('@vue-flow/minimap', () => ({
  MiniMap: defineComponent({ setup() { return () => h('div') } }),
}))

import VueFlowGraph from './VueFlowGraph.vue'

function buildDropEvent() {
  return {
    preventDefault: vi.fn(),
    currentTarget: {
      getBoundingClientRect: () => ({ left: 0, top: 0 }),
    },
    clientX: 80,
    clientY: 120,
    dataTransfer: {
      types: ['application/json'],
      getData: () => JSON.stringify({ resource_key: 'flow.log', display_name: '日志节点' }),
    },
  } as unknown as DragEvent
}

describe('VueFlowGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vueFlowState.props = null
    vueFlowState.nodes = [{
      id: 'node-a', position: { x: 0, y: 0 }, dimensions: { width: 180, height: 56 },
    }]
    vueFlowState.emitNodesInitialized = null
    vueFlowState.updateNode.mockClear()
    backgroundState.props = null
    workspaceSnapshotState.snapshot.graph_workspace.graph_preferences = {
      snap_to_grid: false,
      grid_enabled: false,
      auto_open_node_on_drop: false,
      confirm_delete_node: true,
    }
    graphWorkspaceState.addNode.mockResolvedValue('node-new')
    graphWorkspaceState.rawViewport = null
    diagnosticsState.visibleEntries = []
  })

  it('根据 graph_preferences 控制 snap-to-grid 与 Background 显示', async () => {
    mount(VueFlowGraph)
    await nextTick()

    expect(vueFlowState.props?.snapToGrid).toBe(false)
    expect(backgroundState.props).toBeNull()
  })

  it('auto_open_node_on_drop=false 时只选中节点，不自动打开属性面板', async () => {
    const wrapper = mount(VueFlowGraph)
    await nextTick()

    await wrapper.get('.vf-wrapper').trigger('drop', buildDropEvent())
    await nextTick()

    expect(graphWorkspaceState.addNode).toHaveBeenCalled()
    expect(graphStoreState.selectNode).toHaveBeenCalledWith('node-new')
    expect(dockState.restorePanel).not.toHaveBeenCalled()
  })

  it('confirm_delete_node=false 时右键删除节点直接执行，不走确认弹窗', async () => {
    workspaceSnapshotState.snapshot.graph_workspace.graph_preferences.confirm_delete_node = false
    ;(window as any).__openDeleteConfirm = vi.fn()

    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-node-context-menu').trigger('click')
    await nextTick()

    const deleteButton = wrapper.findAll('.vf-ctxmenu button')
      .find(button => button.text().includes('删除节点'))
    expect(deleteButton).toBeDefined()
    await deleteButton!.trigger('click')

    expect((window as any).__openDeleteConfirm).not.toHaveBeenCalled()
    expect(graphWorkspaceState.removeNode).toHaveBeenCalledWith('node-a')
  })

  it('viewport 变化时缓存原始变换，供 remount 恢复', async () => {
    const wrapper = mount(VueFlowGraph)
    await nextTick()

    await wrapper.get('.emit-viewport-change').trigger('click')

    expect(graphWorkspaceState.setRawViewport).toHaveBeenCalledWith({ x: 12, y: 34, zoom: 1.7 })
  })

  it('无缓存视口时 fit-view-on-init 为 true、使用默认视口', async () => {
    graphWorkspaceState.rawViewport = null
    mount(VueFlowGraph)
    await nextTick()

    expect(vueFlowState.props?.fitViewOnInit).toBe(true)
    expect(vueFlowState.props?.defaultViewport).toEqual({ x: 0, y: 0, zoom: 0.5 })
  })

  it('存在缓存视口时 remount 恢复该视口且不再 fit-view', async () => {
    graphWorkspaceState.rawViewport = { x: 12, y: 34, zoom: 1.7 }
    mount(VueFlowGraph)
    await nextTick()

    expect(vueFlowState.props?.fitViewOnInit).toBe(false)
    expect(vueFlowState.props?.defaultViewport).toEqual({ x: 12, y: 34, zoom: 1.7 })
  })

  it('连接两个数据端口时以 data 层创建边', async () => {
    graphWorkspaceState.graphModel.nodes = [
      {
        node_id: 'node-a', display_name: '来源', node_kind: 'data.get_variable', node_config: {},
        position: { x: 0, y: 0 },
        ports: [{ port_id: 'out:value', direction: 'output', relation_layer: 'data', semantic_slot: 'out.value' }],
      },
      {
        node_id: 'node-b', display_name: '目标', node_kind: 'data.set_variable', node_config: {},
        position: { x: 100, y: 0 },
        ports: [{ port_id: 'in:value', direction: 'input', relation_layer: 'data', semantic_slot: 'in.value' }],
      },
    ]
    const wrapper = mount(VueFlowGraph)
    await nextTick()

    await wrapper.get('.emit-data-connect').trigger('click')

    expect(graphWorkspaceState.addEdge).toHaveBeenCalledWith(expect.objectContaining({
      relation_layer: 'data',
      from_node_id: 'node-a',
      to_node_id: 'node-b',
      from_port_id: 'out:value',
      to_port_id: 'in:value',
    }))
  })

  it('连接不同层级的端口时拒绝创建边', async () => {
    graphWorkspaceState.graphModel.nodes = [
      {
        node_id: 'node-a', display_name: '来源', node_kind: 'data.get_variable', node_config: {},
        position: { x: 0, y: 0 },
        ports: [{ port_id: 'out:value', direction: 'output', relation_layer: 'data', semantic_slot: 'out.value' }],
      },
      {
        node_id: 'node-b', display_name: '目标', node_kind: 'flow.log', node_config: {},
        position: { x: 100, y: 0 },
        ports: [{ port_id: 'in:control', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' }],
      },
    ]
    const wrapper = mount(VueFlowGraph)
    await nextTick()

    await wrapper.get('.emit-mismatched-connect').trigger('click')

    expect(graphWorkspaceState.addEdge).not.toHaveBeenCalled()
    expect(toastState.error).toHaveBeenCalled()
  })

  it('将当前错误诊断映射为画布节点和边的高亮目标', async () => {
    graphWorkspaceState.graphModel = {
      nodes: [
        { node_id: 'node-a', display_name: '来源', node_kind: 'flow.start', node_config: {}, position: { x: 0, y: 0 }, ports: [] },
        { node_id: 'node-b', display_name: '目标', node_kind: 'flow.end', node_config: {}, position: { x: 100, y: 0 }, ports: [] },
      ],
      edges: [{ edge_id: 'edge-invalid', relation_layer: 'control', from_node_id: 'node-a', to_node_id: 'node-b' }],
    } as any
    diagnosticsState.visibleEntries = [{
      diagnostic_id: 'edge-1', stage: 'validate', severity: 'fatal', category: 'graph.edge.invalid',
      message: 'invalid edge', object_ref: 'edge-invalid', trace_ref: null,
      stage_extension: { graph_ref: { edge_id: 'edge-invalid' } }, degraded_extension: null,
    }]

    mount(VueFlowGraph)
    await nextTick()

    const call = graphStoreState.toVueFlow.mock.calls.at(-1) as any[] | undefined
    expect(call?.[2]?.errorEdgeIds).toEqual(new Set(['edge-invalid']))
  })

  it('节点初始化后按动态尺寸局部推开并同步到内存图稿', async () => {
    graphWorkspaceState.graphModel = {
      nodes: [
        { node_id: 'node-a', display_name: '高节点', node_kind: 'x', node_config: {}, position: { x: 100, y: 100 }, ports: [] },
        { node_id: 'node-b', display_name: '矮节点', node_kind: 'y', node_config: {}, position: { x: 100, y: 160 }, ports: [] },
      ],
      edges: [],
    } as any
    vueFlowState.nodes = [
      { id: 'node-a', position: { x: 10, y: 20 }, dimensions: { width: 180, height: 140 } },
      { id: 'node-b', position: { x: 10, y: 80 }, dimensions: { width: 180, height: 40 } },
    ]
    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-nodes-initialized').trigger('click')

    expect(vueFlowState.updateNode).toHaveBeenCalledWith('node-b', { position: { x: 10, y: 176 } })
    expect(graphWorkspaceState.graphModel.nodes[1].position).toEqual({ x: 100, y: 256 })
    expect(graphWorkspaceState.pushUndo).toHaveBeenCalled()
    expect(graphWorkspaceState.markChanged).toHaveBeenCalled()
  })

  it('auto_layout_on_overlap=false 时保留碰撞坐标', async () => {
    workspaceSnapshotState.snapshot.graph_workspace.graph_preferences.auto_layout_on_overlap = false
    graphWorkspaceState.graphModel = {
      nodes: [
        { node_id: 'node-a', position: { x: 100, y: 100 }, ports: [], node_config: {} },
        { node_id: 'node-b', position: { x: 100, y: 160 }, ports: [], node_config: {} },
      ],
      edges: [],
    } as any
    vueFlowState.nodes = [
      { id: 'node-a', position: { x: 10, y: 20 }, dimensions: { width: 180, height: 140 } },
      { id: 'node-b', position: { x: 10, y: 80 }, dimensions: { width: 180, height: 40 } },
    ]
    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-nodes-initialized').trigger('click')

    expect(vueFlowState.updateNode).not.toHaveBeenCalled()
    expect(graphWorkspaceState.pushUndo).not.toHaveBeenCalled()
    expect(graphWorkspaceState.markChanged).not.toHaveBeenCalled()
  })

  it('手动拖拽回写坐标时使用节点实际动态尺寸', async () => {
    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-node-drag-stop').trigger('click')

    expect(graphWorkspaceState.updateNodePosition).toHaveBeenCalledWith('node-a', { x: 140, y: 100 })
  })

})
