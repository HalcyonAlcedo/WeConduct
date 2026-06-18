<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useCompilationStore } from '@/stores/compilationStore'
import { useGraphStore } from '@/stores/graphStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useToastStore } from '@/stores/toastStore'
import { postGraphValidate, postGraphCompile } from '@/services/api'
import type { CompilationRequest } from '@/types/domains/compilation'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import VueFlowGraph from './VueFlowGraph.vue'

const compilation = useCompilationStore()
const graphStore = useGraphStore()
const workspace = useGraphWorkspaceStore()
const toast = useToastStore()

onMounted(() => { workspace.loadGraph() })

const graphStats = computed(() => compilation.graphStats)
const outcome = computed(() => compilation.outcome)

const selected = computed(() => graphStore.selectGraphModel({
  workspaceModel: workspace.graphModel,
  compilationModel: outcome.value?.graph_model,
}))

const selectedModel = computed(() => selected.value.model)
const selectedSource = computed(() => selected.value.source)

const hasGraph = computed(() => !!selectedModel.value || (!!graphStats.value?.graph_model_id))
const nodeCount = computed(() => selectedModel.value?.nodes.length ?? 0)
const edgeCount = computed(() => selectedModel.value?.edges.length ?? 0)
const graphModelId = computed(() => selectedModel.value?.graph_model_id ?? null)

const nodes = computed(() => selectedModel.value?.nodes ?? [])

function nodeKindLabel(k: string) {
  switch (k) {
    case 'execution': return '执行'
    case 'control': return '控制'
    case 'observe': return '观察'
    case 'bridge': return '桥接'
    default: return k
  }
}

function selectNode(nodeId: string) {
  graphStore.selectNode(graphStore.selectedNode === nodeId ? null : nodeId)
}

async function handleSave() {
  if (!workspace.graphModel) return
  const model = workspace.graphModel as unknown as Record<string, unknown>
  await workspace.saveGraph(model)
}

async function validateGraph() {
  if (!selectedModel.value) { toast.info('图校验', '当前图为空，请先添加节点'); return }
  if (selectedSource.value === 'compilation') {
    toast.info('图校验', '当前显示的是编译结果图，请先保存为工作区图后再校验')
    return
  }
  try {
    const model = selectedModel.value as unknown as Record<string, unknown>
    const result = await postGraphValidate(model)
    if (result.status === 'valid') { compilation.compilePhase = 'completed' }
    toast.info('图校验完成', result.status === 'valid' ? '校验通过' : `${result.summary.error_count} 条错误`)
  } catch (err: any) {
    toast.error('图校验失败', err?.message)
  }
}

async function compileGraph() {
  if (!selectedModel.value) { toast.info('图编译', '当前图为空，请先添加节点或加载示例'); return }
  if (selectedSource.value === 'compilation') {
    toast.info('图编译', '当前显示的是编译结果图，请先保存为工作区图后再编译')
    return
  }
  try {
    const model = selectedModel.value as unknown as Record<string, unknown>
    const result = await postGraphCompile(model)
    // Route results to main compilation display (Summary/Diagnostics/Graph tabs)
    if (result.outcome) {
      compilation.lastResponse = {
        status: result.status,
        request: result.request as unknown as CompilationRequest,
        outcome: result.outcome,
        view: result.view,
      }
      if (result.status === 'succeeded') {
        compilation.compilePhase = 'completed'
      } else {
        compilation.compilePhase = 'failed'
        compilation.compileError = result.view?.primary_diagnostic?.message ?? '图编译失败'
      }
    }
    toast.success('图编译完成', `状态: ${result.status}`)
  } catch (err: any) {
    const body = err?.body
    if (body) {
      compilation.compilePhase = 'failed'
      compilation.compileError = body.message || body.error || err?.message
      compilation.lastResponse = {
        status: 'failed',
        request: body as unknown as CompilationRequest,
        outcome: body.outcome || {},
        view: body.view || {},
      }
    }
    toast.error('图编译失败', body?.message || body?.error || err?.message)
  }
}
</script>

