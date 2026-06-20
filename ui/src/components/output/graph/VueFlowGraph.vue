<script setup lang="ts">
import { computed, ref, markRaw } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import BaseNode from './nodes/BaseNode.vue'
import { useGraphStore } from '@/stores/graphStore'
import { useCompilationStore } from '@/stores/compilationStore'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useDockStore } from '@/stores/dockStore'
import { useToastStore } from '@/stores/toastStore'

const compilation = useCompilationStore()
const graphStore = useGraphStore()
const workspace = useGraphWorkspaceStore()
const dock = useDockStore()
const toast = useToastStore()

const { setCenter } = useVueFlow()
// Expose for external node navigation (diagnostics locate, metadata select, etc.)
;(window as any).__panToNode = (nodeId: string) => {
  const n = workspace.graphModel?.nodes.find(x => x.node_id === nodeId)
  if (n?.position) setCenter(n.position.x + 90, n.position.y + 28, { zoom: 1.2, duration: 400 })
}

// Right-click context menu
const contextMenu = ref<{ x: number; y: number; nodeId: string } | null>(null)
const edgeContextMenu = ref<{ x: number; y: number; edgeId: string; relation: string } | null>(null)
function onNodeContextMenu(event: any) {
  event.event?.preventDefault?.()
  const nodeId = (event as any).node?.id || (event as any).id
  if (!nodeId) return
  contextMenu.value = { x: (event as any).event?.clientX ?? 0, y: (event as any).event?.clientY ?? 0, nodeId }
}
const copiedNode = ref<any>(null)

function closeContextMenu() { contextMenu.value = null; edgeContextMenu.value = null }

function copyNode() {
  if (!contextMenu.value) return
  const node = workspace.graphModel?.nodes.find(n => n.node_id === contextMenu.value!.nodeId)
  if (node) { copiedNode.value = JSON.parse(JSON.stringify(node)); toast.info('已复制', node.display_name || node.node_id) }
  closeContextMenu()
}

async function pasteNode() {
  if (!copiedNode.value || !workspace.graphModel) return
  closeContextMenu()
  const newNodeId = await workspace.pasteNode(copiedNode.value)
  if (newNodeId) {
    graphStore.selectNode(newNodeId)
    toast.info('已粘贴', copiedNode.value.display_name || newNodeId)
  }
}

function onEdgeContextMenu(event: any) {
  event.event?.preventDefault?.()
  const edge = (event as any).edge
  if (!edge) return
  const gm = workspace.graphModel
  if (!gm) return
  const e = gm.edges.find(ed => ed.edge_id === edge.id)
  if (!e) return
  edgeContextMenu.value = { x: (event as any).event?.clientX ?? 0, y: (event as any).event?.clientY ?? 0, edgeId: e.edge_id, relation: e.relation_layer }
}

const EDGE_TYPE_CYCLE: Record<string, string> = { control: 'data', data: 'control' }
function switchEdgeType() {
  if (!edgeContextMenu.value) return
  const next = EDGE_TYPE_CYCLE[edgeContextMenu.value.relation] || 'control'
  workspace.updateEdgeRelation(edgeContextMenu.value.edgeId, next)
  toast.info('边类型', next)
  closeContextMenu()
}
function deleteEdge() {
  if (!edgeContextMenu.value) return
  workspace.removeEdge(edgeContextMenu.value.edgeId)
  toast.info('边已删除')
  closeContextMenu()
}
function deleteNode() {
  if (!contextMenu.value) return
  const nodeId = contextMenu.value.nodeId
  closeContextMenu()
  ;(window as any).__openDeleteConfirm?.(() => {
    workspace.removeNode(nodeId)
    toast.info('节点已删除')
  })
}
/** Ensure metadata panel is visible in right zone and select the node */
function openMetadataPanel(nodeId: string) {
  if (!dock.isPanelVisible('metadata')) {
    dock.restorePanel('metadata', 'right')
  }
  graphStore.selectNode(nodeId)
}

function inspectNode() {
  if (!contextMenu.value) return
  openMetadataPanel(contextMenu.value.nodeId)
  closeContextMenu()
}

