<script setup lang="ts">
import { computed, ref } from 'vue'
import { useProjectDiagnosticsStore } from '@/stores/projectDiagnosticsStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import type { DiagnosticSeverity, Diagnostic } from '@/types/domains/diagnostics'
import { t } from '@/i18n'
import { locateGraphEdge, locateGraphNode } from '@/services/graphNodeNavigation'

const projectDiagnostics = useProjectDiagnosticsStore()

const severityFilter = ref<DiagnosticSeverity | 'all'>('all')
const stageFilter = ref<string>('all')
const searchQuery = ref('')
const sortBy = ref<'severity' | 'stage' | 'count'>('severity')
const expandedKeys = ref<Set<string>>(new Set())

const groups = computed(() => {
  const grouped = new Map<string, { stage: string; category: string; severity: string; message: string; count: number }>()
  for (const d of projectDiagnostics.visibleEntries) {
    const key = `${d.stage}|${d.category}|${d.severity}|${d.message}`
    const existing = grouped.get(key)
    if (existing) existing.count += d.count
    else grouped.set(key, { stage: d.stage, category: d.category, severity: d.severity, message: d.message, count: d.count })
  }
  let result = [...grouped.values()]
  if (severityFilter.value !== 'all') {
    result = result.filter(g => g.severity === severityFilter.value)
  }
  if (stageFilter.value !== 'all') {
    result = result.filter(g => g.stage === stageFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(g =>
      g.message.toLowerCase().includes(q) ||
      g.category.toLowerCase().includes(q) ||
      g.stage.toLowerCase().includes(q)
    )
  }
  // Sort
  const sevRank: Record<string, number> = { fatal: 0, error: 1, degraded: 2, warning: 3, info: 4 }
  if (sortBy.value === 'severity') {
    result = [...result].sort((a, b) => (sevRank[a.severity] ?? 5) - (sevRank[b.severity] ?? 5))
  } else if (sortBy.value === 'stage') {
    result = [...result].sort((a, b) => a.stage.localeCompare(b.stage))
  } else if (sortBy.value === 'count') {
    result = [...result].sort((a, b) => b.count - a.count)
  }
  return result
})

const hasAnyActivity = computed(() => projectDiagnostics.entries.length > 0)
const hasDiagnostics = computed(() => projectDiagnostics.visibleEntries.length > 0)

/** Look up individual Diagnostic entries matching a group */
function groupEntries(stage: string, category: string, severity: string, message: string): Diagnostic[] {
  return projectDiagnostics.visibleEntries.filter(
    entry => entry.stage === stage
      && entry.category === category
      && entry.severity === severity
      && entry.message === message,
  )
}

function groupKey(g: { stage: string; category: string; severity: string; message: string }): string {
  return `${g.stage}|${g.category}|${g.severity}|${g.message}`
}

function toggleExpand(g: { stage: string; category: string; severity: string; message: string }) {
  const key = groupKey(g)
  if (expandedKeys.value.has(key)) {
    expandedKeys.value.delete(key)
  } else {
    expandedKeys.value.add(key)
  }
}

function isExpanded(g: { stage: string; category: string; severity: string; message: string }): boolean {
  return expandedKeys.value.has(groupKey(g))
}

function severityClass(s: string) { return `sev-${s}` }

function severityLabel(s: string) {
  switch (s) {
    case 'fatal': return t('framework.diagnostics.severity.fatal', '致命')
    case 'error': return t('framework.diagnostics.severity.error', '错误')
    case 'degraded': return t('framework.diagnostics.severity.degraded', '降级')
    case 'warning': return t('framework.diagnostics.severity.warning', '警告')
    case 'info': return t('framework.diagnostics.severity.info', '信息')
    default: return s
  }
}

function extSummary(ext: Record<string, unknown> | null): string {
  if (!ext) return ''
  const parts: string[] = []
  for (const [k, v] of Object.entries(ext)) {
    if (k !== 'subject_ref' && k !== 'action' && typeof v === 'string') {
      parts.push(`${k}: ${v}`)
    }
  }
  return parts.join(', ')
}

// ---- Context menu ----
const ctxMenu = ref<{ x: number; y: number; text: string; entry?: Diagnostic; structured?: unknown } | null>(null)
function onCtxMenu(e: MouseEvent, text: string, entry?: Diagnostic, structured?: unknown) {
  e.preventDefault()
  ctxMenu.value = { x: e.clientX, y: e.clientY, text, entry, structured }
}
function closeCtxMenu() { ctxMenu.value = null }
async function copyToClipboard(text: string) {
  try { await navigator.clipboard.writeText(text) } catch {}
  closeCtxMenu()
}
function formatStructuredReadable(data: unknown): string {
  if (Array.isArray(data)) {
    return data.map((entry, i) => `--- ${t('framework.diagnostics.copy.entryHeader', `第 ${i + 1} 条`, { n: i + 1 })} ---\n${formatEntryStructured(entry)}`).join('\n\n')
  }
  return formatEntryStructured(data as Diagnostic)
}

function formatEntryStructured(entry: Diagnostic): string {
  const lines: string[] = []
  if (entry.diagnostic_id) lines.push(`${t('framework.diagnostics.copy.diagnosticId', '诊断 ID')}: ${entry.diagnostic_id}`)
  lines.push(`${t('framework.diagnostics.copy.severity', '严重度')}: ${severityLabel(entry.severity)} (${entry.severity})`)
  lines.push(`${t('framework.diagnostics.copy.stage', '阶段')}: ${entry.stage}`)
  lines.push(`${t('framework.diagnostics.copy.category', '分类')}: ${entry.category}`)
  lines.push(`${t('framework.diagnostics.copy.message', '信息')}: ${entry.message}`)
  if (entry.object_ref) lines.push(`${t('framework.diagnostics.copy.objectRef', '对象引用')}: ${entry.object_ref}`)
  if (entry.trace_ref) lines.push(`${t('framework.diagnostics.copy.traceRef', '追踪引用')}: ${entry.trace_ref}`)
  if (entry.stage_extension && Object.keys(entry.stage_extension).length) {
    lines.push(`${t('framework.diagnostics.copy.stageExtension', '扩展信息')}:`)
    for (const [k, v] of Object.entries(entry.stage_extension)) {
      lines.push(`  ${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    }
  }
  if (entry.degraded_extension && Object.keys(entry.degraded_extension).length) {
    lines.push(`${t('framework.diagnostics.copy.degradedExtension', '降级信息')}:`)
    for (const [k, v] of Object.entries(entry.degraded_extension)) {
      lines.push(`  ${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    }
  }
  return lines.join('\n')
}

async function copyStructured() {
  if (!ctxMenu.value?.structured) return
  const text = formatStructuredReadable(ctxMenu.value.structured)
  try { await navigator.clipboard.writeText(text) } catch {}
  closeCtxMenu()
}

function extractNodeId(entry: Diagnostic): string | null {
  // 1. object_ref: "node:<node_id>" or "n-<node_id>" or "node-<node_id>"
  const objRef = entry.object_ref
  if (objRef) {
    const m = objRef.match(/node:([^\s]+)/) || objRef.match(/\b(node-[a-z0-9]+)\b/i)
    if (m) return m[1]
  }
  // 2. stage_extension.graph_ref.node_id
  const ext = entry.stage_extension as Record<string, any> | undefined
  if (ext?.graph_ref?.node_id) return String(ext.graph_ref.node_id)
  // 3. message contains "node-xxx"
  const msgMatch = entry.message?.match(/\b(node-[a-z0-9]+)\b/i)
  if (msgMatch) return msgMatch[1]
  // 4. any stage_extension value that looks like "node-xxx"
  if (ext) {
    for (const v of Object.values(ext)) {
      if (typeof v === 'string') {
        const m = v.match(/\b(node-[a-z0-9]+)\b/i)
        if (m) return m[1]
      }
    }
  }
  return null
}

function diagnosticHasNodeRef(entry?: Diagnostic): boolean {
  if (!entry) return false
  return !!extractNodeId(entry)
}

function extractEdgeId(entry: Diagnostic): string | null {
  const extension = entry.stage_extension as Record<string, any> | undefined
  const graphEdgeId = extension?.graph_ref?.edge_id
  if (typeof graphEdgeId === 'string' && graphEdgeId.trim()) return graphEdgeId
  const objectRef = entry.object_ref
  if (!objectRef) return null
  const prefixed = objectRef.match(/^edge:([^\s]+)$/)
  if (prefixed) return prefixed[1]
  return /^edge-[A-Za-z0-9_-]+$/.test(objectRef) ? objectRef : null
}

function diagnosticHasEdgeRef(entry?: Diagnostic): boolean {
  return !!entry && !!extractEdgeId(entry)
}

function locateNodeFromDiagnostic(entry?: Diagnostic) {
  if (!entry) return
  const nodeId = extractNodeId(entry)
  if (!nodeId) return
  closeCtxMenu()
  void locateGraphNode(nodeId)
}
function locateEdgeFromDiagnostic(entry?: Diagnostic) {
  if (!entry) return
  const edgeId = extractEdgeId(entry)
  if (!edgeId) return
  closeCtxMenu()
  void locateGraphEdge(edgeId)
}
function formatDiagnosticForCopy(g: { stage: string; category: string; severity: string; message: string; count: number }): string {
  return `[${severityLabel(g.severity)}] ${g.stage}/${g.category}: ${g.message} (${t('framework.diagnostics.copy.count', `${g.count} 条`, { n: g.count })})`
}
function formatEntryForCopy(entry: Diagnostic): string {
  let text = `[${severityLabel(entry.severity)}] ${entry.stage}/${entry.category}: ${entry.message}`
  if (entry.diagnostic_id) text += `\n  ID: ${entry.diagnostic_id}`
  if (entry.object_ref) text += `\n  Ref: ${entry.object_ref}`
  if (entry.trace_ref) text += `\n  Trace: ${entry.trace_ref}`
  if (entry.stage_extension && Object.keys(entry.stage_extension).length) text += `\n  Ext: ${extSummary(entry.stage_extension)}`
  return text
}
</script>

<template>
  <div class="diag-tab">
    <PlaceholderBanner
      v-if="!hasAnyActivity"
      type="empty"
      :title="t('framework.diagnostics.empty.needActivity.title', '编译或运行后查看诊断信息')"
      :description="t('framework.diagnostics.empty.needActivity.description', '运行编译或执行任务以生成诊断结果')"
    />

    <PlaceholderBanner
      v-else-if="!hasDiagnostics"
      type="empty"
      :title="t('framework.diagnostics.empty.none.title', '无诊断信息')"
      :description="t('framework.diagnostics.empty.none.description', '编译与运行均未产生诊断条目')"
    />

    <template v-else>
      <div class="dt-toolbar">
        <select class="dt-select" v-model="severityFilter">
          <option value="all">{{ t('framework.diagnostics.filter.severity.all', '全部严重度') }}</option>
          <option value="fatal">{{ t('framework.diagnostics.severity.fatal', '致命') }}</option>
          <option value="error">{{ t('framework.diagnostics.severity.error', '错误') }}</option>
          <option value="degraded">{{ t('framework.diagnostics.severity.degraded', '降级') }}</option>
          <option value="warning">{{ t('framework.diagnostics.severity.warning', '警告') }}</option>
          <option value="info">{{ t('framework.diagnostics.severity.info', '信息') }}</option>
        </select>
        <select class="dt-select" v-model="stageFilter">
          <option value="all">{{ t('framework.diagnostics.filter.stage.all', '全部阶段') }}</option>
          <option value="parse">Parse</option>
          <option value="bind">Bind</option>
          <option value="validate">Validate</option>
          <option value="normalize">Normalize</option>
          <option value="lower">Lower</option>
          <option value="emit">Emit</option>
        </select>
        <select class="dt-select" v-model="sortBy">
          <option value="severity">{{ t('framework.diagnostics.sort.bySeverity', '按严重度') }}</option>
          <option value="stage">{{ t('framework.diagnostics.sort.byStage', '按阶段') }}</option>
          <option value="count">{{ t('framework.diagnostics.sort.byCount', '按数量') }}</option>
        </select>
        <input class="dt-search" type="text" v-model="searchQuery" :placeholder="t('framework.diagnostics.searchPlaceholder', '搜索诊断…')" />
      </div>

      <div class="dt-scroll">
        <table class="dt-table">
          <thead>
            <tr>
              <th class="col-exp"></th>
              <th class="col-sev">{{ t('framework.diagnostics.table.severity', '严重度') }}</th>
              <th class="col-stage">{{ t('framework.diagnostics.table.stage', '阶段') }}</th>
              <th class="col-cat">{{ t('framework.diagnostics.table.category', '分类') }}</th>
              <th class="col-msg">{{ t('framework.diagnostics.table.message', '信息') }}</th>
              <th class="col-count">{{ t('framework.diagnostics.table.count', '计数') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in groups" :key="groupKey(g)">
              <tr
                class="dt-group-row"
                :class="{ 'dt-expanded': isExpanded(g) }"
                @click="toggleExpand(g)"
                @contextmenu="onCtxMenu($event, formatDiagnosticForCopy(g), groupEntries(g.stage, g.category, g.severity, g.message)[0], groupEntries(g.stage, g.category, g.severity, g.message))"
              >
                <td class="col-exp">
                  <span class="exp-arrow">{{ isExpanded(g) ? '▾' : '▸' }}</span>
                </td>
                <td>
                  <span :class="['dt-sev', severityClass(g.severity)]">
                    {{ severityLabel(g.severity) }}
                  </span>
                </td>
                <td class="dt-stage">{{ g.stage }}</td>
                <td class="dt-cat">{{ g.category }}</td>
                <td class="dt-msg">{{ g.message }}</td>
                <td class="dt-count">{{ g.count }}</td>
              </tr>
              <tr v-if="isExpanded(g)" class="dt-detail-row">
                <td colspan="6">
                  <div class="dt-detail-box">
                    <div
                      v-for="entry in groupEntries(g.stage, g.category, g.severity, g.message)"
                      :key="entry.diagnostic_id"
                      class="dt-entry"
                      @contextmenu.stop="onCtxMenu($event, formatEntryForCopy(entry), entry, entry)"
                    >
                      <div class="dt-entry-header">
                        <code class="dt-entry-id">{{ entry.diagnostic_id }}</code>
                        <span v-if="entry.object_ref" class="dt-entry-ref">→ {{ entry.object_ref }}</span>
                      </div>
                      <div class="dt-entry-body">
                        <p class="dt-entry-msg">{{ entry.message }}</p>
                        <div v-if="entry.trace_ref" class="dt-entry-meta">
                          <span>Trace: {{ entry.trace_ref }}</span>
                        </div>
                        <div v-if="entry.stage_extension && Object.keys(entry.stage_extension).length" class="dt-entry-meta">
                          <span>{{ extSummary(entry.stage_extension) }}</span>
                        </div>
                        <div v-if="entry.degraded_extension" class="dt-entry-meta degraded">
                          <span>{{ t('framework.diagnostics.detail.degradedReason', '降级原因') }}: {{ extSummary(entry.degraded_extension) }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="dt-summary" v-if="groups.length > 0">
        {{ t('framework.diagnostics.summary', '{groups} 组诊断 ({total} 条)', { groups: groups.length, total: groups.reduce((s, g) => s + g.count, 0) }) }}
      </div>
    </template>

    <!-- Context menu -->
    <Teleport to="body">
      <div v-if="ctxMenu" class="dt-ctx-overlay" @click="closeCtxMenu" @contextmenu.prevent="closeCtxMenu">
        <div class="dt-ctx-box" :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }">
          <button class="dt-ctx-btn" @click="copyToClipboard(ctxMenu.text)">{{ t('framework.diagnostics.ctxMenu.copyContent', '📋 复制内容') }}</button>
          <button v-if="ctxMenu.structured" class="dt-ctx-btn" @click="copyStructured()">{{ t('framework.diagnostics.ctxMenu.copyStructured', '📋 复制结构化数据') }}</button>
          <button v-if="diagnosticHasNodeRef(ctxMenu.entry)" class="dt-ctx-btn" @click="locateNodeFromDiagnostic(ctxMenu.entry)">{{ t('framework.diagnostics.ctxMenu.locateNode', '📍 定位节点') }}</button>
          <button v-if="diagnosticHasEdgeRef(ctxMenu.entry)" class="dt-ctx-btn" @click="locateEdgeFromDiagnostic(ctxMenu.entry)">{{ t('framework.diagnostics.ctxMenu.locateEdge', '📍 定位边') }}</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.diag-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.loading-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-lg);
}
.skeleton-row {
  height: 24px;
  background: var(--bg-panel-header);
  border-radius: var(--radius-sm);
}

.dt-toolbar {
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-lg);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.dt-select, .dt-search {
  padding: 3px 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--text-small);
  height: 26px;
}
.dt-search { flex: 1; min-width: 120px; }

.dt-scroll { flex: 1; overflow-y: auto; }

.dt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body);
}
.dt-table th {
  text-align: left;
  padding: 5px 8px;
  background: var(--bg-panel-header);
  color: var(--text-disabled);
  font-weight: 600;
  font-size: var(--text-small);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 1;
}
.dt-table td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.col-exp { width: 24px; text-align: center; }
.col-sev { width: 56px; }
.col-stage { width: 64px; }
.col-cat { width: 100px; }
.col-count { width: 36px; text-align: right; }

