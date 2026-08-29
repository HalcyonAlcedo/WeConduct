<script setup lang="ts">
import { computed, ref, markRaw, onUnmounted, watch, nextTick } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import BaseNode from './nodes/BaseNode.vue'
import { useGraphStore } from '@/stores/graphStore'
import { useCompilationStore } from '@/stores/compilationStore'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useDockStore } from '@/stores/dockStore'
import { useToastStore } from '@/stores/toastStore'
import { useDebugStore } from '@/stores/debugStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useProjectDiagnosticsStore } from '@/stores/projectDiagnosticsStore'
import { t } from '@/i18n'
import { registerGraphElementNavigator } from '@/services/graphNodeNavigation'
import { resolveGraphDiagnosticTargets } from '@/services/graphDiagnosticTargets'
import { resolveNodeCollisions } from '@/services/graphCollisionLayout'
import type { RelationLayer } from '@/types/domains/graph'

const compilation = useCompilationStore()
const workspace = useGraphWorkspaceStore()
const debugStore = useDebugStore()
const shellWorkspace = useWorkspaceStore()

const ctxNodeConfig = computed(() => {
  const nid = contextMenu.value?.nodeId
  if (!nid) return undefined
  return workspace.graphModel?.nodes.find(n => n.node_id === nid)?.node_config
})
const contextNodeId = computed(() => contextMenu.value?.nodeId)
const nodeHasBP = computed(() => debugStore.hasBreakpoint(ctxNodeConfig.value, contextNodeId.value))
const nodeHasRF = computed(() => debugStore.hasRecordFrame(ctxNodeConfig.value, contextNodeId.value))
const nodeBPTiming = computed(() => (
  debugStore.getEffectiveDebuggerConfig(ctxNodeConfig.value, contextNodeId.value).breakpoint as any
)?.pause_timing || 'before')
const isPausedDebugSession = computed(() => {
  const status = debugStore.activeSession?.debug_session?.status || debugStore.activeSession?.status
  return status === 'paused'
})
const canEditDebugConfig = computed(() => {
  return workspace.isGraphEditable || isPausedDebugSession.value
})

function getEffectiveNodeConfig(nodeConfig: Record<string, unknown>, nodeId: string) {
  return {
    ...nodeConfig,
    debugger: debugStore.getEffectiveDebuggerConfig(nodeConfig, nodeId),
  }
}

async function applyNodeDebugConfig(nodeId: string, nextNodeConfig: Record<string, unknown>) {
  if (isPausedDebugSession.value) {
    try {
      await debugStore.applyNodeDebuggerConfig(
        nodeId,
        debugStore.getDebuggerConfig(nextNodeConfig),
      )
    } catch (error: any) {
      toast.error(t('framework.graph.toast.debugConfigFailed', '调试配置更新失败'), error?.message || t('framework.graph.toast.requestFailed', '请求失败'))
    }
    return
  }
  const node = workspace.graphModel?.nodes.find(candidate => candidate.node_id === nodeId)
  if (!node) return
  workspace.pushUndo?.()
  node.node_config = nextNodeConfig
  workspace.markChanged?.()
}

async function toggleBreakpointOnNode() {
  if (!canEditDebugConfig.value) return
  const nid = contextMenu.value?.nodeId
  if (!nid) return
  const node = workspace.graphModel?.nodes.find(n => n.node_id === nid)
  if (!node?.node_config) return
  const effectiveConfig = getEffectiveNodeConfig(node.node_config, nid)
  await applyNodeDebugConfig(nid, debugStore.toggleBreakpointConfig(effectiveConfig))
}
async function setBPTiming(timing: string) {
  if (!canEditDebugConfig.value) return
  const nid = contextMenu.value?.nodeId
  if (!nid) return
  const node = workspace.graphModel?.nodes.find(n => n.node_id === nid)
  if (!node?.node_config) return
  const effectiveConfig = getEffectiveNodeConfig(node.node_config, nid)
  await applyNodeDebugConfig(nid, debugStore.setBreakpointPauseTiming(effectiveConfig, timing))
}
async function toggleRecordFrameOnNode() {
  if (!canEditDebugConfig.value) return
  const nid = contextMenu.value?.nodeId
  if (!nid) return
  const node = workspace.graphModel?.nodes.find(n => n.node_id === nid)
  if (!node?.node_config) return
  const effectiveConfig = getEffectiveNodeConfig(node.node_config, nid)
  await applyNodeDebugConfig(nid, debugStore.toggleRecordFrameConfig(effectiveConfig))
}
const graphStore = useGraphStore()
const dock = useDockStore()
const toast = useToastStore()
const projectDiagnostics = useProjectDiagnosticsStore()

