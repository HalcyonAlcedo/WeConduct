<script setup lang="ts">
import { ref } from 'vue'
import { useRuntimeStore } from '@/stores/runtimeStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'

const runtime = useRuntimeStore()
const showRaw = ref(false)

const STRUCTURED_KEYS = new Set(['headers', 'row_count', 'cookie_count', 'local_storage_origin_count', 'dialog_count', 'handled_count', 'value', 'path', 'sheet_name', 'rows', 'dialogs'])
function hasStructuredFields(output: any): boolean {
  return STRUCTURED_KEYS.has(Object.keys(output || {}).find(k => output[k] !== undefined) || '')
}
</script>
<template>
  <div class="rt-tab">
    <PlaceholderBanner v-if="!runtime.activeRt" type="empty" title="Runtime"
      description="在任务执行窗口操作或导入项目后运行" />

    <template v-if="runtime.activeRt">
      <!-- Session Header -->
      <div class="rt-section">
        <div class="rt-header">
          <span class="rt-badge" :class="runtime.activeRt.status === 'completed' ? 'ok' : runtime.activeRt.status === 'failed' ? 'fail' : ''">{{ runtime.activeRt.status }}</span>
          <span class="rt-id">{{ runtime.activeRt.runtime_session.session_id ?? '—' }}</span>
        </div>
      </div>

      <!-- Node States -->
      <div class="rt-section" v-if="runtime.activeRt.node_states?.length">
        <h4>节点状态 ({{ runtime.activeRt.node_states.length }})</h4>
        <div v-for="ns in runtime.activeRt.node_states" :key="(ns as any).node_id" class="rt-node">
          <div class="rt-node-header">
            <span :class="['rt-node-dot', (ns as any).node_status === 'completed' ? 'ok' : (ns as any).node_status === 'failed' ? 'fail' : (ns as any).node_status === 'running' ? 'running' : '']"></span>
            <span class="rt-node-name">{{ (ns as any).display_name || (ns as any).node_id }}</span>
            <span class="rt-node-status">{{ (ns as any).node_status }}</span>
          </div>
          <div v-if="(ns as any).output" class="rt-node-output">
            <div v-if="(ns as any).output.error_code" class="rt-node-err">
              <strong>{{ (ns as any).output.error_code }}</strong>: {{ (ns as any).output.message }}
            </div>
            <div v-else class="rt-node-ok">
              <!-- Structured output fields -->
              <template v-if="(ns as any).output.headers">{{ (ns as any).output.headers?.join?.(', ') || JSON.stringify((ns as any).output.headers) }}</template>
              <div v-if="(ns as any).output.row_count !== undefined" class="rt-field"><span>行数:</span> {{ (ns as any).output.row_count }}</div>
              <div v-if="(ns as any).output.cookie_count !== undefined" class="rt-field"><span>Cookie 数:</span> {{ (ns as any).output.cookie_count }}</div>
              <div v-if="(ns as any).output.local_storage_origin_count !== undefined" class="rt-field"><span>LocalStorage:</span> {{ (ns as any).output.local_storage_origin_count }}</div>
              <div v-if="(ns as any).output.dialog_count !== undefined" class="rt-field"><span>对话框数:</span> {{ (ns as any).output.dialog_count }}</div>
              <div v-if="(ns as any).output.handled_count !== undefined" class="rt-field"><span>已处理:</span> {{ (ns as any).output.handled_count }}</div>
              <div v-if="(ns as any).output.value !== undefined" class="rt-field"><span>值:</span> {{ (ns as any).output.value }}</div>
              <div v-if="(ns as any).output.path" class="rt-field"><span>路径:</span> {{ (ns as any).output.path }}</div>
              <div v-if="(ns as any).output.sheet_name" class="rt-field"><span>Sheet:</span> {{ (ns as any).output.sheet_name }}</div>
              <!-- Fallback: show remaining as JSON -->
              <div v-if="typeof (ns as any).output === 'object' && !hasStructuredFields((ns as any).output)" class="rt-node-json">{{ JSON.stringify((ns as any).output) }}</div>
            </div>
          </div>
          <div v-if="(ns as any).error" class="rt-node-err">
            <strong>{{ (ns as any).error.error_code || 'error' }}</strong>: {{ (ns as any).error.message }}
            <div v-if="(ns as any).error.exception_type" class="rt-mono">{{ (ns as any).error.exception_type }}</div>
          </div>
        </div>
      </div>

      <!-- Result -->
      <div class="rt-section" v-if="runtime.activeRt.result">
        <h4>结果</h4>
        <div class="rt-grid">
          <span>状态: {{ (runtime.activeRt.result as any).status }}</span>
          <span v-if="(runtime.activeRt.result as any).failure_reason">原因: {{ (runtime.activeRt.result as any).failure_reason }}</span>
        </div>
        <div v-if="(runtime.activeRt.result as any).outputs" class="rt-outputs">
          <div v-for="(v, k) in ((runtime.activeRt.result as any).outputs || {})" :key="k" class="rt-output-item">
            <span class="rt-output-key">{{ k }}</span>
            <span class="rt-output-val">{{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
          </div>
        </div>
      </div>

      <!-- Event Log -->
      <div class="rt-section" v-if="runtime.activeRt.event_log?.length">
        <h4>事件日志 ({{ runtime.activeRt.event_log.length }})</h4>
        <div v-for="(ev, i) in runtime.activeRt.event_log" :key="i" class="rt-log-item">
          <span class="rt-log-kind">{{ (ev as any).event_kind || '' }}</span>
          <span class="rt-log-node">{{ (ev as any).node_id || '' }}</span>
          <span class="rt-log-msg">{{ (ev as any).message || (ev as any).error_code || (ev as any).failure_reason || JSON.stringify(ev) }}</span>
        </div>
      </div>

      <!-- Session List -->
      <div class="rt-section" v-if="runtime.rtSessions.length">
        <h4>会话 ({{ runtime.rtSessions.length }})</h4>
        <div v-for="s in runtime.rtSessions" :key="s.session_id" class="rt-row">
          <span :class="s.status==='completed'?'ok':''">{{ s.status }}</span>
          <span class="rt-sid">{{ s.session_id.slice(0,12) }}</span>
        </div>
      </div>

      <!-- Raw JSON -->
      <div class="rt-actions">
        <button class="rt-btn-sm" @click="showRaw = !showRaw">{{ showRaw ? '隐藏' : '显示' }}原始 JSON</button>
      </div>
      <pre v-if="showRaw" class="rt-raw">{{ JSON.stringify(runtime.activeRt, null, 2) }}</pre>
    </template>
  </div>
</template>
<style scoped>
.rt-tab { padding: var(--space-lg); overflow-y: auto; font-size: var(--text-small); height: 100%; }
.rt-section { margin-bottom: var(--space-lg); }
.rt-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); border-bottom: 1px solid var(--border-subtle); padding-bottom: 2px; }
.rt-header { display: flex; align-items: center; gap: var(--space-sm); }
.rt-badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm); font-size: var(--text-small); font-weight: 600; background: var(--bg-panel-header); color: var(--text-disabled); }
.rt-badge.ok { background: rgba(107,154,102,0.12); color: var(--state-success); }
.rt-badge.fail { background: rgba(208,112,96,0.12); color: var(--state-error); }
.rt-id { font-family: var(--font-mono); font-size: var(--text-small); color: var(--text-disabled); }
.rt-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-xs); color: var(--text-secondary); }
.rt-node { padding: 2px 0; border-bottom: 1px solid var(--border-subtle); }
.rt-node-header { display: flex; align-items: center; gap: 6px; }
.rt-node-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-disabled); flex-shrink: 0; }
.rt-node-dot.ok { background: var(--state-success); }
.rt-node-dot.fail { background: var(--state-error); }
.rt-node-dot.running { background: var(--state-info); animation: stage-pulse 0.8s ease-in-out infinite; }
.rt-node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rt-node-status { font-size: var(--text-caption); color: var(--text-disabled); }
.rt-node-output { margin-left: 14px; font-size: var(--text-caption); }
.rt-node-ok { color: var(--text-secondary); }
.rt-node-err { color: var(--state-error); margin-left: 14px; font-size: var(--text-caption); }
.rt-node-err strong { display: block; }
.rt-mono { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.rt-outputs { margin-top: var(--space-xs); }
.rt-output-item { display: flex; gap: var(--space-sm); font-size: var(--text-caption); }
.rt-output-key { color: var(--text-disabled); font-family: var(--font-mono); }
.rt-output-val { color: var(--text-primary); }
.rt-field { display: flex; gap: var(--space-xs); font-size: var(--text-caption); padding: 1px 0; }
.rt-field span { color: var(--text-disabled); min-width: 60px; }
.rt-node-json { font-family: var(--font-mono); font-size: 10px; color: var(--text-secondary); white-space: pre-wrap; }
.rt-log-item { display: flex; gap: var(--space-sm); font-size: var(--text-caption); padding: 1px 0; }
.rt-log-kind { color: var(--accent); font-family: var(--font-mono); font-weight: 600; flex-shrink: 0; min-width: 80px; }
.rt-log-node { font-family: var(--font-mono); color: var(--text-disabled); flex-shrink: 0; max-width: 100px; overflow: hidden; text-overflow: ellipsis; }
.rt-log-msg { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; }
.rt-row { display: flex; gap: var(--space-xs); font-size: var(--text-small); }
.rt-row .ok { color: var(--state-success); }
.rt-sid { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.rt-actions { margin-top: var(--space-sm); }
.rt-btn-sm { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); }
.rt-btn-sm:hover { background: var(--bg-hover); }
.rt-raw { font-family: var(--font-mono); font-size: 10px; background: var(--bg-input); padding: var(--space-sm); border-radius: var(--radius-sm); max-height: 300px; overflow: auto; white-space: pre-wrap; }
</style>
