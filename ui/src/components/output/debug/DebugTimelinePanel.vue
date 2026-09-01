<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDebugStore } from '@/stores/debugStore'
import { useDockStore } from '@/stores/dockStore'
import { t } from '@/i18n'

const debugStore = useDebugStore()
const dock = useDockStore()
const emit = defineEmits<{
  (event: 'select-event', eventIndex: number): void
}>()
const events = computed(() => debugStore.events)
const total = computed(() => debugStore.eventsTotal)
const activeNetworkSummary = computed(() => {
  const activeSummary = debugStore.activeSession?.network_trace_snapshot?.summary
  const historySummary = (debugStore.activeHistorySession?.session as any)?.network_trace_snapshot?.summary
  if (debugStore.projection?.mode === 'history') return historySummary ?? activeSummary ?? null
  return activeSummary ?? historySummary ?? null
})
const selectedEventIndex = ref<number | null>(null)
const projectionLoading = ref(false)

function eventKey(event: Record<string, unknown>, index: number): string {
  if (typeof event.event_id === 'string' && event.event_id) return event.event_id
  if (typeof event.event_index === 'number') return `event-${event.event_index}`
  return `event-${index}`
}

async function selectEvent(eventIndex: unknown) {
  if (typeof eventIndex !== 'number' || !debugStore.eventsSessionId) return
  projectionLoading.value = true
  try {
    await debugStore.loadProjection(debugStore.eventsSessionId, 'history', eventIndex)
    selectedEventIndex.value = eventIndex
    emit('select-event', eventIndex)
  } finally {
    projectionLoading.value = false
  }
}

async function exitHistory() {
  const activeSessionId = debugStore.activeSession?.debug_session?.session_id
  if (debugStore.isDebugActive && activeSessionId) {
    await debugStore.loadProjection(activeSessionId, 'live')
  } else {
    debugStore.clearProjection()
  }
  selectedEventIndex.value = null
}

function openNetworkDebug() {
  dock.restorePanel('debugNetwork')
  dock.activatePanel('debugNetwork')
}
</script>

