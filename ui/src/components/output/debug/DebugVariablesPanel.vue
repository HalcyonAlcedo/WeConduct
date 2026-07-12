<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useDebugStore } from '@/stores/debugStore'
import { useToastStore } from '@/stores/toastStore'

const debugStore = useDebugStore()
const toast = useToastStore()
const drafts = reactive<Record<string, string>>({})
const stagedValues = reactive<Record<string, unknown>>({})
const rowErrors = reactive<Record<string, string>>({})

const isHistory = computed(() => debugStore.projection?.mode === 'history')
const activeDoc = computed(() => debugStore.activeSession)
const historySession = computed(() => debugStore.activeHistorySession?.session as any)
const values = computed<Record<string, unknown>>(() => isHistory.value
  ? (debugStore.projectionVariableSnapshot || {})
  : (activeDoc.value?.variable_snapshot || {}))
const descriptors = computed<Record<string, any>>(() => isHistory.value
  ? (historySession.value?.variable_descriptors || {})
  : ((activeDoc.value as any)?.variable_descriptors || {}))
const changes = computed<Record<string, any>>(() => isHistory.value
  ? (historySession.value?.variable_changes || {})
  : ((activeDoc.value as any)?.variable_changes || {}))
const editMode = computed<'immediate' | 'staged'>(() =>
  activeDoc.value?.debug_session?.variable_apply_mode === 'staged' ? 'staged' : 'immediate')
const rows = computed(() => Object.keys(values.value).map(name => ({
  name,
  value: stagedValues[name] ?? values.value[name],
  descriptor: descriptors.value[name] || { value_type: inferType(values.value[name]), scope: 'dynamic', editable: true },
  change: changes.value[name],
})))

function inferType(value: unknown) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number'
  return typeof value === 'object' ? 'object' : typeof value
}
function encode(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value) }
function parse(name: string, type: string): unknown {
  const raw = drafts[name] ?? encode(stagedValues[name] ?? values.value[name])
  if (type === 'string') return raw
  if (type === 'integer') { const value = Number(raw); if (!Number.isInteger(value)) throw new Error('请输入整数'); return value }
  if (type === 'number') { const value = Number(raw); if (!Number.isFinite(value)) throw new Error('请输入数字'); return value }
  if (type === 'boolean') return raw === 'true'
  if (type === 'null') return null
  return JSON.parse(raw)
}
async function commit(name: string) {
  if (isHistory.value) return
  const sid = activeDoc.value?.debug_session?.session_id
  if (!sid) return
  try {
    const value = parse(name, descriptors.value[name]?.value_type || inferType(values.value[name]))
    rowErrors[name] = ''
    if (editMode.value === 'staged') { stagedValues[name] = value; return }
    await debugStore.applyVariables(sid, { [name]: value }, 'immediate')
    await debugStore.loadActiveSession(sid)
  } catch (error: any) { rowErrors[name] = error?.body?.details?.message || error?.message || '值无效' }
}
async function applyAll() {
  const sid = activeDoc.value?.debug_session?.session_id
  if (!sid || !Object.keys(stagedValues).length) return
  try {
    await debugStore.applyVariables(sid, { ...stagedValues }, 'immediate')
    for (const key of Object.keys(stagedValues)) delete stagedValues[key]
    await debugStore.loadActiveSession(sid)
    toast.success('变量已应用')
  } catch (error: any) { toast.error('应用失败', error?.message) }
}
function discardAll() {
  for (const key of Object.keys(stagedValues)) delete stagedValues[key]
  for (const key of Object.keys(drafts)) delete drafts[key]
}
watch(values, current => {
  for (const [name, value] of Object.entries(current)) if (!(name in drafts)) drafts[name] = encode(value)
}, { immediate: true })
</script>

<template>
  <div class="dvp-root">
    <div v-if="!rows.length" class="dvp-empty">无变量快照</div>
    <template v-else>
      <div class="dvp-toolbar">
        <span>{{ isHistory ? '历史快照只读' : editMode === 'immediate' ? '立即提交' : '暂存编辑' }}</span>
        <span v-if="editMode === 'staged' && !isHistory" class="dvp-actions">
          <button @click="applyAll" :disabled="!Object.keys(stagedValues).length">应用全部</button>
          <button @click="discardAll" :disabled="!Object.keys(stagedValues).length">撤销全部</button>
        </span>
      </div>
      <div class="dvp-table">
        <div class="dvp-head"><span>变量名</span><span>类型</span><span>值</span><span>作用域</span><span>状态</span></div>
        <div v-for="row in rows" :key="row.name" :class="['dvp-row', { changed: row.change || row.name in stagedValues }]">
          <span class="dvp-name">{{ row.name }}</span>
          <span class="dvp-type">{{ row.descriptor.value_type }}</span>
          <span class="dvp-editor">
            <select v-if="row.descriptor.value_type === 'boolean'" v-model="drafts[row.name]" :disabled="isHistory" @change="commit(row.name)"><option value="true">true</option><option value="false">false</option></select>
            <textarea v-else-if="['object','array'].includes(row.descriptor.value_type)" v-model="drafts[row.name]" :disabled="isHistory" rows="2" @keydown.ctrl.enter.prevent="commit(row.name)" @blur="commit(row.name)" />
            <input v-else v-model="drafts[row.name]" :disabled="isHistory || row.descriptor.value_type === 'null'" @keydown.enter.prevent="commit(row.name)" @blur="commit(row.name)" />
            <small v-if="rowErrors[row.name]">{{ rowErrors[row.name] }}</small>
          </span>
          <span>{{ row.descriptor.scope }}</span>
          <span>{{ row.name in stagedValues ? '待应用' : row.change ? '已修改' : '' }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dvp-root { height: 100%; overflow: auto; padding: var(--space-sm); font-size: var(--text-caption); }
.dvp-toolbar { min-height: 28px; display: flex; justify-content: space-between; align-items: center; color: var(--text-secondary); border-bottom: 1px solid var(--border-subtle); }
.dvp-actions { display: flex; gap: var(--space-xs); }
button, input, select, textarea { border: 1px solid var(--border-default); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-caption); border-radius: var(--radius-sm); }
button { padding: 2px 8px; cursor: pointer; } button:disabled { opacity: 0.5; }
.dvp-table { min-width: 620px; }
.dvp-head, .dvp-row { display: grid; grid-template-columns: minmax(110px, 1fr) 72px minmax(220px, 2fr) 110px 72px; gap: var(--space-sm); align-items: center; min-height: 34px; padding: var(--space-xs) var(--space-sm); border-bottom: 1px solid var(--border-subtle); }
.dvp-head { color: var(--text-disabled); font-weight: 600; }
.dvp-row.changed { box-shadow: inset 2px 0 0 var(--accent); background: var(--bg-hover); }
.dvp-name { font-family: var(--font-mono); color: var(--text-primary); }
.dvp-type { color: var(--state-info); }
.dvp-editor input, .dvp-editor select, .dvp-editor textarea { width: 100%; padding: 3px 5px; resize: vertical; }
.dvp-editor small { display: block; color: var(--state-error); margin-top: 2px; }
.dvp-empty { color: var(--text-disabled); padding: var(--space-md); }
</style>