<template>
  <div class="graph-tab">
    <!-- Graph loading -->
    <PlaceholderBanner
      v-if="workspace.loadState === 'error'"
      type="failure"
      :title="workspace.loadError ?? '图稿加载失败'"
      description="无法从后端加载图工作区"
    />

    <div v-else-if="workspace.loadState === 'loading'" class="loading-block">
      <div class="skeleton-graph skeleton-pulse"></div>
    </div>

    <PlaceholderBanner
      v-else-if="!hasGraph && !compilation.isCompiling"
      type="empty"
      title="暂无图数据"
      description="编译源代码或加载图工作区以查看图模型"
    />

    <template v-else>
      <!-- Header with workspace info + actions -->
      <div class="gt-header">
        <span class="gt-id" v-if="graphModelId">{{ graphModelId }}</span>
        <span class="gt-stats">节点: {{ nodeCount }} · 边: {{ edgeCount }}</span>
        <span v-if="workspace.isLoaded" class="gt-meta">
          rev: {{ workspace.saveRevision }}
          <span v-if="workspace.view?.graph_document_saved_at" class="gt-saved-at">
            · {{ workspace.view.graph_document_saved_at.slice(0, 19) }}
          </span>
          <span v-if="!workspace.lastCompileMatches" class="gt-mismatch" title="最近编译结果与当前保存图稿不一致">
            ⚠ 未同步
          </span>
        </span>
        <span class="gt-actions">
          <button class="gt-act-btn" title="校验当前图稿" @click="validateGraph">校</button>
          <button class="gt-act-btn" title="编译当前图稿" @click="compileGraph">编</button>
          <button class="gt-act-btn save" title="保存图稿" @click="handleSave" :disabled="workspace.saveState === 'saving'">{{ workspace.saveState === 'saving' ? '…' : '存' }}</button>
        </span>
      </div>

      <VueFlowGraph />

      <div class="gt-node-list" v-if="nodes.length > 0">
        <h4 class="gt-heading">节点列表</h4>
        <table class="gt-table">
          <thead>
            <tr>
              <th>节点 ID</th>
              <th>类型</th>
              <th>来源锚点</th>
              <th>扩展角色</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="node in nodes" :key="node.node_id"
              :class="{ 'gt-row-sel': graphStore.selectedNode === node.node_id }"
              @click="selectNode(node.node_id)">
              <td class="gt-node-id">{{ node.node_id }}</td>
              <td>{{ nodeKindLabel(node.lowered_kind) }}</td>
              <td class="gt-mono">{{ node.source_anchor_ref }}</td>
              <td>{{ node.expansion_role }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.graph-tab { display: flex; flex-direction: column; height: 100%; }
.loading-block { padding: var(--space-lg); }
.skeleton-graph { height: 200px; background: var(--bg-panel-header); border-radius: var(--radius-md); }

.gt-header {
  display: flex; align-items: center; gap: var(--space-md);
  padding: var(--space-sm) var(--space-lg);
  border-bottom: 1px solid var(--border-subtle); flex-shrink: 0; flex-wrap: wrap;
}
.gt-id { font-family: var(--font-mono); font-size: var(--text-small); color: var(--text-secondary); }
.gt-stats { font-size: var(--text-small); color: var(--text-disabled); }
.gt-meta { font-size: var(--text-small); color: var(--text-disabled); }
.gt-saved-at { color: var(--text-disabled); }
.gt-mismatch { color: var(--state-degraded); margin-left: var(--space-xs); }
.gt-actions { margin-left: auto; display: flex; gap: 4px; }
.gt-act-btn {
  padding: 2px 8px; border: 1px solid var(--border-default); background: var(--bg-panel);
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  font-size: var(--text-small); font-family: var(--font-ui);
}
.gt-act-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.gt-act-btn.save { background: var(--accent); color: #fff; border-color: var(--accent); }
.gt-act-btn.save:hover:not(:disabled) { background: var(--accent-hover); }
.gt-act-btn.save:disabled { opacity: 0.5; }

.gt-node-list { border-top: 1px solid var(--border-subtle); flex-shrink: 0; max-height: 38%; overflow-y: auto; }
.gt-heading { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); padding: var(--space-sm) var(--space-lg); }
.gt-table { width: 100%; border-collapse: collapse; font-size: var(--text-small); }
.gt-table th { text-align: left; padding: 3px 8px; background: var(--bg-panel-header); color: var(--text-disabled); font-weight: 600; font-size: var(--text-caption); border-bottom: 1px solid var(--border-subtle); }
.gt-table td { padding: 3px 8px; border-bottom: 1px solid var(--border-subtle); cursor: pointer; }
.gt-row-sel { background: var(--bg-selected); }
.gt-node-id { font-family: var(--font-mono); font-size: var(--text-caption); }
.gt-mono { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
</style>
