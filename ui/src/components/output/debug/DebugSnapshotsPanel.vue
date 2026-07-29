<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDebugStore } from '@/stores/debugStore'
import DebugValueTree from './DebugValueTree.vue'
import { t } from '@/i18n'
import { locateGraphNode } from '@/services/graphNodeNavigation'

type DetailTab = 'overview' | 'variables' | 'io' | 'runtime' | 'trace'

const tabs = computed<Array<{ id: DetailTab; label: string }>>(() => [
  { id: 'overview', label: t('framework.debug.snapshots.tab.overview', '概要') },
  { id: 'variables', label: t('framework.debug.snapshots.tab.variables', '变量') },
  { id: 'io', label: t('framework.debug.snapshots.tab.io', '输入/输出') },
  { id: 'runtime', label: t('framework.debug.snapshots.tab.runtime', '运行状态') },
  { id: 'trace', label: t('framework.debug.snapshots.tab.trace', '追踪') },
])

const debugStore = useDebugStore()
const selectedId = ref<string | null>(null)
const detailTab = ref<DetailTab>('overview')
const showAll = ref(false)
const rawExpanded = ref(false)

const sessionSource = computed<any>(() => (
  (debugStore.activeHistorySession?.session as any) || debugStore.activeSession || null
))
const snapshots = computed<any[]>(() => {
  const source = sessionSource.value
  const snapshotRecords = source?.snapshots || source?.debug_snapshots
  const keyframes = source?.keyframes || source?.debug_keyframes
  const records = showAll.value && Array.isArray(keyframes) ? keyframes : snapshotRecords
  if (!Array.isArray(records)) return []
  return showAll.value
    ? records
    : records.filter(item => ['breakpoint.hit', 'debug.paused', 'record_frame.hit'].includes(item.event_kind))
})
const itemIdentity = (item: any) => item.snapshot_id || item.keyframe_id || item.event_id
const selected = computed(() => (
  snapshots.value.find(item => itemIdentity(item) === selectedId.value) || snapshots.value[0] || null
))
const variableEntries = computed(() => Object.entries(selected.value?.variable_snapshot || {}))
const rawJson = computed(() => (
  rawExpanded.value && selected.value ? JSON.stringify(selected.value, null, 2) : ''
))

watch([selectedId, detailTab], () => { rawExpanded.value = false })

async function selectSnapshot(snapshot: any) {
  selectedId.value = itemIdentity(snapshot)
  const sessionId = snapshot.session_id || debugStore.activeSession?.debug_session?.session_id
  if (sessionId && typeof snapshot.event_index === 'number') {
    await debugStore.loadProjection(sessionId, 'history', snapshot.event_index)
  }
  if (snapshot.node_id) void locateGraphNode(snapshot.node_id)
}

function snapshotLabel(snapshot: any) {
  if (snapshot.event_kind === 'breakpoint.hit') return t('framework.debug.snapshots.kind.breakpoint', '断点')
  if (snapshot.event_kind === 'debug.paused') return snapshot.reason === 'manual_pause' ? t('framework.debug.snapshots.kind.manualPause', '手动暂停') : t('framework.debug.snapshots.kind.paused', '暂停')
  if (snapshot.event_kind === 'record_frame.hit') return t('framework.debug.snapshots.kind.recordPoint', '记录点')
  return t('framework.debug.snapshots.kind.keyframe', '关键帧')
}

function outputStateLabel(state: unknown) {
  if (state === 'captured') return t('framework.debug.snapshots.outputState.captured', '已捕获')
  if (state === 'not_executed') return t('framework.debug.snapshots.outputState.notExecuted', '尚未执行')
  return t('framework.debug.snapshots.outputState.unavailable', '不可用')
}

