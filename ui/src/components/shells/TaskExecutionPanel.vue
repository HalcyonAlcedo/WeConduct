<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useToastStore } from '@/stores/toastStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useDockStore } from '@/stores/dockStore'
import {
  postRuntimePrepare, postRuntimeStart, postRuntimeRun,
  fetchRuntimeSession,
  postDebugPrepare, postDebugStart,
  fetchDebugSession, fetchExecutionHistory,
} from '@/services/api'
import type { ExecutionHistoryResponse } from '@/types/domains/api'

const toast = useToastStore()
const workspace = useWorkspaceStore()
const graphWs = useGraphWorkspaceStore()
const runtime = useRuntimeStore()
const loading = ref('')
const execHistory = ref<ExecutionHistoryResponse | null>(null)

function graphBody() {
  if (!graphWs.graphModel) return undefined
  // If project loaded and graph not dirty, let backend use saved graph
  if (workspace.snapshot?.project?.loaded && !graphWs.isDirty) return undefined
  return { graph_document: graphWs.graphModel as unknown as Record<string, unknown> }
}

onMounted(async () => { await runtime.refreshAll(); try { execHistory.value = await fetchExecutionHistory() } catch {} })

async function rtPrepare() {
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，无法执行'); return }
  loading.value='rt-prepare'; try { await postRuntimePrepare(graphBody()); toast.success('Runtime 已就绪'); await runtime.refreshAll() } catch(e:any){
    const msg = e?.body?.message || e?.body?.error || e?.message
    toast.error('准备失败', msg)
    if (e?.body) runtime.setActiveRt(e.body)
  } finally {loading.value=''}
}
async function rtStart() {
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，无法执行'); return }
  loading.value='rt-start'; try {
    const r = await postRuntimeStart(graphBody())
    runtime.setActiveRt(r); toast.success('已启动', r.runtime_session.session_id ?? '')
    await runtime.refreshAll()
  } catch(e: any) {
    if (e?.body) {
      runtime.setActiveRt(e.body)
      const body = e.body
      const diagMsg = body.details?.primary_diagnostic?.message || body.message
      if (body.error === 'diagnostic_blocked') {
        const entries = body.diagnostics?.entries || []
        const nodeIds = [...new Set(entries.map((d: any) => d?.stage_extension?.graph_ref?.node_id).filter(Boolean))]
        toast.error('启动受阻：组件已禁用', nodeIds.length ? `节点: ${nodeIds.join(', ')}` : diagMsg || '请检查资源管理')
      } else {
        toast.error('启动失败', diagMsg || body.error || e?.message)
      }
    } else {
      toast.error('启动失败', e?.message)
    }
  } finally {loading.value=''}
}
async function rtRun(id: string) {
  loading.value='rt-run'
  try {
    runtime.subscribeRuntimeSession(id)
    const r = await postRuntimeRun(id)
    runtime.setActiveRt(r)
    if (r.status === 'completed' || r.status === 'failed') {
      toast.success('执行完成', r.status)
    }
  } catch(e:any){
    if (e?.body) {
      runtime.setActiveRt(e.body)
      const msg = e.body.details?.primary_diagnostic?.message || e.body.message || e.body.error
      toast.error('执行失败', msg || e?.message)
    } else { toast.error('执行失败', e?.message) }
  } finally {loading.value=''}
}
async function rtDetail(id: string) { try { const r = await fetchRuntimeSession(id); runtime.setActiveRt(r) } catch(e:any){toast.error('查询失败',e?.message)} }
async function dbPrepare() {
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，无法调试'); return }
  loading.value='db-prepare'; try { await postDebugPrepare(graphBody()); toast.success('Debug 已就绪'); await runtime.refreshAll() } catch(e:any){toast.error('准备失败',e?.message)} finally {loading.value=''}
}
async function dbStart() {
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，无法调试'); return }
  loading.value='db-start'; try {
    const r = await postDebugStart(graphBody())
    runtime.setActiveDb(r); toast.success('已启动', r.debug_session.session_id ?? '')
    await runtime.refreshAll()
  } catch(e:any){
    if (e?.body) {
      runtime.setActiveDb(e.body)
      const msg = e.body.details?.primary_diagnostic?.message || e.body.message || e.body.error
      toast.error('启动失败', msg || e?.message)
    } else { toast.error('启动失败', e?.message) }
  } finally {loading.value=''}
}
async function dbDetail(id: string) { try { const r = await fetchDebugSession(id); runtime.setActiveDb(r) } catch(e:any){toast.error('查询失败',e?.message)} }