const { setCenter, getNodes, updateNode } = useVueFlow()
const unregisterGraphElementNavigator = registerGraphElementNavigator(target => {
  const graphModel = workspace.graphModel
  if (!graphModel) return
  if (target.kind === 'node') {
    const node = graphModel.nodes.find(item => item.node_id === target.id)
    if (node?.position) setCenter(node.position.x + 90, node.position.y + 28, { zoom: 1.2, duration: 400 })
    return
  }
  const edge = graphModel.edges.find(item => item.edge_id === target.id)
  const source = edge && graphModel.nodes.find(item => item.node_id === edge.from_node_id)
  const targetNode = edge && graphModel.nodes.find(item => item.node_id === edge.to_node_id)
  if (!source?.position || !targetNode?.position) return
  setCenter(
    (source.position.x + targetNode.position.x) / 2 + 90,
    (source.position.y + targetNode.position.y) / 2 + 28,
    { zoom: 1.2, duration: 400 },
  )
})
onUnmounted(unregisterGraphElementNavigator)

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
  if (node) { copiedNode.value = JSON.parse(JSON.stringify(node)); toast.info(t('framework.graph.toast.copied', '已复制'), node.display_name || node.node_id) }
  closeContextMenu()
}

async function pasteNode() {
  if (!workspace.isGraphEditable) return
  if (!copiedNode.value || !workspace.graphModel) return
  closeContextMenu()
  const newNodeId = await workspace.pasteNode(copiedNode.value)
  if (newNodeId) {
    graphStore.selectNode(newNodeId)
    toast.info(t('framework.graph.toast.pasted', '已粘贴'), copiedNode.value.display_name || newNodeId)
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
  if (!workspace.isGraphEditable) return
  if (!edgeContextMenu.value) return
  const next = EDGE_TYPE_CYCLE[edgeContextMenu.value.relation] || 'control'
  workspace.updateEdgeRelation(edgeContextMenu.value.edgeId, next)
  toast.info(t('framework.graph.toast.edgeType', '边类型'), next)
  closeContextMenu()
}
function deleteEdge() {
  if (!workspace.isGraphEditable) return
  if (!edgeContextMenu.value) return
  workspace.removeEdge(edgeContextMenu.value.edgeId)
  toast.info(t('framework.graph.toast.edgeDeleted', '边已删除'))
  closeContextMenu()
}
function deleteNode() {
  if (!workspace.isGraphEditable) return
  if (!contextMenu.value) return
  const nodeId = contextMenu.value.nodeId
  closeContextMenu()
  if (!graphPreferences.value.confirm_delete_node) {
    workspace.removeNode(nodeId)
    toast.info(t('framework.graph.toast.nodeDeleted', '节点已删除'))
    return
  }
  ;(window as any).__openDeleteConfirm?.(() => {
    workspace.removeNode(nodeId)
    toast.info(t('framework.graph.toast.nodeDeleted', '节点已删除'))
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
  if (!workspace.isGraphEditable) return
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
      if (graphPreferences.value.auto_open_node_on_drop) {
        openMetadataPanel(nodeId)
      }
      toast.info(t('framework.graph.toast.nodeAdded', '已添加节点'), item.display_name)
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
  const highlights = resolveGraphDiagnosticTargets(model, projectDiagnostics.visibleEntries)
  return graphStore.toVueFlow(model, graphPreferences.value.edge_line_style, highlights)
})

const isWorkspaceEmpty = computed(() =>
  workspace.isLoaded && workspace.graphModel && (workspace.graphModel.nodes?.length ?? 0) === 0
)

const hasGraph = computed(() => graphData.value.nodes.length > 0)
const graphPreferences = computed(() => {
  const prefs = (shellWorkspace.snapshot as any)?.graph_workspace?.graph_preferences
  return {
    snap_to_grid: prefs?.snap_to_grid ?? true,
    grid_enabled: prefs?.grid_enabled ?? true,
    auto_open_node_on_drop: prefs?.auto_open_node_on_drop ?? true,
    confirm_delete_node: prefs?.confirm_delete_node ?? true,
    edge_line_style: prefs?.edge_line_style ?? 'smoothstep',
    auto_layout_on_overlap: prefs?.auto_layout_on_overlap ?? true,
  }
})

const autoLayoutPending = ref(true)
const autoLayoutInProgress = ref(false)
let autoLayoutScheduleId = 0

watch(() => workspace.loadState, state => {
  if (state === 'loading') autoLayoutPending.value = true
})
watch(() => workspace.currentDocumentId, () => {
  autoLayoutPending.value = true
  scheduleAutoLayoutCheck()
})

watch(
  () => workspace.graphModel?.nodes.map(node => `${node.node_id}:${node.position?.x ?? 'none'}:${node.position?.y ?? 'none'}`).join('|'),
  () => {
    autoLayoutPending.value = true
    scheduleAutoLayoutCheck()
  },
)

function scheduleAutoLayoutCheck() {
  const scheduleId = ++autoLayoutScheduleId
  void nextTick(() => {
    if (scheduleId !== autoLayoutScheduleId) return
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => {
        if (scheduleId === autoLayoutScheduleId) onNodesInitialized()
      })
    } else {
      setTimeout(() => {
        if (scheduleId === autoLayoutScheduleId) onNodesInitialized()
      }, 0)
    }
  })
}