function formatTime(value: unknown) {
  if (typeof value !== 'string') return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function descriptorType(name: string, value: unknown) {
  const descriptor = selected.value?.variable_descriptors?.[name]
  if (typeof descriptor?.value_type === 'string') return descriptor.value_type
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
}
</script>

<template>
  <div class="dsp-root">
    <aside class="dsp-list">
      <label class="dsp-filter"><input v-model="showAll" type="checkbox"> {{ t('framework.debug.snapshots.showAllKeyframes', '显示全部关键帧') }}</label>
      <button
        v-for="snapshot in snapshots"
        :key="itemIdentity(snapshot)"
        class="dsp-list-item"
        :class="{ active: itemIdentity(selected) === itemIdentity(snapshot) }"
        @click="selectSnapshot(snapshot)"
      >
        <span class="dsp-list-heading">
          <strong>{{ snapshotLabel(snapshot) }}</strong>
          <span>#{{ snapshot.event_index }}</span>
          <small :data-state="snapshot.output_state">{{ outputStateLabel(snapshot.output_state) }}</small>
        </span>
        <span class="dsp-node">{{ snapshot.node_id || t('framework.debug.snapshots.noNode', '无节点') }}</span>
        <time>{{ formatTime(snapshot.recorded_at) }}</time>
      </button>
      <div v-if="!snapshots.length" class="dsp-empty">{{ t('framework.debug.snapshots.emptyList', '暂无快照') }}</div>
    </aside>

    <section v-if="selected" class="dsp-detail">
      <nav class="dsp-nav" :aria-label="t('framework.debug.snapshots.detailNavLabel', '快照详情')">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :data-tab="tab.id"
          :class="{ active: detailTab === tab.id }"
          @click="detailTab = tab.id"
        >{{ tab.label }}</button>
      </nav>

      <div v-if="detailTab === 'overview'" class="dsp-section">
        <header class="dsp-title">
          <div><strong>{{ snapshotLabel(selected) }}</strong><span>#{{ selected.event_index }}</span></div>
          <span class="dsp-state">{{ outputStateLabel(selected.output_state) }}</span>
        </header>
        <dl class="dsp-grid">
          <div><dt>{{ t('framework.debug.snapshots.field.node', '节点') }}</dt><dd>{{ selected.node_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.nodeKind', '节点类型') }}</dt><dd>{{ selected.node_kind || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.pauseReason', '暂停原因') }}</dt><dd>{{ selected.reason || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.pauseTiming', '暂停时机') }}</dt><dd>{{ selected.pause_timing || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.graphModel', '图模型') }}</dt><dd>{{ selected.graph_model_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.graphRevision', '图版本') }}</dt><dd>{{ selected.graph_revision ?? '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.compilationId', '编译 ID') }}</dt><dd>{{ selected.compilation_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.recordedTime', '记录时间') }}</dt><dd>{{ formatTime(selected.recorded_at) }}</dd></div>
        </dl>
      </div>

      <div v-else-if="detailTab === 'variables'" class="dsp-section">
        <div v-if="variableEntries.length" class="dsp-variable-list">
          <section v-for="([name, value]) in variableEntries" :key="name" class="dsp-variable">
            <header><strong>{{ name }}</strong><span>{{ descriptorType(name, value) }}</span></header>
            <DebugValueTree :value="value" expanded />
          </section>
        </div>
        <div v-else class="dsp-empty">{{ t('framework.debug.snapshots.noVariables', '当前快照没有变量') }}</div>
      </div>

      <div v-else-if="detailTab === 'io'" class="dsp-section dsp-io">
        <section>
          <header><strong>{{ t('framework.debug.snapshots.nodeInput', '节点输入') }}</strong></header>
          <DebugValueTree label="input" :value="selected.node_input_snapshot" expanded />
        </section>
        <section>
          <header><strong>{{ t('framework.debug.snapshots.nodeOutput', '节点输出') }}</strong><span>{{ outputStateLabel(selected.output_state) }}</span></header>
          <DebugValueTree label="output" :value="selected.node_output_snapshot" expanded />
        </section>
      </div>

      <div v-else-if="detailTab === 'runtime'" class="dsp-section">
        <dl class="dsp-grid">
          <div><dt>{{ t('framework.debug.snapshots.field.currentNode', '当前节点') }}</dt><dd>{{ selected.runtime_preview_summary?.current_node_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.queuedNodes', '排队节点') }}</dt><dd>{{ selected.runtime_preview_summary?.queued_node_count ?? 0 }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.executedNodes', '已执行节点') }}</dt><dd>{{ selected.runtime_preview_summary?.executed_node_count ?? 0 }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.schedulerMode', '调度模式') }}</dt><dd>{{ selected.runtime_preview_summary?.scheduler_mode || '-' }}</dd></div>
        </dl>
        <div class="dsp-subsection"><strong>{{ t('framework.debug.snapshots.runtimeProjection', '运行投影') }}</strong><DebugValueTree :value="selected.runtime_preview || {}" /></div>
      </div>

      <div v-else class="dsp-section">
        <section class="dsp-trace-block">
          <strong>{{ t('framework.debug.snapshots.instancePath', '实例路径') }}</strong>
          <ol><li v-for="(item, index) in selected.instance_path || []" :key="`${item}-${index}`">{{ item }}</li></ol>
        </section>
        <section class="dsp-trace-block">
          <strong>{{ t('framework.debug.snapshots.iterationStack', '迭代栈') }}</strong>
          <DebugValueTree :value="selected.iteration_stack || []" />
        </section>
        <dl class="dsp-grid dsp-identifiers">
          <div><dt>{{ t('framework.debug.snapshots.field.frameIdentity', '帧标识') }}</dt><dd>{{ selected.frame_identity || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.eventId', '事件 ID') }}</dt><dd>{{ selected.event_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.snapshots.field.keyframeId', '关键帧 ID') }}</dt><dd>{{ selected.keyframe_id || '-' }}</dd></div>
        </dl>
        <button data-testid="snapshot-raw-toggle" class="dsp-raw-toggle" @click="rawExpanded = !rawExpanded">{{ t('framework.debug.snapshots.rawData', '原始数据') }}</button>
        <pre v-if="rawExpanded" data-testid="snapshot-raw-json" class="dsp-raw-json">{{ rawJson }}</pre>
      </div>
    </section>
    <div v-else class="dsp-empty dsp-detail-empty">{{ t('framework.debug.snapshots.selectPrompt', '选择快照后查看详情') }}</div>
  </div>
</template>

