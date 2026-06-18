<script setup lang="ts">
import { ref } from 'vue'
import { postDebugPrepare } from '@/services/api'
import { useToastStore } from '@/stores/toastStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import type { DebugPrepareResponse } from '@/types/domains/api'

const toast = useToastStore()
const runtime = useRuntimeStore()
const loading = ref(false)
const result = ref<DebugPrepareResponse | null>(null)
const error = ref<string | null>(null)
const showRaw = ref(false)

async function prepare() {
  loading.value = true; error.value = null
  try { result.value = await postDebugPrepare(); if (result.value.status === 'ready') toast.success('Debug 就绪', result.value.debug_session.session_id) }
  catch (e: any) { error.value = e?.message ?? '请求失败'; toast.error('Debug 失败', error.value ?? undefined) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="dbg-tab">
    <PlaceholderBanner v-if="!result && !loading && !runtime.activeDb" type="empty" title="Debug 准备"
      description="发起 Debug Prepare 或在任务执行窗口操作" />
    <div v-if="loading" class="loading"><div class="sk skeleton-pulse"></div></div>
    <div v-if="error" class="db-err">✕ {{ error }}</div>

    <template v-if="runtime.activeDb">
      <div class="db-section">
        <div class="db-badge" :class="runtime.activeDb.status === 'ready' ? 'ok' : 'fail'">{{ runtime.activeDb.status }}</div>
        <span class="db-id">{{ runtime.activeDb.debug_session.session_id }}</span>
      </div>
      <div class="db-section" v-if="runtime.activeDb.object_index">
        <h4>对象索引</h4>
        <span>节点: {{ runtime.activeDb.object_index.nodes.length }} · 端口: {{ runtime.activeDb.object_index.ports.length }} · 边: {{ runtime.activeDb.object_index.edges.length }}</span>
      </div>
      <div class="db-section" v-if="runtime.dbSessions.length">
        <h4>会话 ({{ runtime.dbSessions.length }})</h4>
        <div v-for="s in runtime.dbSessions" :key="s.session_id" class="db-row">
          <span>{{ s.status }}</span>
          <span class="db-sid">{{ s.session_id.slice(0,12) }}</span>
        </div>
      </div>
    </template>

    <div class="db-section" v-if="(runtime.activeRt as any)?.event_log?.length">
      <h4>事件日志 ({{ (runtime.activeRt as any).event_log.length }})</h4>
      <div v-for="(ev, i) in (runtime.activeRt as any).event_log" :key="i" class="db-log-item">
        <span class="rt-log-kind">{{ (ev as any).event_kind || '' }}</span>
        <span class="rt-log-msg">{{ (ev as any).message || (ev as any).error_code || JSON.stringify(ev) }}</span>
      </div>
    </div>

    <div class="db-actions">
      <button class="db-btn" @click="prepare" :disabled="loading">Prepare</button>
      <button class="db-btn-sm" @click="showRaw = !showRaw">{{ showRaw ? '隐藏' : '显示' }}原始 JSON</button>
    </div>
    <div v-if="showRaw">
      <h4>Runtime Session</h4>
      <pre class="db-raw">{{ JSON.stringify(runtime.activeRt ?? {}, null, 2) }}</pre>
      <h4>Debug Session</h4>
      <pre class="db-raw">{{ JSON.stringify(runtime.activeDb ?? {}, null, 2) }}</pre>
    </div>
  </div>
</template>

<style scoped>
.dbg-tab { padding: var(--space-lg); }
.loading { padding: var(--space-lg); } .sk { height: 60px; background: var(--bg-panel-header); border-radius: var(--radius-sm); }
.db-err { padding: var(--space-md); color: var(--state-error); font-size: var(--text-body); }
.db-section { margin-bottom: var(--space-lg); }
.db-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); }
.db-badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm); font-size: var(--text-small); font-weight: 600; margin-right: var(--space-sm); }
.db-badge.ok { background: rgba(107,154,102,0.12); color: var(--state-success); }
.db-badge.fail { background: rgba(208,112,96,0.12); color: var(--state-error); }
.db-id { font-family: var(--font-mono); font-size: var(--text-small); color: var(--text-disabled); }
.db-row { display: flex; gap: var(--space-xs); font-size: var(--text-small); }
.db-sid { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.db-actions { margin-top: var(--space-lg); }
.db-btn { padding: 6px 16px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); }
.db-btn:hover:not(:disabled) { background: var(--bg-hover); }
.db-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.db-log-item { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-secondary); padding: 1px 0; }
.db-btn-sm { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); margin-left: var(--space-sm); }
.db-btn-sm:hover { background: var(--bg-hover); }
.db-raw { font-family: var(--font-mono); font-size: 10px; background: var(--bg-input); padding: var(--space-sm); border-radius: var(--radius-sm); max-height: 250px; overflow: auto; white-space: pre-wrap; margin-bottom: var(--space-sm); }
</style>