function onNodeDoubleClick(event: any) {
  const nodeId = (event as any).node?.id || (event as any).id
  if (!nodeId) return
  openMetadataPanel(nodeId)
}

// Drag-drop from component library
function onDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes('application/json')) {
    e.preventDefault()
    e.dataTransfer!.dropEffect = 'copy'
  }
}
async function onDrop(e: DragEvent) {
  e.preventDefault()
  const raw = e.dataTransfer?.getData('application/json')
  if (!raw) return
  try {
    const item = JSON.parse(raw) as { resource_key: string; display_name: string; resource_type?: string }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const pos = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    const nodeId = await workspace.addNode(item, pos)
    if (nodeId) {
      graphStore.selectNode(nodeId)
      toast.info('已添加节点', item.display_name)
    }
  } catch { /* ignore invalid drops */ }
}

// Mark imported components as non-reactive for VueFlow
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const nodeTypes: Record<string, any> = markRaw({ execution: BaseNode, control: BaseNode, observe: BaseNode, bridge: BaseNode })

const graphData = computed(() => {
  const { model } = graphStore.selectGraphModel({
    workspaceModel: workspace.graphModel,
    compilationModel: compilation.outcome?.graph_model,
  })
  if (!model) return { nodes: [], edges: [] }
  return graphStore.toVueFlow(model)
})

const isWorkspaceEmpty = computed(() =>
  workspace.isLoaded && workspace.graphModel && (workspace.graphModel.nodes?.length ?? 0) === 0
)

const hasGraph = computed(() => graphData.value.nodes.length > 0)

function onNodeClick({ node }: { node: { id: string } }) {
  graphStore.selectNode(node.id)
}

function onPaneClick() { graphStore.selectNode(null) }

// Write back drag positions — snapshot at start, save center coordinates at stop
function onNodeDragStart() { workspace.pushUndo?.() }
function onNodeDragStop(event: any) {
  const node = (event as any).node
  if (!node) return
  workspace.updateNodePosition(node.id, {
    x: node.position.x + 90,  // NODE_WIDTH / 2 = center
    y: node.position.y + 28,  // NODE_HEIGHT / 2 = center
  })
}
// Write back new connections — defaults to 'control'
function onConnect(connection: any) {
  workspace.addEdge({
    edge_id: `edge-${Date.now().toString(36)}`,
    relation_layer: 'control',
    from_node_id: connection.source,
    to_node_id: connection.target,
    from_port_id: connection.sourceHandle || undefined,
    to_port_id: connection.targetHandle || undefined,
  })
}

// Edge click: cycle relation_layer (observe loop shows warning)
function onEdgeClick(event: any) {
  const edge = (event as any).edge
  if (!edge) return
  const gm = workspace.graphModel
  if (!gm) return
  const e = gm.edges.find(ed => ed.edge_id === edge.id)
  if (!e) return
  const next: Record<string, string> = { control: 'data', data: 'control' }
  const newLayer = next[e.relation_layer] || 'control'
  workspace.updateEdgeRelation(e.edge_id, newLayer)
  toast.info('边类型已切换', newLayer)
}
function onEdgesChange(changes: any[]) {
  for (const c of changes) {
    if (c.type === 'remove') {
      workspace.removeEdge((c as any).id)
    }
  }
}
function onViewportChange(vp: { x: number; y: number; zoom: number }) {
  // Compute viewport center in flow coordinates
  const el = (document.querySelector('.vf-canvas') as HTMLElement)
  const w = el?.clientWidth || 800
  const h = el?.clientHeight || 600
  const cx = (w / 2 - vp.x) / vp.zoom
  const cy = (h / 2 - vp.y) / vp.zoom
  workspace.updateViewport({ x: Math.round(cx), y: Math.round(cy), zoom: vp.zoom })
}
</script>