.dt-group-row {
  cursor: pointer;
  transition: background 80ms;
}
.dt-group-row:hover { background: var(--bg-hover); }
.dt-group-row.dt-expanded { background: var(--bg-selected); }

.exp-arrow {
  font-size: 10px;
  color: var(--text-disabled);
}

.dt-stage { font-family: var(--font-mono); font-size: var(--text-small); color: var(--text-secondary); }
.dt-cat { font-family: var(--font-mono); font-size: var(--text-small); }
.dt-msg { font-size: var(--text-small); }
.dt-count { text-align: right; font-weight: 600; }

.dt-sev {
  display: inline-block;
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  font-size: var(--text-caption);
  font-weight: 600;
}
.sev-fatal    { background: rgba(176,80,66,0.12); color: var(--state-fatal); }
.sev-error    { background: rgba(208,112,96,0.12); color: var(--state-error); }
.sev-degraded { background: rgba(200,148,74,0.12); color: var(--state-degraded); }
.sev-warning  { background: rgba(232,152,104,0.12); color: var(--state-warning); }
.sev-info     { background: rgba(107,154,168,0.12); color: var(--state-info); }

.dt-detail-row td { padding: 0; border-bottom: 2px solid var(--border-subtle); }
.dt-detail-box { padding: var(--space-sm) var(--space-lg) var(--space-md); background: var(--bg-input); }

