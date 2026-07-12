import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

const compilationState = vi.hoisted(() => ({
  compilePhase: 'completed',
  diagnosticGroups: [
    { stage: 'bind', category: 'bind.failed', severity: 'error', message: 'bind failed', count: 2 },
    { stage: 'parse', category: 'parse.completed', severity: 'info', message: 'parsed source document', count: 1 },
  ],
}))

const runtimeState = vi.hoisted(() => ({
  runtimeTabRequest: 0,
  runtimeDiagnosticGroups: [
    { stage: 'runtime', category: 'runtime.node_failed', severity: 'error', message: 'runtime failed', count: 3 },
  ],
  hasRuntimeDiagnostics: true,
  runtimeLiveStatus: 'failed',
}))

const debugState = vi.hoisted(() => ({
  activeSession: {
    diagnostic_links: [
      { diagnostic_id: 'dbg-1', stage: 'debug', category: 'debug.breakpoint_condition_error', severity: 'error', message: 'condition failed' },
      { diagnostic_id: 'dbg-2', stage: 'parse', category: 'parse.completed', severity: 'info', message: 'parsed source document' },
    ],
  } as any,
  activeSessionStatus: 'paused',
  hasBreakpoint: vi.fn((cfg: any) => !!cfg?.debugger?.breakpoint?.enabled),
  hasRecordFrame: vi.fn((cfg: any) => !!cfg?.debugger?.record_frame?.enabled),
  getDebuggerConfig: vi.fn((cfg: any) => cfg?.debugger || {}),
  getEffectiveDebuggerConfig: vi.fn((cfg: any) => cfg?.debugger || {}),
  toggleBreakpointConfig: vi.fn((cfg: any) => ({ ...cfg, debugger: { ...(cfg?.debugger || {}), breakpoint: { enabled: !(cfg?.debugger?.breakpoint?.enabled) } } })),
  setBreakpointPauseTiming: vi.fn((cfg: any, timing: string) => ({ ...cfg, debugger: { ...(cfg?.debugger || {}), breakpoint: { enabled: true, pause_timing: timing } } })),
  toggleRecordFrameConfig: vi.fn((cfg: any) => ({ ...cfg, debugger: { ...(cfg?.debugger || {}), record_frame: { enabled: !(cfg?.debugger?.record_frame?.enabled) } } })),
  applyNodeDebuggerConfig: vi.fn(),
}))

const workspaceState = vi.hoisted(() => ({
  isGraphEditable: false,
  graphModel: {
    nodes: [
      {
        node_id: 'node-a',
        display_name: '节点A',
        node_kind: 'data.set_variable',
        node_config: {},
        position: { x: 0, y: 0 },
        ports: [],
      },
    ],
    edges: [],
  },
  pushUndo: vi.fn(),
  markChanged: vi.fn(),
  updateEdgeRelation: vi.fn(),
  removeEdge: vi.fn(),
  removeNode: vi.fn(),
  addEdge: vi.fn(),
  updateViewport: vi.fn(),
  updateNodePosition: vi.fn(),
  pasteNode: vi.fn(),
  isLoaded: true,
}))

const graphStoreState = vi.hoisted(() => ({
  selectGraphModel: vi.fn(({ workspaceModel }: any) => ({ model: workspaceModel })),
  toVueFlow: vi.fn(() => ({ nodes: [{ id: 'node-a', position: { x: 0, y: 0 }, data: { label: '节点A', nodeId: 'node-a', kind: 'execution', expansionRole: 'x', ports: [] } }], edges: [] })),
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

vi.mock('@/stores/compilationStore', () => ({
  useCompilationStore: () => compilationState,
}))
vi.mock('@/stores/runtimeStore', () => ({
  useRuntimeStore: () => runtimeState,
}))
vi.mock('@/stores/debugStore', () => ({
  useDebugStore: () => debugState,
}))
vi.mock('@/stores/graphWorkspaceStore', () => ({
  useGraphWorkspaceStore: () => workspaceState,
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
vi.mock('@/stores/resourceStore', () => ({
  useResourceStore: () => ({
    getResourceEnabledState: vi.fn(() => true),
  }),
}))
vi.mock('@/services/api', async () => {
  const actual = await vi.importActual('@/services/api')
  return {
    ...actual,
    postFileDialog: vi.fn(),
    postGraphNormalize: vi.fn(),
  }
})
vi.mock('@/config/fieldTemplates', () => ({
  PARAM_TEMPLATES: {},
}))
vi.mock('@vue-flow/core', () => ({
  VueFlow: defineComponent({
    emits: ['node-context-menu'],
    setup(_, { emit, slots }) {
      return () => h('div', [
        h('button', {
          class: 'emit-node-context-menu',
          onClick: () => emit('node-context-menu', {
            node: { id: 'node-a' },
            event: { preventDefault() {}, clientX: 10, clientY: 20 },
          }),
        }),
        slots.default?.(),
      ])
    },
  }),
  Handle: defineComponent({ setup() { return () => h('div') } }),
  Position: { Left: 'left', Right: 'right' },
  useVueFlow: () => ({ setCenter: vi.fn() }),
}))
vi.mock('@vue-flow/background', () => ({
  Background: defineComponent({ setup() { return () => h('div') } }),
}))
vi.mock('@vue-flow/controls', () => ({
  Controls: defineComponent({ setup() { return () => h('div') } }),
}))
vi.mock('@vue-flow/minimap', () => ({
  MiniMap: defineComponent({ setup() { return () => h('div') } }),
}))

import OutputPanel from './OutputPanel.vue'
import VueFlowGraph from './graph/VueFlowGraph.vue'

describe('OutputPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    runtimeState.runtimeTabRequest = 0
  })

  it('诊断角标同时展示 compilation/runtime/debug 三路可见计数', async () => {
    const wrapper = mount(OutputPanel, {
      global: {
        stubs: {
          SummaryTab: true,
          DiagnosticsTab: true,
          GraphTab: true,
          HistoryTab: true,
          RuntimeTab: true,
          DebugTab: true,
          HostInfoTab: true,
        },
      },
    })

    await nextTick()
    expect(wrapper.text()).toContain('诊断 (C2/R3/D1)')
    expect(wrapper.text()).not.toContain('parsed source document')
  })
})

describe('VueFlowGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    workspaceState.isGraphEditable = false
    debugState.activeSession = {
      debug_session: {
        status: 'paused',
      },
      diagnostic_links: [],
    }
  })

  it('paused 时仍允许断点与 record-frame 配置，但结构编辑保持锁定', async () => {
    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-node-context-menu').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('添加断点')
    expect(wrapper.text()).toContain('添加记录帧')
    expect(wrapper.text()).not.toContain('删除节点')
  })

  it('paused 时添加断点只更新活动 session，不修改项目图', async () => {
    const wrapper = mount(VueFlowGraph)
    await wrapper.get('.emit-node-context-menu').trigger('click')
    await nextTick()

    const addBreakpoint = wrapper.findAll('.vf-ctxmenu button')
      .find(button => button.text().includes('添加断点'))
    expect(addBreakpoint).toBeDefined()
    await addBreakpoint!.trigger('click')
    await nextTick()

    expect(debugState.applyNodeDebuggerConfig).toHaveBeenCalledWith('node-a', {
      breakpoint: { enabled: true },
    })
    expect(workspaceState.pushUndo).not.toHaveBeenCalled()
    expect(workspaceState.markChanged).not.toHaveBeenCalled()
  })
})
