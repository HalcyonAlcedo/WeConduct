<script setup lang="ts">
/** Thin wrapper: VueFlowGraph with workspace header, used inside PanelContainer */
import { computed, onMounted, ref } from 'vue'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useGraphStore } from '@/stores/graphStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useToastStore } from '@/stores/toastStore'
import { postGraphValidate, postGraphCompile, postCreateEmptyCustomComponent } from '@/services/api'
import { useResourceStore } from '@/stores/resourceStore'
import VueFlowGraph from './VueFlowGraph.vue'
import type { CompilationRequest } from '@/types/domains/compilation'

const workspace = useGraphWorkspaceStore()
const graphStore = useGraphStore()
const compilation = useCompilationStore()
const toast = useToastStore()
const resource = useResourceStore()

const showNewCompDlg = ref(false)
const newCompName = ref('')

onMounted(() => { if (!workspace.isLoaded) workspace.loadGraph(); workspace.refreshGraphDocuments() })

async function switchGraph(docId: string) {
  if (docId === (workspace.currentDocumentId || '')) return
  await workspace.loadGraph(docId || undefined)
  await workspace.syncSource()
  graphStore.selectNode(null)
  compilation.resetCompilation()
}

async function createCustomComponent() {
  const name = newCompName.value.trim()
  if (!name) return
  try {
    const r = await postCreateEmptyCustomComponent(name)
    toast.success('已创建', r.resource.display_name)
    await resource.refreshAll()
    const docId = `custom_node_graph:${r.resource.resource_id}`
    await workspace.loadGraph(docId)
    await workspace.syncSource()
    await workspace.refreshGraphDocuments()
    showNewCompDlg.value = false; newCompName.value = ''
  } catch (e: any) { toast.error('创建失败', e?.message) }
}


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
      <select class="gcp-graph-sel" :value="workspace.currentDocumentId || ''" @change="switchGraph(($event.target as HTMLSelectElement).value)">
        <option value="">📄 主图</option>
        <option v-for="d in workspace.graphDocuments.filter(x => x.document_role === 'custom_node_graph')" :key="d.document_id" :value="d.document_id">🔧 {{ d.display_name || d.document_id }}</option>
      </select>
      <button class="gcp-btn" @click="showNewCompDlg = true" title="新建用户组件">+</button>
      <span class="gcp-info">节点: {{ nodeCount }} · 边: {{ edgeCount }}</span>
      <span v-if="workspace.isLoaded" class="gcp-rev">rev: {{ workspace.saveRevision }}</span>
      <span v-if="!workspace.lastCompileMatches" class="gcp-warn">⚠ 未同步</span>
      <span class="gcp-actions">
        <button class="gcp-btn" @click="handleValidate">校验</button>
        <button class="gcp-btn" @click="handleCompile">编译</button>
        <button class="gcp-btn save" @click="handleSave" :disabled="!workspace.isGraphEditable" :title="workspace.isGraphEditable ? '保存' : '.wcrun 只读'">保存</button>
      </span>
    </div>
    <VueFlowGraph />
    <Teleport to="body">
      <div v-if="showNewCompDlg" class="gcp-dlg-overlay" @click.self="showNewCompDlg = false">
        <div class="gcp-dlg-box">
          <div class="gcp-dlg-hd">新建用户组件<span class="gcp-dlg-close" @click="showNewCompDlg = false">✕</span></div>
          <div class="gcp-dlg-body"><input v-model="newCompName" class="gcp-dlg-input" placeholder="组件名称" @keyup.enter="createCustomComponent" /></div>
          <div class="gcp-dlg-ft"><button class="gcp-dlg-btn" @click="createCustomComponent" :disabled="!newCompName.trim()">创建</button></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.gcp { display: flex; flex-direction: column; height: 100%; }
.gcp-graph-sel { padding: 1px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); font-family: var(--font-ui); max-width: 180px; }
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
.gcp-dlg-overlay { position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; }
.gcp-dlg-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-md); min-width: 300px; box-shadow: var(--shadow-menu); }
.gcp-dlg-hd { display: flex; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); font-weight: 600; font-size: var(--text-body); }
.gcp-dlg-close { cursor: pointer; color: var(--text-disabled); }
.gcp-dlg-body { padding: 12px; }
.gcp-dlg-input { width: 100%; padding: 4px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-body); }
.gcp-dlg-ft { padding: 8px 12px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: flex-end; }
.gcp-dlg-btn { padding: 4px 14px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--accent); color: #fff; cursor: pointer; font-size: var(--text-small); }
.gcp-dlg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
