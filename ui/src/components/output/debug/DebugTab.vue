<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useToastStore } from '@/stores/toastStore'
import { useDebugStore } from '@/stores/debugStore'
import { useDockStore } from '@/stores/dockStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import { t } from '@/i18n'
import { locateGraphNode } from '@/services/graphNodeNavigation'

const toast = useToastStore()
const debugStore = useDebugStore()
const dock = useDockStore()
const graphWs = useGraphWorkspaceStore()
const workspaceStore = useWorkspaceStore()

function graphBody() {
  if (!graphWs.graphModel) return undefined
  if (workspaceStore.snapshot?.project?.loaded && !graphWs.isDirty) return undefined
  return { graph_document: graphWs.graphModel as unknown as Record<string, unknown> }
}
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(() => { void debugStore.refreshSessions() })

// Single truth source: debugStore.activeSession
const activeSessionId = computed(() =>
  debugStore.activeSession?.debug_session?.session_id || null
)
const activeDoc = computed(() => debugStore.activeSession)
const historyDoc = computed(() => debugStore.activeHistorySession)

async function doStart() {
  loading.value = true; error.value = null
  const r = await debugStore.startDebugSession(graphBody())
  if (r.phase === 'started') {
    toast.success(t('framework.debug.tab.debugStarted', 'Debug 已启动'), r.sessionId ?? '')
  } else if (r.phase === 'started_with_sync_warning') {
    toast.success(t('framework.debug.tab.debugStarted', 'Debug 已启动'), r.sessionId ?? '')
    toast.error(t('framework.debug.tab.panelSyncFailed', '面板同步失败'), r.syncError ?? '')
  } else if (r.phase === 'unlock_required') {
    toast.success(t('framework.debug.tab.unlockRequired', '等待参数解锁'), r.sessionId ?? '')
  } else {
    error.value = r.startError ?? ''
    toast.error(t('framework.debug.tab.debugStartFailed', 'Debug 启动失败'), error.value ?? '')
  }
  loading.value = false
}

function statusClass(s: string): string {
  if (['completed'].includes(s)) return 'ok'
  if (['preparing', 'running', 'stepping', 'paused'].includes(s)) return 'info'
  return 'fail'
}

async function doControl(action: string) {
  const sid = activeSessionId.value
  if (!sid) return
  const labels: Record<string, string> = {
    continue: t('framework.debug.tab.continue', '继续'),
    'step-over': t('framework.debug.tab.stepOver', '单步跳过'),
    'step-into': t('framework.debug.tab.stepInto', '单步进入'),
    'step-out': t('framework.debug.tab.stepOut', '单步跳出'),
    pause: t('framework.debug.tab.pause', '暂停'),
    abort: t('framework.debug.tab.abort', '中止'),
  }
  let session: any = null
  try {
    if (action === 'continue') session = await debugStore.doContinue(sid)
    else if (action === 'step-over') session = await debugStore.doStepOver(sid)
    else if (action === 'step-into') session = await debugStore.doStepInto(sid)
    else if (action === 'step-out') session = await debugStore.doStepOut(sid)
    else if (action === 'pause') session = await debugStore.doPause(sid)
    else if (action === 'abort') session = await debugStore.doAbort(sid)
  } catch (e: any) {
    toast.error(t('framework.debug.tab.actionFailed', `${labels[action]}失败`, { action: labels[action] }), e?.message)
    return
  }
  if (session) {
    toast.success(labels[action], t('framework.debug.tab.statusLabel', `状态: ${session.status}`, { status: session.status }))
    try {
      await debugStore.pollOnce(sid, { throwOnError: true })
    } catch (e: any) {
      toast.error(t('framework.debug.tab.panelSyncFailed', '面板同步失败'), e?.message)
    }
  }
}

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    preparing: t('framework.debug.tab.status.preparing', '准备中'),
    running: t('framework.debug.tab.status.running', '运行中'),
    paused: t('framework.debug.tab.status.paused', '已暂停'),
    stepping: t('framework.debug.tab.status.stepping', '单步中'),
    completed: t('framework.debug.tab.status.completed', '已完成'),
    failed: t('framework.debug.tab.status.failed', '失败'),
    cancelled: t('framework.debug.tab.status.cancelled', '已取消'),
    aborted: t('framework.debug.tab.status.aborted', '已中止'),
    incomplete: t('framework.debug.tab.status.incomplete', '未完成'),
  }
  return m[s] || s
}

async function loadHistorySession(sid: string) {
  await debugStore.loadHistorySession(sid)
  await debugStore.loadProjection(sid, 'history')
  await debugStore.loadEvents(sid)
}

const currentNodeId = computed(() => (debugStore.activeSession?.runtime_preview as any)?.current_node?.node_id || null)