function onNodesInitialized() {
  if (!autoLayoutPending.value || autoLayoutInProgress.value) return
  autoLayoutPending.value = false
  if (!graphPreferences.value.auto_layout_on_overlap || !workspace.isGraphEditable || !workspace.graphModel) return

  const measuredNodes = getNodes.value
    .filter(node => Number.isFinite(node.position.x) && Number.isFinite(node.position.y))
    .filter(node => Number.isFinite(node.dimensions.width) && Number.isFinite(node.dimensions.height))
    .map(node => ({
      id: node.id,
      position: { x: node.position.x, y: node.position.y },
      dimensions: { width: node.dimensions.width, height: node.dimensions.height },
    }))
  if (measuredNodes.length < 2) return

  const resolvedNodes = resolveNodeCollisions(measuredNodes, 16)
  const changedNodes = resolvedNodes.filter((resolved, index) => {
    const current = measuredNodes[index]
    return resolved.position.x !== current.position.x || resolved.position.y !== current.position.y
  })
  if (!changedNodes.length) return

  autoLayoutInProgress.value = true
  try {
    workspace.pushUndo?.()
    const graphNodesById = new Map(workspace.graphModel.nodes.map(node => [node.node_id, node]))
    for (const resolved of changedNodes) {
      const current = measuredNodes.find(node => node.id === resolved.id)
      if (!current) continue
      updateNode(resolved.id, { position: { ...resolved.position } })
      const graphNode = graphNodesById.get(resolved.id)
      if (!graphNode) continue
      const deltaX = resolved.position.x - current.position.x
      const deltaY = resolved.position.y - current.position.y
      if (graphNode.position) {
        graphNode.position = {
          x: graphNode.position.x + deltaX,
          y: graphNode.position.y + deltaY,
        }
      } else {
        graphNode.position = {
          x: resolved.position.x + current.dimensions.width / 2,
          y: resolved.position.y + current.dimensions.height / 2,
        }
      }
    }
    workspace.markChanged?.()
  } finally {
    autoLayoutInProgress.value = false
  }
}

function onNodeClick({ node }: { node: { id: string } }) {
  graphStore.selectNode(node.id)
}

function onPaneClick() { graphStore.selectNode(null) }

// Write back drag positions — snapshot at start, save center coordinates at stop
function onNodeDragStart() { workspace.pushUndo?.() }
function onNodeDragStop(event: any) {
  const node = (event as any).node
  if (!node) return
  const width = Number.isFinite(node.dimensions?.width) ? node.dimensions.width : 180
  const height = Number.isFinite(node.dimensions?.height) ? node.dimensions.height : 56
  workspace.updateNodePosition(node.id, {
    x: node.position.x + width / 2,
    y: node.position.y + height / 2,
  })
}
function resolveConnectionRelationLayer(connection: any): RelationLayer | null {
  const graphModel = workspace.graphModel
  if (!graphModel) return 'control'

  const sourcePort = graphModel.nodes
    .find(node => node.node_id === connection.source)
    ?.ports?.find(port => port.port_id === connection.sourceHandle)
  const targetPort = graphModel.nodes
    .find(node => node.node_id === connection.target)
    ?.ports?.find(port => port.port_id === connection.targetHandle)
  const sourceLayer = sourcePort?.relation_layer
  const targetLayer = targetPort?.relation_layer

  if (sourceLayer && targetLayer && sourceLayer !== targetLayer) return null
  return sourceLayer ?? targetLayer ?? 'control'
}