async function startAndRun() {
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，无法执行'); return }
  loading.value = 'start-run'
  // Auto-open output panel and switch to Runtime tab
  const dock = useDockStore()
  if (!dock.isPanelVisible('output')) dock.restorePanel('output')
  runtime.requestRuntimeTab()
  try {
    const result = await runtime.startAndRun(
      graphWs.graphModel as Record<string, unknown> | undefined,
      graphWs.isDirty,
    )
    try { execHistory.value = await fetchExecutionHistory() } catch {}
    if (result.success) {
      toast.success('运行完成', result.message)
    } else {
      toast.error('运行失败', result.message)
    }
  } catch (e: any) {
    toast.error('运行失败', e?.message)
  }
  finally { loading.value = '' }
}
</script>

<template>
  <div class="tep">
    <div class="tep-bar">
      <button class="tep-btn" @click="rtPrepare" :disabled="!!loading">Runtime Prepare</button>
      <button class="tep-btn" @click="rtStart" :disabled="!!loading">Runtime Start</button>
      <button class="tep-btn" @click="dbPrepare" :disabled="!!loading">Debug Prepare</button>
      <button class="tep-btn" @click="dbStart" :disabled="!!loading">Debug Start</button>
      <span class="tep-sep">|</span>
      <button class="tep-btn primary" @click="startAndRun" :disabled="!!loading">▶ 一键运行</button>
      <span v-if="loading" class="tep-loading">{{ loading }}</span>
    </div>

    <!-- Live Progress -->
    <div v-if="runtime.runtimeProgress && runtime.runtimeProgress.total_node_count > 0" class="tep-progress">
      <div class="tep-pg-bar-wrap">
        <div class="tep-pg-bar" :style="{ width: (runtime.runtimeProgress.percent ?? 0) + '%' }" :class="{ done: runtime.runtimeLiveStatus === 'completed', fail: runtime.runtimeLiveStatus === 'failed' }"></div>
      </div>
      <div class="tep-pg-info">
        <span>{{ runtime.runtimeProgress.percent ?? 0 }}%</span>
        <span>总节点 {{ runtime.runtimeProgress.total_node_count ?? 0 }}</span>
        <span class="ok">完成 {{ runtime.runtimeProgress.completed_node_count ?? 0 }}</span>
        <span v-if="runtime.runtimeProgress.failed_node_count" class="fail">失败 {{ runtime.runtimeProgress.failed_node_count }}</span>
        <span v-if="runtime.runtimeProgress.running_node_count" class="running">运行中 {{ runtime.runtimeProgress.running_node_count }}</span>
      </div>
      <div class="tep-pg-live">
        <span v-if="runtime.runtimeLiveStatus === 'connecting'" class="connecting">⏳ 正在连接…</span>
        <span v-else-if="runtime.runtimeLiveStatus === 'streaming'" class="streaming">⟳ 实时同步中</span>
        <span v-else-if="runtime.runtimeLiveStatus === 'completed'" class="done">✓ 运行完成</span>
        <span v-else-if="runtime.runtimeLiveStatus === 'failed'" class="fail">✕ 运行失败</span>
        <span v-else-if="runtime.runtimeLiveStatus === 'disconnected'" class="disconnected">⚠ 实时连接中断（数据已保留）</span>
        <span v-else-if="runtime.runtimeLiveStatus === 'error'" class="fail">⚠ 实时连接错误</span>
      </div>
    </div>

    <div class="tep-grid">
      <div class="tep-col">
        <h4>Runtime 会话 ({{ runtime.rtSessions.length }})</h4>
        <div v-if="!runtime.rtSessions.length" class="tep-empty">暂无</div>
        <div v-for="s in runtime.rtSessions" :key="s.session_id" class="tep-row">
          <span :class="['tep-st', s.status === 'completed' ? 'ok' : s.status === 'failed' ? 'fail' : '']">{{ s.status }}</span>
          <span class="tep-sid">{{ s.session_id.slice(0,12) }}</span>
          <button class="tep-sm" @click="rtDetail(s.session_id)">详</button>
          <button v-if="s.status !== 'completed'" class="tep-sm" @click="rtRun(s.session_id)">▶</button>
        </div>
        <div v-if="runtime.activeRt" class="tep-detail">
          <strong>{{ runtime.activeRt.runtime_session.session_id }}</strong>
          <div>状态: {{ runtime.activeRt.status }}</div>
          <div v-if="runtime.activeRt.runtime_plan">节点: {{ runtime.activeRt.runtime_plan.node_count }}</div>
          <div v-if="runtime.activeRt.event_log?.length">事件: {{ runtime.activeRt.event_log.length }} 条</div>
          <div v-if="runtime.activeRt.node_states?.length">节点状态: {{ runtime.activeRt.node_states.length }} 个</div>
        </div>
      </div>

      <div class="tep-col">
        <h4>Debug 会话 ({{ runtime.dbSessions.length }})</h4>
        <div v-if="!runtime.dbSessions.length" class="tep-empty">暂无</div>
        <div v-for="s in runtime.dbSessions" :key="s.session_id" class="tep-row">
          <span :class="['tep-st', s.status === 'ready' ? 'ok' : '']">{{ s.status }}</span>
          <span class="tep-sid">{{ s.session_id.slice(0,12) }}</span>
          <button class="tep-sm" @click="dbDetail(s.session_id)">详</button>
        </div>
        <div v-if="runtime.activeDb" class="tep-detail">
          <strong>{{ runtime.activeDb.debug_session.session_id }}</strong>
          <div>阶段: {{ runtime.activeDb.stage_timeline?.length ?? 0 }}</div>
          <div v-if="runtime.activeDb.object_index">对象: {{ runtime.activeDb.object_index.nodes.length }}N / {{ runtime.activeDb.object_index.edges.length }}E</div>
        </div>
      </div>
    </div>

    <div class="tep-section">
      <h4>执行历史</h4>
      <div v-if="!execHistory" class="tep-empty">暂无</div>
      <template v-else>
        <div class="tep-summary">Runtime: {{ execHistory.summary.runtime_run_count }} · Debug: {{ execHistory.summary.debug_session_count }}</div>
        <div class="tep-sub" v-if="execHistory.runtime_runs.length">
          <h5>Runtime 运行</h5>
          <div v-for="(r, i) in execHistory.runtime_runs" :key="i" class="tep-row">
            <span>{{ (r as any).status ?? '—' }}</span>
            <span class="tep-sid">{{ ((r as any).session_id ?? '').slice(0,12) }}</span>
          </div>
        </div>
        <div class="tep-sub" v-if="execHistory.debug_sessions.length">
          <h5>Debug 会话</h5>
          <div v-for="(d, i) in execHistory.debug_sessions" :key="i" class="tep-row">
            <span>{{ (d as any).status ?? '—' }}</span>
            <span class="tep-sid">{{ ((d as any).session_id ?? '').slice(0,12) }}</span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.tep { padding: var(--space-sm); overflow-y: auto; font-size: var(--text-small); height: 100%; }