<style scoped>
.dsp-root { display: grid; grid-template-columns: minmax(220px, 30%) minmax(0, 1fr); height: 100%; min-width: 520px; color: var(--text-primary); }
.dsp-list { overflow: auto; border-right: 1px solid var(--border-subtle); padding: var(--space-xs); }
.dsp-filter { min-height: 28px; display: flex; align-items: center; gap: var(--space-xs); padding: 0 var(--space-xs); color: var(--text-secondary); font-family: var(--font-ui); font-size: var(--text-caption); }
.dsp-list-item { width: 100%; min-height: 64px; display: flex; flex-direction: column; align-items: stretch; gap: 4px; padding: var(--space-sm); border: 0; border-bottom: 1px solid var(--border-subtle); background: transparent; color: inherit; cursor: pointer; text-align: left; }
.dsp-list-item:hover { background: var(--bg-hover); }
.dsp-list-item.active { background: var(--bg-hover); box-shadow: inset 2px 0 0 var(--accent); }
.dsp-list-heading { display: flex; align-items: center; gap: var(--space-xs); font-family: var(--font-ui); font-size: var(--text-caption); }
.dsp-list-heading span { color: var(--text-disabled); font-family: var(--font-mono); }
.dsp-list-heading small { margin-left: auto; color: var(--text-secondary); }
.dsp-node, .dsp-list time { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); font-size: var(--text-caption); }
.dsp-list time { color: var(--text-disabled); }
.dsp-detail { min-width: 0; overflow: auto; }
.dsp-nav { position: sticky; top: 0; z-index: 1; display: flex; gap: 2px; padding: 0 var(--space-sm); border-bottom: 1px solid var(--border-subtle); background: var(--bg-primary); }
.dsp-nav button { min-height: 34px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--text-secondary); padding: 0 var(--space-sm); cursor: pointer; font-family: var(--font-ui); font-size: var(--text-caption); white-space: nowrap; }
.dsp-nav button:hover { color: var(--text-primary); }
.dsp-nav button.active { color: var(--accent); border-bottom-color: var(--accent); }
.dsp-section { padding: var(--space-md); }
.dsp-title { display: flex; align-items: center; justify-content: space-between; gap: var(--space-md); padding-bottom: var(--space-sm); border-bottom: 1px solid var(--border-subtle); }
.dsp-title div { display: flex; align-items: baseline; gap: var(--space-xs); }
.dsp-title span, .dsp-state { color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-caption); }
.dsp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
.dsp-grid > div { min-width: 0; display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: var(--space-sm); padding: var(--space-sm) 0; border-bottom: 1px solid var(--border-subtle); }
.dsp-grid > div:nth-child(odd) { padding-right: var(--space-md); }
.dsp-grid dt { color: var(--text-disabled); font-family: var(--font-ui); font-size: var(--text-caption); }
.dsp-grid dd { min-width: 0; margin: 0; overflow-wrap: anywhere; font-family: var(--font-mono); font-size: var(--text-caption); }
.dsp-variable-list { display: grid; gap: var(--space-sm); }
.dsp-variable { padding-bottom: var(--space-sm); border-bottom: 1px solid var(--border-subtle); }
.dsp-variable > header, .dsp-io header { min-height: 28px; display: flex; align-items: center; gap: var(--space-sm); }
.dsp-variable > header span, .dsp-io header span { color: var(--text-disabled); font-family: var(--font-mono); font-size: 10px; }
.dsp-io { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-lg); }
.dsp-io > section + section { padding-left: var(--space-lg); border-left: 1px solid var(--border-subtle); }
.dsp-subsection, .dsp-trace-block { padding: var(--space-md) 0; border-bottom: 1px solid var(--border-subtle); }
.dsp-trace-block ol { margin: var(--space-sm) 0 0; padding-left: var(--space-lg); font-family: var(--font-mono); font-size: var(--text-caption); }
.dsp-identifiers { margin-top: var(--space-sm); }
.dsp-raw-toggle { display: block; margin: var(--space-xl) 0 0 auto; border: 0; background: transparent; color: var(--text-disabled); opacity: .45; padding: 2px 0; cursor: pointer; font-family: var(--font-ui); font-size: 10px; }
.dsp-raw-toggle:hover { opacity: .8; }
.dsp-raw-json { max-height: 360px; overflow: auto; margin-top: var(--space-xs); padding: var(--space-sm); border: 1px solid var(--border-subtle); background: var(--bg-secondary); white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--font-mono); font-size: var(--text-caption); }
.dsp-empty { padding: var(--space-md); color: var(--text-disabled); font-family: var(--font-ui); font-size: var(--text-caption); }
.dsp-detail-empty { align-self: center; justify-self: center; }
@media (max-width: 760px) {
  .dsp-root { grid-template-columns: minmax(180px, 38%) minmax(0, 1fr); }
  .dsp-grid, .dsp-io { grid-template-columns: minmax(0, 1fr); }
  .dsp-grid > div:nth-child(odd) { padding-right: 0; }
  .dsp-io > section + section { padding: var(--space-md) 0 0; border-left: 0; border-top: 1px solid var(--border-subtle); }
}
</style>