function onConnect(connection: any) {
  const relationLayer = resolveConnectionRelationLayer(connection)
  if (!relationLayer) {
    toast.error(
      t('framework.graph.toast.connectionRejected', '无法创建连接'),
      t('framework.graph.toast.connectionLayerMismatch', '两端端口的数据层级不一致'),
    )
    return
  }
  workspace.addEdge({
    edge_id: `edge-${Date.now().toString(36)}`,
    relation_layer: relationLayer,
    from_node_id: connection.source,
    to_node_id: connection.target,
    from_port_id: connection.sourceHandle || undefined,
    to_port_id: connection.targetHandle || undefined,
  })
}

// Edge click: cycle relation_layer (observe loop shows warning)
function onEdgeClick(event: any) {
  if (!workspace.isGraphEditable) return
  const edge = (event as any).edge
  if (!edge) return
  const gm = workspace.graphModel
  if (!gm) return
  const e = gm.edges.find(ed => ed.edge_id === edge.id)
  if (!e) return
  const next: Record<string, string> = { control: 'data', data: 'control' }
  const newLayer = next[e.relation_layer] || 'control'
  workspace.updateEdgeRelation(e.edge_id, newLayer)
  toast.info(t('framework.graph.toast.edgeTypeSwitched', '边类型已切换'), newLayer)
}
function onEdgesChange(changes: any[]) {
  if (!workspace.isGraphEditable) return
  for (const c of changes) {
    if (c.type === 'remove') {
      workspace.removeEdge((c as any).id)
    }
  }
}
function onViewportChange(vp: { x: number; y: number; zoom: number }) {
  // Cache the raw pan/zoom transform so the exact view can be restored after a
  // canvas remount (tab switch within the same dock zone).
  workspace.setRawViewport(vp)
  // Compute viewport center in flow coordinates (used for placing new nodes).
  const el = (document.querySelector('.vf-canvas') as HTMLElement)
  const w = el?.clientWidth || 800
  const h = el?.clientHeight || 600
  const cx = (w / 2 - vp.x) / vp.zoom
  const cy = (h / 2 - vp.y) / vp.zoom
  workspace.updateViewport({ x: Math.round(cx), y: Math.round(cy), zoom: vp.zoom })
}

// On mount, restore the cached view if we have one; otherwise fit-view.
const cachedRawViewport = computed(() => workspace.rawViewport)
const hasCachedViewport = computed(() => cachedRawViewport.value !== null)
</script>