<template>
  <div class="vf-wrapper" @dragover="onDragOver" @drop="onDrop">
    <div v-if="!hasGraph" class="vf-empty">
      <span class="vf-empty-text">无图数据
        <span v-if="isWorkspaceEmpty" class="vf-source-tag">(工作区图为空 — 请编译源代码或在画布上添加节点)</span>
        <span v-else> — 编译源代码以生成图模型</span>
      </span>
    </div>
    <VueFlow
      v-else
      v-bind="graphData"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 1 }"
      :nodes-draggable="true"
      :nodes-connectable="true"
      :edges-updatable="true"
      :elements-selectable="true"
      :zoom-on-scroll="true"
      :pan-on-scroll="true"
      :snap-to-grid="true"
      :snap-grid="[10, 10]"
      :fit-view-on-init="true"
      class="vf-canvas"
      @node-click="onNodeClick"
      @node-double-click="onNodeDoubleClick"
      @node-context-menu="onNodeContextMenu"
      @pane-click="onPaneClick"
      @node-drag-start="onNodeDragStart"
      @node-drag-stop="onNodeDragStop"
      @connect="onConnect"
      @edge-click="onEdgeClick"
      @edge-context-menu="onEdgeContextMenu"
      @edges-change="onEdgesChange"
      @viewport-change="onViewportChange"
    >
      <Background :gap="16" :size="1" pattern-color="#aaa" />
      <Controls position="bottom-right" />
    </VueFlow>

    <!-- Context Menu -->
    <div v-if="contextMenu" class="vf-ctxmenu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.self="closeContextMenu">
      <button @click="inspectNode">查看属性</button>
      <button @click="copyNode">复制节点</button>
      <button v-if="copiedNode" @click="pasteNode">粘贴节点</button>
      <button @click="deleteNode">删除节点</button>
      <hr><button @click="closeContextMenu">取消</button>
    </div>
    <div v-if="contextMenu || edgeContextMenu" class="vf-ctxmask" @click="closeContextMenu"></div>

    <!-- Edge Context Menu -->
    <div v-if="edgeContextMenu" class="vf-ctxmenu" :style="{ left: edgeContextMenu.x + 'px', top: edgeContextMenu.y + 'px' }">
      <div class="vf-ctxmenu-label">边: {{ edgeContextMenu.relation }} <span v-if="edgeContextMenu.relation === 'observe'" class="vf-observe-warn">(不支持执行)</span></div>
      <button @click="switchEdgeType">切换类型 ({{ EDGE_TYPE_CYCLE[edgeContextMenu.relation] || 'control' }})</button>
      <button @click="deleteEdge">删除连线</button>
      <hr><button @click="closeContextMenu">取消</button>
    </div>
  </div>
</template>

<style scoped>
.vf-wrapper {
  flex: 1;
  overflow: hidden;
  background: var(--bg-input);
  position: relative;
}

.vf-canvas {
  width: 100%;
  height: 100%;
}

.vf-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.vf-empty-text {
  font-size: var(--text-body);
  color: var(--text-disabled);
}

/* Edge styles */
:deep(.vf-edge-control .vue-flow__edge-path) {
  stroke: var(--border-default);
  stroke-width: 1.5;
}
:deep(.vf-edge-data .vue-flow__edge-path) {
  stroke: var(--state-info);
  stroke-width: 1.5;
  stroke-dasharray: 6 3;
}
:deep(.vf-edge-observe .vue-flow__edge-path) {
  stroke: var(--state-warning);
  stroke-width: 1.5;
  stroke-dasharray: 3 2;
}

/* Node selection ring */
:deep(.vue-flow__node.selected .vf-node) {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-light);
}

.vf-ctxmask { position: fixed; inset: 0; z-index: 99; }
.vf-ctxmenu {
  position: fixed; z-index: 100; min-width: 140px;
  background: var(--bg-panel); border: 1px solid var(--border-default);
  border-radius: var(--radius-md); box-shadow: var(--shadow-menu);
  padding: var(--space-xs);
}
.vf-ctxmenu button {
  display: block; width: 100%; padding: 5px 10px; border: none; background: transparent;
  color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-body);
  cursor: pointer; border-radius: var(--radius-sm); text-align: left;
}
.vf-ctxmenu button:hover { background: var(--bg-hover); }
.vf-ctxmenu hr { margin: var(--space-xs) 0; border: none; border-top: 1px solid var(--border-subtle); }
.vf-ctxmenu-label { padding: 3px 10px; font-size: var(--text-caption); color: var(--text-disabled); border-bottom: 1px solid var(--border-subtle); }
.vf-observe-warn { color: var(--state-error); font-weight: 600; }
</style>