function panToCurrentNode() {
  const nid = currentNodeId.value
  if (nid) void locateGraphNode(nid)
}

// Auto-pan to current executing node (covers running, paused, stepping)
let lastPanNodeId: string | null = null
watch(() => ({
  nodeId: (debugStore.activeSession?.runtime_preview as any)?.current_node?.node_id,
  status: debugStore.activeSession?.debug_session?.status,
}), ({ nodeId, status }) => {
  if (nodeId && ['running', 'paused', 'stepping'].includes(status || '') && nodeId !== lastPanNodeId) {
    const nid = nodeId
    lastPanNodeId = nid
    void locateGraphNode(nid)
  }
})
</script>

<template>
  <div class="dbg-tab">
    <PlaceholderBanner v-if="!loading && !activeDoc" type="empty" :title="t('framework.debug.tab.emptyTitle', '尚未启动 Debug')"
      :description="t('framework.debug.tab.emptyDescription', '从此面板或任务执行窗口启动调试')" />
    <div v-if="loading" class="loading"><div class="sk skeleton-pulse"></div></div>
    <div v-if="error" class="db-err">✕ {{ error }}</div>

    <!-- Toolbar -->
    <div class="db-tb">
      <button class="db-btn" @click="doStart" :disabled="loading || debugStore.isDebugActive">Debug Start</button>
      <button class="db-btn-sm" @click="dock.restorePanel('debugVariables')" :title="t('framework.debug.tab.openVariablesTitle', '打开变量窗口')">{{ t('framework.debug.tab.variables', '变量') }}</button>
      <button class="db-btn-sm" @click="dock.restorePanel('debugTimeline')" :title="t('framework.debug.tab.openEventsTitle', '打开事件窗口')">{{ t('framework.debug.tab.events', '事件') }}</button>
      <button class="db-btn-sm" @click="dock.restorePanel('debugSnapshots')" :title="t('framework.debug.tab.openSnapshotsTitle', '打开快照窗口')">{{ t('framework.debug.tab.snapshots', '快照') }}</button>
      <button class="db-btn-sm" @click="panToCurrentNode()" :disabled="!currentNodeId" :title="t('framework.debug.tab.panToNodeTitle', '定位到当前运行节点')">{{ t('framework.debug.tab.panToNode', '📍 定位节点') }}</button>
      <template v-if="activeSessionId">
        <span class="db-session-badge">{{ activeSessionId }}</span>
      </template>
    </div>

    <!-- Active session (from debugStore) -->
    <template v-if="activeDoc">
      <div class="db-section">
        <div class="db-sect-hd">
          <span class="db-badge" :class="statusClass(activeDoc.status)">{{ statusLabel(activeDoc.status) }}</span>
          <span v-if="activeDoc.debug_session.step_mode" class="db-meta">{{ t('framework.debug.tab.stepMode', '步进模式') }}: {{ activeDoc.debug_session.step_mode }}</span>
          <span v-if="activeDoc.debug_session.paused_reason" class="db-meta">{{ t('framework.debug.tab.pausedReason', '暂停原因') }}: {{ activeDoc.debug_session.paused_reason }}</span>
        </div>

        <!-- Control buttons -->
        <div class="db-ctls">
          <button class="db-ctl-btn" :disabled="debugStore.controlLoading || activeDoc.debug_session.status !== 'paused'" @click="doControl('continue')">{{ t('framework.debug.tab.btnContinue', '▶ 继续') }}</button>
          <button class="db-ctl-btn" :disabled="debugStore.controlLoading || !['running','stepping'].includes(activeDoc.debug_session.status)" @click="doControl('pause')">{{ t('framework.debug.tab.btnPause', '⏸ 暂停') }}</button>
          <button class="db-ctl-btn" :disabled="debugStore.controlLoading || activeDoc.debug_session.status !== 'paused'" @click="doControl('step-over')">{{ t('framework.debug.tab.btnStepOver', '⤵ 单步跳过') }}</button>
          <button class="db-ctl-btn" :disabled="debugStore.controlLoading || activeDoc.debug_session.status !== 'paused'" @click="doControl('step-into')">{{ t('framework.debug.tab.btnStepInto', '↓ 单步进入') }}</button>
          <button class="db-ctl-btn" :disabled="debugStore.controlLoading || activeDoc.debug_session.status !== 'paused' || !activeDoc.debug_session.can_step_out" @click="doControl('step-out')">{{ t('framework.debug.tab.btnStepOut', '↑ 单步跳出') }}</button>
          <button class="db-ctl-btn db-ctl-abort" :disabled="debugStore.controlLoading || !['preparing','running','paused','stepping'].includes(activeDoc.debug_session.status)" @click="doControl('abort')">{{ t('framework.debug.tab.btnAbort', '✕ 中止') }}</button>
        </div>
        <div v-if="debugStore.controlLoading" class="db-meta">{{ t('framework.debug.tab.requestSent', '已发送请求…') }}</div>
      </div>

      <!-- Graph projection summary -->
      <div class="db-section" v-if="debugStore.projection">
        <h4>{{ t('framework.debug.tab.projectionTitle', '图投影摘要') }} {{ debugStore.projection.mode === 'live' ? t('framework.debug.tab.projectionLive', '(实时)') : t('framework.debug.tab.projectionHistory', '(历史)') }}</h4>
        <div class="db-meta">
          {{ t('framework.debug.tab.projectionRunning', '运行中') }} {{ Object.values(debugStore.projection.node_status_by_id).filter(s => s === 'running').length }}
          · {{ t('framework.debug.tab.projectionWaiting', '等待中') }} {{ Object.values(debugStore.projection.node_status_by_id).filter(s => s === 'waiting').length }}
          · {{ t('framework.debug.tab.projectionCompleted', '已完成') }} {{ Object.values(debugStore.projection.node_status_by_id).filter(s => s === 'completed').length }}
        </div>
        <div v-if="debugStore.projection.paused_node_id" class="db-meta">{{ t('framework.debug.tab.projectionPausedNode', '暂停节点') }}: {{ debugStore.projection.paused_node_id }}</div>
        <div v-if="debugStore.projection.active_paths?.length" class="db-meta">{{ t('framework.debug.tab.projectionActivePaths', `活跃路径: ${debugStore.projection.active_paths.length} 条`, { n: debugStore.projection.active_paths.length }) }}</div>
      </div>

      <!-- Debug events -->
      <div class="db-section" v-if="debugStore.events.length">
        <h4>{{ t('framework.debug.tab.debugEvents', '调试事件') }} ({{ debugStore.eventsTotal }})</h4>
        <div v-for="ev in debugStore.events" :key="ev.event_id || `event-${ev.event_index}`"
          :data-event-id="ev.event_id || ''"
          :class="['db-ev', `db-ev-${ev.event_kind.replace('.','-')}`]">
          <span class="db-ev-kind">{{ ev.event_kind }}</span>
          <span v-if="ev.reason" class="db-ev-reason">{{ ev.reason }}</span>
          <span v-if="ev.node_id" class="db-ev-node">→ {{ ev.node_id }}</span>
          <span v-if="ev.frame_identity" class="db-ev-frame">{{ ev.frame_identity.slice(0, 8) }}</span>
          <span v-if="ev.pause_timing" class="db-ev-meta">{{ ev.pause_timing }}</span>
        </div>
      </div>

      <!-- Object index -->
      <div class="db-section" v-if="activeDoc.object_index">
        <h4>{{ t('framework.debug.tab.objectIndex', '对象索引') }}</h4>
        <span>{{ t('framework.debug.tab.objectIndexNodes', '节点') }}: {{ activeDoc.object_index.nodes.length }} · {{ t('framework.debug.tab.objectIndexPorts', '端口') }}: {{ activeDoc.object_index.ports.length }} · {{ t('framework.debug.tab.objectIndexEdges', '边') }}: {{ activeDoc.object_index.edges.length }}</span>
      </div>

      <!-- Variable snapshot -->
      <div class="db-section" v-if="activeDoc.variable_snapshot && Object.keys(activeDoc.variable_snapshot).length">
        <h4>{{ t('framework.debug.tab.variableSnapshot', '变量快照') }}</h4>
        <div class="db-var-grid">
          <div v-for="(v, k) in activeDoc.variable_snapshot" :key="k" class="db-var-item">
            <span class="db-var-key">{{ k }}</span>
            <code class="db-var-value">{{ typeof v === 'object' ? JSON.stringify(v) : String(v) }}</code>
          </div>
        </div>
      </div>

    </template>

    <!-- History session detail -->
    <template v-if="historyDoc">
      <div class="db-section">
        <h4>{{ t('framework.debug.tab.historySessionDetail', '历史会话详情') }}</h4>
        <div class="db-sect-hd">
          <span class="db-badge ok">{{ historyDoc.source }}</span>
          <span class="db-sid">{{ historyDoc.session_id }}</span>
        </div>
      </div>
    </template>

    <!-- Active sessions list -->
    <div class="db-section" v-if="debugStore.sessions.length">
      <h4>{{ t('framework.debug.tab.activeSessions', '活动会话') }} ({{ debugStore.sessions.length }})</h4>
      <div v-for="s in debugStore.sessions" :key="s.session_id" class="db-row"
        @click="debugStore.loadActiveSession(s.session_id); debugStore.loadProjection(s.session_id, 'live'); debugStore.loadEvents(s.session_id); ['preparing','running','paused','stepping'].includes(s.status) && debugStore.startPolling(s.session_id)">
        <span class="db-badge" :class="statusClass(s.status)">{{ statusLabel(s.status) }}</span>
        <span class="db-sid">{{ s.session_id }}</span>
      </div>
    </div>

    <!-- History sessions -->
    <div class="db-section" v-if="debugStore.historySessions.length">
      <h4>{{ t('framework.debug.tab.historySessions', '历史会话') }} ({{ debugStore.historySessions.length }})</h4>
      <div v-for="(s, i) in debugStore.historySessions" :key="String((s as any).session_id ?? i)" class="db-row"
        @click="loadHistorySession((s as any).session_id)">
        <span class="db-badge" :class="statusClass((s as any).status ?? 'unknown')">{{ statusLabel((s as any).status ?? 'unknown') }}</span>
        <span class="db-sid">{{ (s as any).session_id ?? '—' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dbg-tab { padding: var(--space-md); overflow-y: auto; height: 100%; }
.loading { padding: var(--space-lg); } .sk { height: 60px; background: var(--bg-panel-header); border-radius: var(--radius-sm); }
.db-err { padding: var(--space-md); color: var(--state-error); font-size: var(--text-body); }
.db-tb { display: flex; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-md); min-height: 30px; }
.db-session-badge { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.db-section { margin-bottom: var(--space-md); }
.db-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); }
.db-sect-hd { display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap; }
.db-badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm); font-size: var(--text-small); font-weight: 600; }
.db-badge.ok { background: rgba(107,154,102,0.12); color: var(--state-success); }
.db-badge.info { background: rgba(107,154,168,0.12); color: var(--state-info); }
.db-badge.fail { background: rgba(208,112,96,0.12); color: var(--state-error); }
.db-meta { font-size: var(--text-caption); color: var(--text-disabled); }
.db-ctls { display: flex; gap: var(--space-xs); margin: var(--space-sm) 0; flex-wrap: wrap; min-height: 30px; align-items: center; }
.db-ctl-btn { padding: 3px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.db-ctl-btn:hover:not(:disabled) { background: var(--bg-hover); border-color: var(--accent); }
.db-ctl-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.db-ctl-abort { border-color: var(--state-error); color: var(--state-error); }
.db-ctl-abort:hover:not(:disabled) { background: rgba(208,112,96,0.08); }
.db-proj-grid { display: flex; flex-wrap: wrap; gap: var(--space-xs); margin: var(--space-xs) 0; }
.db-proj-node { display: flex; align-items: center; gap: 2px; padding: 1px var(--space-sm); border-radius: var(--radius-sm); font-size: var(--text-caption); font-family: var(--font-mono); }
.db-proj-running { background: rgba(107,154,168,0.12); color: var(--state-info); }
.db-proj-waiting { background: rgba(0,0,0,0.04); color: var(--text-disabled); }
.db-proj-completed { background: rgba(107,154,102,0.12); color: var(--state-success); }
.db-proj-id { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.db-ev { display: flex; gap: var(--space-sm); align-items: center; padding: 2px 4px; font-size: var(--text-caption); border-bottom: 1px solid var(--border-subtle); }
.db-ev-kind { font-weight: 600; color: var(--state-info); min-width: 100px; }
.db-ev-reason { color: var(--state-warning); font-style: italic; }
.db-ev-node { font-family: var(--font-mono); color: var(--text-primary); }
.db-ev-frame { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.db-ev-meta { color: var(--text-disabled); }
.db-var-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 2px 8px; }
.db-var-item { display: contents; font-size: var(--text-caption); }
.db-var-key { color: var(--accent); font-weight: 500; }
.db-var-value { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); }
.db-var-row { display: flex; gap: 4px; align-items: center; margin: 4px 0; }
.db-var-input { padding: 2px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); min-width: 80px; }
.db-row { display: flex; gap: var(--space-xs); font-size: var(--text-small); padding: 2px 0; cursor: pointer; }
.db-row:hover { background: var(--bg-hover); }
.db-sid { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.db-btn { padding: 6px 16px; border: 1px solid var(--accent); background: var(--accent); color: #fff; cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); }
.db-btn:hover:not(:disabled) { background: var(--accent-hover); }
.db-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.db-btn-sm { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); }
.db-btn-sm:hover { background: var(--bg-hover); }
.db-raw { font-family: var(--font-mono); font-size: 10px; background: var(--bg-input); padding: var(--space-sm); border-radius: var(--radius-sm); max-height: 250px; overflow: auto; white-space: pre-wrap; margin-bottom: var(--space-sm); }
</style>
