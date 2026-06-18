<script setup lang="ts">
/** Thin wrapper: VueFlowGraph with workspace header, used inside PanelContainer */
import { computed, onMounted } from 'vue'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useGraphStore } from '@/stores/graphStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useToastStore } from '@/stores/toastStore'
import { postGraphValidate, postGraphCompile } from '@/services/api'
import VueFlowGraph from './VueFlowGraph.vue'
import type { CompilationRequest } from '@/types/domains/compilation'

const workspace = useGraphWorkspaceStore()
const graphStore = useGraphStore()
const compilation = useCompilationStore()
const toast = useToastStore()

onMounted(() => { workspace.loadGraph() })

const selected = computed(() => graphStore.selectGraphModel({
  workspaceModel: workspace.graphModel,
  compilationModel: compilation.outcome?.graph_model,
}))
const selectedModel = computed(() => selected.value.model)
const selectedSource = computed(() => selected.value.source)
const nodeCount = computed(() => selectedModel.value?.nodes.length ?? 0)
const edgeCount = computed(() => selectedModel.value?.edges.length ?? 0)

async function handleSave() {
  if (!workspace.graphModel) return
  await workspace.saveGraph(workspace.graphModel as unknown as Record<string, unknown>)
}
async function handleValidate() {
  if (!selectedModel.value) { toast.info('', '当前图为空'); return }
  if (selectedSource.value === 'compilation') { toast.info('', '请先保存为工作区图'); return }
  try {
    const r = await postGraphValidate(selectedModel.value as unknown as Record<string, unknown>)
    // On valid: show passing state; on failure: bridge diagnostics to output tabs
    if (r.status === 'valid') {
      compilation.lastResponse = {
        status: 'succeeded',
        request: {} as CompilationRequest,
        outcome: {
          graph_model: null,
          compilation_summary: { compilation_id: 'graph-validate', stage_outcomes: [], duration_ms: null },
          diagnostic_catalog: { entries: [] },
        },
        view: {
          status: 'succeeded', duration_ms: null,
          stage_cards: [],
          stage_overview: { total_stage_count: 0, succeeded_stage_count: 0, failed_stage_count: 0, terminal_stage: null },
          diagnostic_groups: [],
          diagnostic_summary: { total_count: 0, highest_severity: null },
          primary_diagnostic: null,
          graph_stats: { graph_model_id: null, node_count: 0, edge_count: 0, effective_diagnostic_anchor_count: 0 },
        },
      }
      compilation.compilePhase = 'completed'
    } else if (r.diagnostics.length > 0) {
      // Select primary diagnostic by severity, not array order
      const severityRank: Record<string, number> = { fatal: 0, error: 1, degraded: 2, warning: 3, info: 4 }
      const sorted = [...r.diagnostics].sort((a, b) => (severityRank[a.severity] ?? 5) - (severityRank[b.severity] ?? 5))
      const primary = sorted[0]
      const highestSev = sorted[0]?.severity ?? null
      compilation.lastResponse = {
        status: 'failed',
        request: {} as CompilationRequest,
        outcome: {
          graph_model: null,
          compilation_summary: { compilation_id: 'graph-validate', stage_outcomes: [], duration_ms: null },
          diagnostic_catalog: { entries: r.diagnostics },
        },
        view: {
          status: 'failed', duration_ms: null,
          stage_cards: [], stage_overview: { total_stage_count: 0, succeeded_stage_count: 0, failed_stage_count: 0, terminal_stage: null },
          diagnostic_groups: r.diagnostics.map(d => ({ stage: d.stage, category: d.category, severity: d.severity, count: 1, message: d.message })),
          diagnostic_summary: { total_count: r.diagnostics.length, highest_severity: highestSev },
          primary_diagnostic: primary ? { stage: primary.stage, category: primary.category, severity: primary.severity, message: primary.message } : null,
          graph_stats: { graph_model_id: null, node_count: 0, edge_count: 0, effective_diagnostic_anchor_count: 0 },
        },
      }
      compilation.compilePhase = 'failed'
    }
    toast.info('校验完成', r.status === 'valid' ? '校验通过' : `${r.summary.error_count} 条错误 — 查看诊断标签页`)
  } catch (e: any) {
    const body = e?.body
    const msg = body?.message || body?.error || e?.message
    if (body) { compilation.compilePhase = 'failed'; compilation.compileError = msg }
    toast.error('校验失败', msg)
  }
}
async function handleCompile() {
  if (!selectedModel.value) { toast.info('', '当前图为空'); return }
  if (selectedSource.value === 'compilation') { toast.info('', '请先保存为工作区图'); return }
  try {
    const r = await postGraphCompile(selectedModel.value as unknown as Record<string, unknown>)
    if (r.outcome) {
      compilation.lastResponse = {
        status: r.status, request: r.request as unknown as CompilationRequest,
        outcome: r.outcome, view: r.view,
      }
      compilation.compilePhase = r.status === 'succeeded' ? 'completed' : 'failed'
    }
    if (r.status === 'succeeded') {
      toast.success('编译完成', `节点: ${r.view.graph_stats.node_count}`)
    } else {
      const diag = r.view.primary_diagnostic
      toast.error('编译失败', diag ? `${diag.message} — 查看诊断标签页` : '查看诊断标签页')
    }
  } catch (e: any) {
    const body = e?.body
    if (body) {
      compilation.compilePhase = 'failed'
      compilation.compileError = body.message || body.error || e?.message
      compilation.lastResponse = {
        status: 'failed',
        request: body as unknown as CompilationRequest,
        outcome: body.outcome || {},
        view: body.view || {},
      }
    }
    const msg = e?.body?.details?.primary_diagnostic?.message || e?.body?.message || e?.body?.error || e?.message
    toast.error('编译失败', msg)
  }
}
</script>

<template>
  <div class="gcp">
    <div class="gcp-bar">
      <span class="gcp-info">节点: {{ nodeCount }} · 边: {{ edgeCount }}</span>
      <span v-if="workspace.isLoaded" class="gcp-rev">rev: {{ workspace.saveRevision }}</span>
      <span v-if="!workspace.lastCompileMatches" class="gcp-warn">⚠ 未同步</span>
      <span class="gcp-actions">
        <button class="gcp-btn" @click="handleValidate">校验</button>
        <button class="gcp-btn" @click="handleCompile">编译</button>
        <button class="gcp-btn save" @click="handleSave">保存</button>
      </span>
    </div>
    <VueFlowGraph />
  </div>
</template>

<style scoped>
.gcp { display: flex; flex-direction: column; height: 100%; }
.gcp-bar {
  display: flex; align-items: center; gap: var(--space-sm);
  padding: 2px var(--space-sm); border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-small); color: var(--text-disabled); flex-shrink: 0;
}
.gcp-info { color: var(--text-secondary); }
.gcp-rev { font-family: var(--font-mono); }
.gcp-warn { color: var(--state-degraded); }
.gcp-actions { margin-left: auto; display: flex; gap: 3px; }
.gcp-btn {
  padding: 1px 8px; border: 1px solid var(--border-default); background: var(--bg-panel);
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  font-size: var(--text-small); font-family: var(--font-ui);
}
.gcp-btn:hover { background: var(--bg-hover); }
.gcp-btn.save { background: var(--accent); color: #fff; border-color: var(--accent); }
.gcp-btn.save:hover { background: var(--accent-hover); }
</style>