<template>
  <div class="vf-wrapper" @dragover="onDragOver" @drop="onDrop">
    <div v-if="!hasGraph" class="vf-empty">
      <span class="vf-empty-text">{{ t('framework.graph.canvas.emptyText', '无图数据') }}
        <span v-if="isWorkspaceEmpty" class="vf-source-tag">{{ t('framework.graph.canvas.emptyWorkspace', '(工作区图为空 — 请编译源代码或在画布上添加节点)') }}</span>
        <span v-else> {{ t('framework.graph.canvas.emptyHint', '— 编译源代码以生成图模型') }}</span>
      </span>
    </div>
    <VueFlow
      v-else
      v-bind="graphData"
      :node-types="nodeTypes"
      :default-viewport="cachedRawViewport ?? { x: 0, y: 0, zoom: 0.5 }"
      :nodes-draggable="workspace.isGraphEditable"
      :nodes-connectable="workspace.isGraphEditable"
      :edges-updatable="workspace.isGraphEditable"
      :elements-selectable="true"
      :zoom-on-scroll="true"
      :pan-on-scroll="true"
      :min-zoom="0.1"
      :snap-to-grid="graphPreferences.snap_to_grid"
      :snap-grid="[10, 10]"
      :fit-view-on-init="!hasCachedViewport"
      class="vf-canvas"
      @node-click="onNodeClick"
      @node-double-click="onNodeDoubleClick"
      @node-context-menu="onNodeContextMenu"
      @pane-click="onPaneClick"
      @node-drag-start="onNodeDragStart"
      @node-drag-stop="onNodeDragStop"
      @nodes-initialized="onNodesInitialized"
      @connect="onConnect"
      @edge-click="onEdgeClick"
      @edge-context-menu="onEdgeContextMenu"
      @edges-change="onEdgesChange"
      @viewport-change="onViewportChange"
    >
      <Background v-if="graphPreferences.grid_enabled" :gap="16" :size="1" pattern-color="#aaa" />
      <MiniMap position="bottom-left" :width="160" :height="100" :mask-color="'rgba(0,0,0,0.08)'" />
      <Controls position="bottom-right" />
    </VueFlow>

    <!-- Context Menu -->
    <div v-if="contextMenu" class="vf-ctxmenu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.self="closeContextMenu">
      <button @click="inspectNode">{{ t('framework.graph.ctxMenu.inspect', '查看属性') }}</button>
      <button @click="copyNode">{{ t('framework.graph.ctxMenu.copy', '复制节点') }}</button>
      <button v-if="copiedNode && workspace.isGraphEditable" @click="pasteNode">{{ t('framework.graph.ctxMenu.paste', '粘贴节点') }}</button>
      <button v-if="workspace.isGraphEditable" @click="deleteNode">{{ t('framework.graph.ctxMenu.delete', '删除节点') }}</button>
      <hr>
      <button v-if="canEditDebugConfig" @click="toggleBreakpointOnNode(); closeContextMenu()">
        {{ nodeHasBP ? t('framework.graph.ctxMenu.removeBreakpoint', '🔴 移除断点') : t('framework.graph.ctxMenu.addBreakpoint', '🔴 添加断点') }}
      </button>
      <button v-if="nodeHasBP && canEditDebugConfig" @click="setBPTiming('before'); closeContextMenu()" style="padding-left:20px">{{ nodeBPTiming === 'before' ? '✓ ' : '' }}{{ t('framework.graph.ctxMenu.pauseBefore', '执行前暂停') }}</button>
      <button v-if="nodeHasBP && canEditDebugConfig" @click="setBPTiming('after'); closeContextMenu()" style="padding-left:20px">{{ nodeBPTiming === 'after' ? '✓ ' : '' }}{{ t('framework.graph.ctxMenu.pauseAfter', '执行后暂停') }}</button>
      <button v-if="nodeHasBP && canEditDebugConfig" @click="setBPTiming('both'); closeContextMenu()" style="padding-left:20px">{{ nodeBPTiming === 'both' ? '✓ ' : '' }}{{ t('framework.graph.ctxMenu.pauseBoth', '前后都停') }}</button>
      <button v-if="canEditDebugConfig" @click="toggleRecordFrameOnNode(); closeContextMenu()">
        {{ nodeHasRF ? t('framework.graph.ctxMenu.removeRecordFrame', '◉ 移除记录帧') : t('framework.graph.ctxMenu.addRecordFrame', '◉ 添加记录帧') }}
      </button>
      <hr><button @click="closeContextMenu">{{ t('framework.graph.ctxMenu.cancel', '取消') }}</button>
    </div>
    <div v-if="contextMenu || edgeContextMenu" class="vf-ctxmask" @click="closeContextMenu"></div>

    <!-- Edge Context Menu -->
    <div v-if="edgeContextMenu" class="vf-ctxmenu" :style="{ left: edgeContextMenu.x + 'px', top: edgeContextMenu.y + 'px' }">
      <div class="vf-ctxmenu-label">{{ t('framework.graph.edgeCtxMenu.label', `边: ${edgeContextMenu.relation}`, { relation: edgeContextMenu.relation }) }} <span v-if="edgeContextMenu.relation === 'observe'" class="vf-observe-warn">{{ t('framework.graph.edgeCtxMenu.observeUnsupported', '(不支持执行)') }}</span></div>
      <button v-if="workspace.isGraphEditable" @click="switchEdgeType">{{ t('framework.graph.edgeCtxMenu.switchType', `切换类型 (${EDGE_TYPE_CYCLE[edgeContextMenu.relation] || 'control'})`, { next: EDGE_TYPE_CYCLE[edgeContextMenu.relation] || 'control' }) }}</button>
      <button v-if="workspace.isGraphEditable" @click="deleteEdge">{{ t('framework.graph.edgeCtxMenu.deleteEdge', '删除连线') }}</button>
      <hr><button @click="closeContextMenu">{{ t('framework.graph.ctxMenu.cancel', '取消') }}</button>
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
:deep(.vf-edge-error .vue-flow__edge-path) {
  stroke: var(--state-error) !important;
  stroke-width: 3;
}

/* Node selection ring */
:deep(.vue-flow__node.selected .vf-node) {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-light);
}
:deep(.vue-flow__node.vf-node-error .vf-node) {
  border-color: var(--state-error);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--state-error) 35%, transparent);
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