<template>
  <div class="dtp-root">
    <div class="dtp-toolbar">
      <span class="dtp-summary">{{ t('framework.debug.timeline.eventCount', `共 ${total} 条事件`, { n: total }) }}</span>
      <span class="dtp-actions">
        <button data-action="open-network-debug" class="dtp-network"
          @click="openNetworkDebug">{{ t('framework.debug.timeline.openNetworkDebug', '打开网络调试') }}</button>
        <button v-if="selectedEventIndex !== null" data-action="exit-history" class="dtp-exit"
          :disabled="projectionLoading" @click="exitHistory">{{ t('framework.debug.timeline.exitHistory', '退出历史查看') }}</button>
      </span>
    </div>
    <div v-if="activeNetworkSummary" class="dtp-network-overview">
      <span>{{ t('framework.debug.timeline.networkOverview', '网络概览') }}</span>
      <strong>{{ t('framework.debug.timeline.networkOperations', `操作 ${activeNetworkSummary.total_operations} 条`, { n: activeNetworkSummary.total_operations }) }}</strong>
      <strong>{{ t('framework.debug.timeline.networkConnections', `连接 ${activeNetworkSummary.active_connections} 条`, { n: activeNetworkSummary.active_connections }) }}</strong>
      <span>{{ t('framework.debug.timeline.networkSuccesses', `成功 ${activeNetworkSummary.successful_operations} 条`, { n: activeNetworkSummary.successful_operations }) }}</span>
      <span>{{ t('framework.debug.timeline.networkFailures', `失败 ${activeNetworkSummary.failed_operations} 条`, { n: activeNetworkSummary.failed_operations }) }}</span>
      <span>{{ t('framework.debug.timeline.networkCancelled', `取消 ${activeNetworkSummary.cancelled_operations} 条`, { n: activeNetworkSummary.cancelled_operations }) }}</span>
      <span>{{ t('framework.debug.timeline.networkQueueDepth', `队列 ${activeNetworkSummary.queue_depth} 条`, { n: activeNetworkSummary.queue_depth }) }}</span>
      <span>{{ t('framework.debug.timeline.networkReconnects', `重连 ${activeNetworkSummary.reconnect_count} 次`, { n: activeNetworkSummary.reconnect_count }) }}</span>
      <span>{{ t('framework.debug.timeline.networkDropped', `丢弃 ${activeNetworkSummary.dropped_count} 条`, { n: activeNetworkSummary.dropped_count }) }}</span>
      <span v-if="activeNetworkSummary.recent_errors?.length">
        {{ t('framework.debug.timeline.networkRecentError', `最近错误 ${activeNetworkSummary.recent_errors[activeNetworkSummary.recent_errors.length - 1]?.error_code || '未知'}`, { error: activeNetworkSummary.recent_errors[activeNetworkSummary.recent_errors.length - 1]?.error_code || '未知' }) }}
      </span>
    </div>
    <template v-if="events.length">
      <div v-for="(ev, index) in events" :key="eventKey(ev, index)"
        :data-event-id="ev.event_id || ''"
        :data-keyframe-id="ev.keyframe_id || ''"
        :class="['dtp-ev', `dtp-ev-${ev.event_kind.replace('.','-')}`, { 'dtp-selected': selectedEventIndex === ev.event_index }]"
        @click="selectEvent(ev.event_index)">
        <span class="dtp-kind">{{ ev.event_kind }}</span>
        <span v-if="ev.reason" class="dtp-reason">{{ ev.reason }}</span>
        <div class="dtp-meta">
          <span v-if="ev.event_index != null">#{{ ev.event_index }}</span>
          <span v-if="ev.keyframe_id" class="dtp-keyframe">{{ t('framework.debug.timeline.keyframe', '关键帧') }}</span>
          <span v-if="ev.node_id">{{ t('framework.debug.timeline.node', '节点') }}: {{ ev.node_id }}</span>
          <span v-if="ev.session_id">{{ t('framework.debug.timeline.session', '会话') }}: {{ ev.session_id }}</span>
          <span v-if="ev.recorded_at">{{ t('framework.debug.timeline.time', '时间') }}: {{ ev.recorded_at }}</span>
          <span v-if="ev.frame_identity">{{ t('framework.debug.timeline.frame', '帧') }}: {{ ev.frame_identity.slice(0, 12) }}</span>
          <span v-if="ev.pause_timing">{{ t('framework.debug.timeline.timing', '时机') }}: {{ ev.pause_timing }}</span>
          <span v-if="ev.breakpoint_hit_ordinal_in_session != null">#{{ ev.breakpoint_hit_ordinal_in_session }}</span>
        </div>
        <div v-if="ev.instance_path?.length" class="dtp-stack">
          {{ t('framework.debug.timeline.instancePath', '实例路径') }}: {{ ev.instance_path.join(' → ') }}
        </div>
        <div v-if="ev.iteration_stack?.length" class="dtp-stack">
          {{ t('framework.debug.timeline.iterationStack', '迭代栈') }}: {{ ev.iteration_stack.join(' → ') }}
        </div>
      </div>
    </template>
    <div v-else class="dtp-empty">{{ t('framework.debug.timeline.empty', '无事件记录') }}</div>
  </div>
</template>

<style scoped>
.dtp-root { padding: var(--space-md); overflow-y: auto; height: 100%; }
.dtp-empty { font-size: var(--text-caption); color: var(--text-disabled); }
.dtp-toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); margin-bottom: var(--space-sm); }
.dtp-actions { display: flex; gap: var(--space-xs); align-items: center; }
.dtp-summary { font-size: var(--text-small); color: var(--text-disabled); }
.dtp-network, .dtp-exit { border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; padding: 2px 8px; border-radius: var(--radius-sm); font-size: var(--text-caption); font-family: var(--font-ui); }
.dtp-network:hover:not(:disabled), .dtp-exit:hover:not(:disabled) { background: var(--bg-hover); }
.dtp-network-overview { display: flex; flex-wrap: wrap; gap: var(--space-sm); align-items: center; padding: 0 0 var(--space-sm); margin-bottom: var(--space-sm); border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); font-size: var(--text-caption); }
.dtp-ev { padding: 4px 8px; border-bottom: 1px solid var(--border-subtle); font-size: var(--text-caption); cursor: pointer; }
.dtp-ev:hover { background: var(--bg-hover); }
.dtp-selected { background: var(--bg-hover); box-shadow: inset 2px 0 0 var(--accent); }
.dtp-kind { font-weight: 600; color: var(--state-info); }
.dtp-keyframe { color: var(--state-success); font-weight: 600; }
.dtp-reason { color: var(--state-warning); font-style: italic; margin-left: 8px; }
.dtp-meta { display: flex; gap: var(--space-md); margin-top: 2px; color: var(--text-disabled); font-family: var(--font-mono); font-size: var(--text-caption); }
.dtp-stack { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); margin-top: 2px; }
</style>