.tep-bar { display: flex; gap: var(--space-xs); margin-bottom: var(--space-sm); flex-wrap: wrap; align-items: center; }
.tep-btn { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); }
.tep-btn:hover:not(:disabled) { background: var(--bg-hover); }
.tep-btn:disabled { opacity: 0.5; }
.tep-btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.tep-btn.primary:hover:not(:disabled) { background: var(--accent-hover); }
.tep-sep { color: var(--border-default); font-size: var(--text-small); }
.tep-loading { color: var(--text-disabled); }
.tep-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); margin-bottom: var(--space-md); }
.tep-col h4, .tep-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); }
.tep-empty { color: var(--text-disabled); padding: var(--space-sm); }
.tep-row { display: flex; align-items: center; gap: var(--space-xs); padding: 1px 0; }
.tep-st { font-size: var(--text-caption); font-weight: 600; color: var(--text-disabled); }
.tep-st.ok { color: var(--state-success); }
.tep-st.fail { color: var(--state-error); }
.tep-sid { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.tep-sm { padding: 0 4px; border: 1px solid var(--border-subtle); background: transparent; color: var(--text-secondary); cursor: pointer; border-radius: 2px; font-size: var(--text-caption); }
.tep-detail { margin-top: var(--space-xs); padding: var(--space-xs); background: var(--bg-input); border-radius: var(--radius-sm); }
.tep-detail strong { font-size: var(--text-caption); color: var(--text-primary); }
.tep-summary { color: var(--text-disabled); margin-bottom: var(--space-xs); }
.tep-sub { margin-top: var(--space-xs); }
.tep-sub h5 { font-size: var(--text-caption); font-weight: 600; color: var(--text-secondary); }

.tep-progress { padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); }
.tep-pg-bar-wrap { height: 6px; background: var(--bg-input); border-radius: 3px; overflow: hidden; margin-bottom: 4px; }
.tep-pg-bar { height: 100%; background: var(--accent); border-radius: 3px; transition: width 300ms ease-out; }
.tep-pg-bar.done { background: var(--state-success); }
.tep-pg-bar.fail { background: var(--state-error); }
.tep-pg-info { display: flex; gap: var(--space-md); font-size: var(--text-caption); color: var(--text-secondary); margin-bottom: 2px; }
.tep-pg-info .ok { color: var(--state-success); }
.tep-pg-info .fail { color: var(--state-error); }
.tep-pg-info .running { color: var(--accent); }
.tep-pg-live { font-size: var(--text-caption); }
.tep-pg-live .connecting { color: var(--state-warning); }
.tep-pg-live .streaming { color: var(--accent); }
.tep-pg-live .done { color: var(--state-success); }
.tep-pg-live .fail { color: var(--state-error); }
.tep-pg-live .disconnected { color: var(--state-warning); }
</style>