.dt-entry { margin-bottom: var(--space-sm); }
.dt-entry:last-child { margin-bottom: 0; }

.dt-entry-header {
  display: flex;
  gap: var(--space-sm);
  align-items: baseline;
  margin-bottom: 2px;
}
.dt-entry-id {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--text-disabled);
}
.dt-entry-ref {
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--state-info);
}
.dt-entry-body { padding-left: 4px; }
.dt-entry-msg { font-size: var(--text-small); color: var(--text-primary); margin: 0; }
.dt-entry-meta {
  font-size: var(--text-caption);
  color: var(--text-disabled);
  margin-top: 2px;
  font-family: var(--font-mono);
}
.dt-entry-meta.degraded { color: var(--state-degraded); }

.dt-summary {
  padding: var(--space-sm) var(--space-lg);
  font-size: var(--text-small);
  color: var(--text-disabled);
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

/* Context menu */
.dt-ctx-overlay { position: fixed; inset: 0; z-index: 1000; }
.dt-ctx-box { position: fixed; background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-menu); min-width: 160px; padding: var(--space-xs); }
.dt-ctx-btn { display: block; width: 100%; padding: 4px 10px; border: none; background: transparent; color: var(--text-primary); cursor: pointer; font-family: var(--font-ui); font-size: var(--text-small); text-align: left; border-radius: var(--radius-sm); }
.dt-ctx-btn:hover { background: var(--bg-hover); }
</style>
