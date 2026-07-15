<script setup lang="ts">
import { computed, markRaw, ref } from 'vue'
import { VueFlow, type NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import DocsBaseNode from './DocsBaseNode.vue'
import DocsMetadataPanel from './DocsMetadataPanel.vue'
import { toVueFlowGraph } from './graph-model'
import type { GraphNode, GraphRuntimeState, LoweredNodeKind } from './types'

const props = defineProps<{ state: GraphRuntimeState }>()
const selectedNodeId = ref<string | null>(null)
const metadataVisible = ref(false)
const metadataCollapsed = ref(false)

const nodeTypes = markRaw({
  execution: DocsBaseNode,
  control: DocsBaseNode,
  observe: DocsBaseNode,
  bridge: DocsBaseNode,
})

const graphData = computed(() => (
  props.state.graph ? toVueFlowGraph(props.state.graph) : { nodes: [], edges: [] }
))

const selectedNode = computed<GraphNode | null>(() => (
  props.state.graph?.nodes.find(node => node.node_id === selectedNodeId.value) || null
))

function onNodeClick(event: NodeMouseEvent): void {
  selectedNodeId.value = event.node.id
}

function onNodeDoubleClick(event: NodeMouseEvent): void {
  selectedNodeId.value = event.node.id
  metadataVisible.value = true
  metadataCollapsed.value = false
}

function onPaneClick(): void {
  selectedNodeId.value = null
  metadataVisible.value = false
  metadataCollapsed.value = false
}

function toggleMetadata(): void {
  metadataCollapsed.value = !metadataCollapsed.value
}

function minimapColor(node: { data?: { kind?: LoweredNodeKind } }): string {
  switch (node.data?.kind) {
    case 'control': return '#9b80b4'
    case 'observe': return 'var(--state-warning)'
    case 'bridge': return 'var(--state-success)'
    case 'execution':
    default: return 'var(--state-info)'
  }
}

async function toggleFullscreen(event: MouseEvent): Promise<void> {
  const host = (event.currentTarget as HTMLElement).closest('weconduct-graph') as HTMLElement | null
  if (!host) return
  try {
    if (document.fullscreenElement === host) {
      await document.exitFullscreen()
    } else {
      await host.requestFullscreen()
    }
  } catch (error) {
    props.state.error = `全屏切换失败：${error instanceof Error ? error.message : '未知错误'}`
  }
}
</script>

<template>
  <section class="wc-graph">
    <header class="wc-graph-header">
      <p class="wc-graph-title">{{ state.title }}</p>
      <span v-if="state.graph" class="wc-graph-stats">
        {{ state.graph.nodes.length }}N / {{ state.graph.edges.length }}E
      </span>
      <button
        type="button"
        class="wc-graph-fullscreen"
        title="全屏"
        aria-label="全屏"
        @click="toggleFullscreen"
      >
        ⛶
      </button>
    </header>

    <div
      :class="[
        'wc-graph-viewport',
        {
          'has-metadata': metadataVisible && selectedNode,
          'metadata-collapsed': metadataCollapsed,
        },
      ]"
    >
      <p v-if="state.loading" class="wc-graph-status">正在加载图示...</p>
      <div v-else-if="state.error" class="wc-graph-error">
        <p>{{ state.error }}</p>
        <p v-if="state.fallback" class="wc-graph-fallback">{{ state.fallback }}</p>
      </div>
      <VueFlow
        v-else-if="state.graph"
        :id="state.instanceId"
        :nodes="graphData.nodes"
        :edges="graphData.edges"
        :node-types="nodeTypes"
        :nodes-draggable="false"
        :nodes-connectable="false"
        :edges-updatable="false"
        :elements-selectable="true"
        :zoom-on-scroll="true"
        :zoom-on-double-click="false"
        :pan-on-scroll="true"
        :min-zoom="0.45"
        :max-zoom="1.5"
        :fit-view-on-init="true"
        class="vf-canvas"
        @node-click="onNodeClick"
        @node-double-click="onNodeDoubleClick"
        @pane-click="onPaneClick"
      >
        <Background :gap="16" :size="1" pattern-color="#aaa" />
        <MiniMap
          position="bottom-left"
          :width="160"
          :height="100"
          :mask-color="'rgba(0,0,0,0.08)'"
          :node-color="minimapColor"
        />
        <Controls position="bottom-right" />
      </VueFlow>
      <DocsMetadataPanel
        v-if="metadataVisible && selectedNode"
        :node="selectedNode"
        :collapsed="metadataCollapsed"
        @toggle="toggleMetadata"
      />
    </div>
  </section>
</template>
