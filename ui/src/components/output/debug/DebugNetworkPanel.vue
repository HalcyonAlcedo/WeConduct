<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDebugStore } from '@/stores/debugStore'
import { useDockStore } from '@/stores/dockStore'
import {
  fetchDebugSessionNetwork,
  fetchDebugHistorySessionNetwork,
  fetchDebugHistorySessionNetworkSummary,
  fetchDebugHistorySessionNetworkTrace,
  fetchDebugHistorySessionNetworkTraceBody,
  fetchDebugSessionNetworkSummary,
  fetchDebugSessionNetworkTrace,
  fetchDebugSessionNetworkTraceBody,
} from '@/services/api'
import type {
  DebugNetworkBodyPayload,
  DebugNetworkSummary,
  DebugNetworkTraceRecord,
  DebugNetworkTraceBodyResponse,
} from '@/types/domains/api'
import { t } from '@/i18n'
import { locateGraphNode } from '@/services/graphNodeNavigation'

const debugStore = useDebugStore()
const dock = useDockStore()
const summary = ref<DebugNetworkSummary | null>(null)
type DebugNetworkTraceRow = DebugNetworkTraceRecord & {
  _record_kind?: 'operation' | 'connection' | 'message'
  connection_id?: string | null
  sequence_id?: number
  connection_epoch?: number | null
  recorded_at?: string
  protocol?: string | null
  connection_state?: string | null
  event_kind?: string | null
  method?: string
  url?: string
}

const traces = ref<DebugNetworkTraceRow[]>([])
const selected = ref<DebugNetworkTraceRecord | null>(null)
const selectedRow = ref<DebugNetworkTraceRow | null>(null)
const selectedRowKey = ref('')
const body = ref<DebugNetworkTraceBodyResponse | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const statusFilter = ref('')
const protocolFilter = ref('')
const query = ref('')
const nodeFilter = ref('')
const operationFilter = ref('')
const connectionFilter = ref('')
const sessionFilter = ref('')
const epochFilter = ref('')
const sequenceFilter = ref('')
const eventKindFilter = ref('')
const fromTime = ref('')
const toTime = ref('')
const onlyErrors = ref(false)
const onlyActiveConnections = ref(false)
const onlyExecutionActivations = ref(false)
const requestBodyExpanded = ref(false)
const responseBodyExpanded = ref(false)
const messagesExpanded = ref(false)

function liveMessageSignature(message: any): unknown {
  const payload = message?.payload
  let payloadSignature: unknown = payload
  if (payload && typeof payload === 'object') {
    try {
      const serialized = JSON.stringify(payload)
      payloadSignature = serialized.length <= 1024
        ? serialized
        : `object:${serialized.length}:${serialized.slice(0, 128)}`
    } catch {
      payloadSignature = Object.prototype.toString.call(payload)
    }
  } else if (typeof payload === 'string' && payload.length > 1024) {
    payloadSignature = `string:${payload.length}:${payload.slice(0, 128)}`
  }
  return [
    message?.event_kind,
    message?.connection_id,
    message?.sequence_id,
    message?.connection_epoch,
    message?.recorded_at,
    message?.debug_event_index,
    message?.size_bytes,
    payloadSignature,
  ]
}

const sourceMode = computed<'live' | 'history'>(() => (
  debugStore.projection?.mode === 'history'
    ? 'history'
    : 'live'
))
const sessionId = computed(() => (
  sourceMode.value === 'history'
    ? debugStore.activeHistorySession?.session_id
      || debugStore.activeSession?.debug_session?.session_id
      || null
    : debugStore.activeSession?.debug_session?.session_id || null
))
const liveSnapshot = computed(() => (
  sourceMode.value === 'live' ? debugStore.activeSession?.network_trace_snapshot ?? null : null
))
const liveSnapshotSignature = computed(() => {
  const snapshot = liveSnapshot.value
  if (!snapshot) return ''
  const summary = snapshot.summary || {}
  const traceMetadata = Object.entries(snapshot.traces || {}).map(([traceId, rawTrace]) => {
    const trace = rawTrace as any
    const operation = trace?.operation || {}
    const connections = Array.isArray(trace?.connections)
      ? trace.connections.map((connection: any) => [
        connection?.connection_id,
        connection?.connection_epoch,
        connection?.connection_state,
        connection?.message_count,
        connection?.queue_depth,
        connection?.dropped_count,
        connection?.reconnect_count,
        connection?.last_event_id,
      ])
      : []
    const messages = Array.isArray(trace?.messages) ? trace.messages : []
    return [
      traceId,
      trace?.status,
      trace?.error_code,
      operation?.status,
      operation?.ended_at,
      operation?.duration_ms,
      connections,
      messages.map(liveMessageSignature),
    ]
  })
  return JSON.stringify({
    traceOrder: snapshot.trace_order,
    summary: [
      summary.total_operations,
      summary.successful_operations,
      summary.failed_operations,
      summary.cancelled_operations,
      summary.active_connections,
      summary.queue_depth,
      summary.reconnect_count,
      summary.dropped_count,
      summary.queue_events || [],
      summary.recent_errors || [],
    ],
    traceMetadata,
  })
})
const sourceKey = computed(() => {
  if (sourceMode.value === 'history') return `history:${sessionId.value || ''}`
  return `live:${sessionId.value || ''}:${liveSnapshotSignature.value}`
})
const sourceScopeKey = computed(() => `${sourceMode.value}:${sessionId.value || ''}`)
const filteredTraces = computed<DebugNetworkTraceRow[]>(() => traces.value.filter((trace) => {
  const operation = (trace.operation || trace) as unknown as DebugNetworkTraceRow
  const status = operation.status || trace.status || ''
  const protocol = trace.protocol || (operation as DebugNetworkTraceRow).protocol || ''
  const needle = query.value.trim().toLowerCase()
  const recordKind = trace._record_kind || (trace.event_kind ? 'message' : trace.connection_id ? 'connection' : 'operation')
  const epoch = trace.connection_epoch
  const sequence = trace.sequence_id
  const recordTime = trace.recorded_at || trace.started_at || trace.ended_at
  const isError = status === 'failed' || status === 'cancelled' || Boolean(trace.error_code)
    || trace.connection_state === 'failed'
  const isActiveConnection = recordKind === 'connection'
    && !['closed', 'failed', 'disconnected'].includes(String(trace.connection_state || '').toLowerCase())
  const isExecutionActivation = typeof trace.event_kind === 'string'
    && trace.event_kind.toLowerCase().includes('activation')
  if (statusFilter.value && status !== statusFilter.value && trace.connection_state !== statusFilter.value) return false
  if (protocolFilter.value && protocol !== protocolFilter.value) return false
  if (nodeFilter.value.trim() && trace.node_id !== nodeFilter.value.trim()) return false
  if (operationFilter.value.trim() && trace.operation_id !== operationFilter.value.trim()) return false
  if (connectionFilter.value.trim() && trace.connection_id !== connectionFilter.value.trim()) return false
  if (sessionFilter.value.trim() && String(trace.debug_session_id || trace.operation?.debug_session_id || '').trim() !== sessionFilter.value.trim()) return false
  if (epochFilter.value.trim() && String(epoch ?? '') !== epochFilter.value.trim()) return false
  if (sequenceFilter.value.trim() && String(sequence ?? '') !== sequenceFilter.value.trim()) return false
  if (eventKindFilter.value.trim() && trace.event_kind !== eventKindFilter.value.trim()) return false
  if (onlyErrors.value && !isError) return false
  if (onlyActiveConnections.value && !isActiveConnection) return false
  if (onlyExecutionActivations.value && !isExecutionActivation) return false
  if (fromTime.value && (!recordTime || new Date(recordTime).getTime() < new Date(fromTime.value).getTime())) return false
  if (toTime.value && (!recordTime || new Date(recordTime).getTime() > new Date(toTime.value).getTime())) return false
  if (needle && ![trace.trace_id, trace.node_id, trace.operation_id, operation.url, operation.method]
    .concat(String(trace.debug_session_id || trace.operation?.debug_session_id || ''))
    .some(value => String(value || '').toLowerCase().includes(needle))) return false
  return true
}))

function normalizeTrace(item: any): DebugNetworkTraceRecord {
  if (item.operation) return { ...item, _record_kind: 'operation' } as DebugNetworkTraceRecord
  const isOperation = item.method !== undefined
  const operation = isOperation ? {
    ...item,
    trace_id: String(item.trace_id || ''),
    debug_session_id: String(item.debug_session_id || sessionId.value || ''),
    runtime_session_id: String(item.runtime_session_id || ''),
    node_id: item.node_id ?? null,
    operation_id: item.operation_id ?? null,
    started_at: String(item.started_at || ''),
    ended_at: item.ended_at ?? null,
    duration_ms: item.duration_ms ?? null,
    status: String(item.status || ''),
    error_code: item.error_code ?? null,
    method: String(item.method || ''),
    url: String(item.url || ''),
    request_headers: item.request_headers || {},
    request_query: item.request_query || {},
    request_body: item.request_body || null,
    response_status: item.response_status ?? null,
    response_headers: item.response_headers ?? null,
    response_body: item.response_body || null,
    retry_attempt: Number(item.retry_attempt || 0),
    final_url: item.final_url ?? null,
    redirects: Array.isArray(item.redirects) ? item.redirects : [],
    proxy: item.proxy ?? null,
    tls: item.tls ?? null,
  } : undefined
  return {
    ...item,
    trace_id: String(item.trace_id || ''),
    debug_session_id: String(item.debug_session_id || sessionId.value || ''),
    runtime_session_id: String(item.runtime_session_id || ''),
    node_id: item.node_id ?? null,
    operation_id: item.operation_id ?? null,
    started_at: String(item.started_at || ''),
    ended_at: item.ended_at ?? null,
    duration_ms: item.duration_ms ?? null,
    status: String(item.status || item.connection_state || ''),
    error_code: item.error_code ?? null,
    debug_event_index: item.debug_event_index ?? null,
    operation,
    connections: item.connections || [],
    messages: item.messages || [],
    _record_kind: item._record_kind || (isOperation ? 'operation' : item.event_kind ? 'message' : 'connection'),
  } as DebugNetworkTraceRecord
}

function flattenTraceItems(items: any[]): DebugNetworkTraceRow[] {
  const flattened: DebugNetworkTraceRow[] = []
  for (const item of items) {
    if (!item || typeof item !== 'object') continue
    const traceId = item.trace_id
    const baseNodeId = item.node_id
    const baseOperationId = item.operation_id
    flattened.push(normalizeTrace(item))
    for (const connection of Array.isArray(item.connections) ? item.connections : []) {
      flattened.push(normalizeTrace({
        ...connection,
        trace_id: traceId,
        node_id: connection.node_id ?? baseNodeId,
        operation_id: connection.operation_id ?? baseOperationId,
        started_at: connection.started_at || item.started_at,
        status: connection.connection_state || item.status,
        _record_kind: 'connection',
      }))
    }
    for (const message of Array.isArray(item.messages) ? item.messages : []) {
      flattened.push(normalizeTrace({
        ...message,
        trace_id: traceId,
        node_id: message.node_id ?? baseNodeId,
        operation_id: message.operation_id ?? baseOperationId,
        started_at: message.recorded_at || item.started_at,
        protocol: message.protocol
          || item.connections?.find((connection: any) => connection.connection_id === message.connection_id)?.protocol
          || item.operation?.protocol
          || item.protocol,
        _record_kind: 'message',
      }))
    }
  }
  return flattened
}

function traceRowKey(trace: DebugNetworkTraceRow): string {
  return [
    trace.trace_id,
    trace._record_kind || 'operation',
    trace.connection_id || '',
    trace.connection_epoch ?? '',
    trace.sequence_id ?? '',
    trace.event_kind || '',
    trace.debug_event_index ?? '',
    trace.recorded_at || '',
  ].join('|')
}

function isSelectedRow(trace: DebugNetworkTraceRow): boolean {
  return selectedRowKey.value === traceRowKey(trace)
}

function applySnapshot(snapshot: any) {
  if (!snapshot || typeof snapshot !== 'object') {
    summary.value = null
    traces.value = []
    clearSelection()
    return false
  }
  summary.value = snapshot.summary || null
  const orderedTraceIds = Array.isArray(snapshot.trace_order) ? snapshot.trace_order : Object.keys(snapshot.traces || {})
  const snapshotTraces: DebugNetworkTraceRow[] = snapshot.traces && typeof snapshot.traces === 'object'
    ? flattenTraceItems(orderedTraceIds.map((traceId: string) => snapshot.traces[traceId]))
    : []
  traces.value = snapshotTraces
  if (selected.value?.trace_id) {
    const selectedTrace = snapshotTraces.find((item: DebugNetworkTraceRow) => item.trace_id === selected.value?.trace_id)
    if (selectedTrace) selected.value = selectedTrace
    else clearSelection()
  }
  if (selectedRowKey.value) {
    const selectedTraceRow = snapshotTraces.find((item) => traceRowKey(item) === selectedRowKey.value)
    if (selectedTraceRow) selectedRow.value = selectedTraceRow
    else {
      selectedRow.value = null
      selectedRowKey.value = ''
    }
  }
  return true
}

function clearSelection() {
  selected.value = null
  selectedRow.value = null
  selectedRowKey.value = ''
  body.value = null
  requestBodyExpanded.value = false
  responseBodyExpanded.value = false
  messagesExpanded.value = false
}

async function loadNetwork() {
  const sid = sessionId.value
  if (!sid) {
    summary.value = null
    traces.value = []
    clearSelection()
    return
  }
  if (sourceMode.value === 'live' && applySnapshot(liveSnapshot.value)) {
    return
  }
  loading.value = true
  error.value = ''
  try {
    const loader = sourceMode.value === 'history'
      ? Promise.all([
        fetchDebugHistorySessionNetworkSummary(sid),
        fetchDebugHistorySessionNetwork(sid),
      ])
      : Promise.all([
        fetchDebugSessionNetworkSummary(sid),
        fetchDebugSessionNetwork(sid),
      ])
    const [summaryPayload, listPayload] = await loader
    summary.value = summaryPayload.summary
    traces.value = flattenTraceItems(listPayload.traces || [])
  } catch (cause: any) {
    error.value = cause?.message || t('framework.debug.network.loadFailed', '网络调试数据加载失败')
  } finally {
    loading.value = false
  }
}

async function selectTrace(trace: DebugNetworkTraceRow) {
  const sid = sessionId.value
  if (!sid || !trace.trace_id) return
  selectedRow.value = trace
  selectedRowKey.value = traceRowKey(trace)
  detailLoading.value = true
  error.value = ''
  requestBodyExpanded.value = false
  responseBodyExpanded.value = false
  messagesExpanded.value = false
  body.value = null
  try {
    selected.value = (
      await (
        sourceMode.value === 'history'
          ? fetchDebugHistorySessionNetworkTrace(sid, trace.trace_id)
          : fetchDebugSessionNetworkTrace(sid, trace.trace_id)
      )
    ).trace
  } catch (cause: any) {
    error.value = cause?.message || t('framework.debug.network.detailFailed', '网络轨迹详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function toggleBody(kind: 'request' | 'response') {
  const sid = sessionId.value
  const traceId = selected.value?.trace_id
  if (!sid || !traceId) return
  const expanded = kind === 'request' ? requestBodyExpanded : responseBodyExpanded
  expanded.value = !expanded.value
  const field = kind === 'request' ? 'request_body' : 'response_body'
  if (!expanded.value || (body.value && Object.prototype.hasOwnProperty.call(body.value, field))) return
  try {
    const payload = await (
      sourceMode.value === 'history'
        ? fetchDebugHistorySessionNetworkTraceBody(sid, traceId, kind)
        : fetchDebugSessionNetworkTraceBody(sid, traceId, kind)
    )
    body.value = { ...(body.value || {}), ...payload }
  } catch (cause: any) {
    expanded.value = false
    error.value = cause?.message || t('framework.debug.network.bodyFailed', '请求正文加载失败')
  }
}

async function toggleMessages() {
  const sid = sessionId.value
  const traceId = selected.value?.trace_id
  if (!sid || !traceId) return
  messagesExpanded.value = !messagesExpanded.value
  if (!messagesExpanded.value || (body.value && Object.prototype.hasOwnProperty.call(body.value, 'messages'))) return
  try {
    const payload = await (
      sourceMode.value === 'history'
        ? fetchDebugHistorySessionNetworkTraceBody(sid, traceId, 'messages')
        : fetchDebugSessionNetworkTraceBody(sid, traceId, 'messages')
    )
    body.value = { ...(body.value || {}), ...payload }
  } catch (cause: any) {
    messagesExpanded.value = false
    error.value = cause?.message || t('framework.debug.network.messagesFailed', '消息正文加载失败')
  }
}

function payloadText(payload: DebugNetworkBodyPayload | null | undefined) {
  if (!payload) return ''
  if (payload.encoding === 'text') return payload.text ?? String(payload.value ?? '')
  return typeof payload.value === 'string' ? payload.value : JSON.stringify(payload.value, null, 2)
}

function bodyPayload(kind: 'request' | 'response') {
  return body.value?.[`${kind}_body`]
    || selected.value?.operation?.[`${kind}_body`] as DebugNetworkBodyPayload | null
}

function payloadSummary(payload: DebugNetworkBodyPayload | null | undefined) {
  if (!payload) return ''
  const parts: string[] = []
  if (payload.encoding) parts.push(payload.encoding)
  if (payload.size_bytes != null) parts.push(`${payload.size_bytes} bytes`)
  if (payload.content_type) parts.push(payload.content_type)
  if (payload.sha256) parts.push(`sha256 ${payload.sha256}`)
  if (payload.resource_kind) parts.push(`引用 ${payload.resource_kind}`)
  if (payload.resource_id) parts.push(`资源 ${payload.resource_id}`)
  return parts.join(' · ')
}

function displayBody(kind: 'request' | 'response') {
  return payloadText(bodyPayload(kind))
}

function displayMessages() {
  return JSON.stringify(body.value?.messages || selected.value?.messages || [], null, 2)
}

function jsonText(value: unknown) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function locateSelectedNode() {
  const nodeId = selected.value?.node_id || selected.value?.operation?.node_id
  if (typeof nodeId === 'string' && nodeId) void locateGraphNode(nodeId)
}

async function locateSelectedEvent() {
  const sid = sessionId.value
  const row = selectedRow.value
  const selectedMessage = row?._record_kind === 'message'
    ? selected.value?.messages?.find((message) => (
      (row.sequence_id == null || message.sequence_id === row.sequence_id)
      && (row.connection_id == null || message.connection_id === row.connection_id)
      && (row.event_kind == null || message.event_kind === row.event_kind)
    ))
    : undefined
  const selectedConnection = row?._record_kind === 'connection'
    ? selected.value?.connections?.find((connection) => (
      connection.connection_id === row.connection_id
      && (row.connection_epoch == null || connection.connection_epoch === row.connection_epoch)
    ))
    : undefined
  const candidates = [
    row?.debug_event_index,
    selectedMessage?.debug_event_index,
    selectedConnection?.debug_event_index,
    selected.value?.debug_event_index,
    selected.value?.connections?.[0]?.debug_event_index,
    selected.value?.messages?.[0]?.debug_event_index,
  ]
  const eventIndex = candidates.find((value) => (
    typeof value === 'number' && Number.isInteger(value) && value >= 0
  ))
  if (!sid || typeof eventIndex !== 'number') return
  await debugStore.loadProjection(sid, 'history', eventIndex)
  dock.restorePanel('debugTimeline')
  dock.activatePanel('debugTimeline')
}

function formatTime(value: unknown) {
  if (typeof value !== 'string') return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour12: false })
}

watch(sourceScopeKey, () => { clearSelection() }, { immediate: true })
watch(sourceKey, () => { void loadNetwork() }, { immediate: true })
</script>

<template>
  <div class="dnp-root">
    <div class="dnp-toolbar">
      <span class="dnp-title">{{ t('framework.debug.network.title', '网络调试') }}</span>
      <span v-if="sessionId" class="dnp-session">{{ sessionId }}</span>
      <span v-if="loading" class="dnp-muted">{{ t('framework.debug.network.loading', '加载中…') }}</span>
    </div>
    <div v-if="error" class="dnp-error">{{ error }}</div>
    <div v-if="summary" class="dnp-summary">
      <span>{{ t('framework.debug.network.operations', '操作') }} {{ summary.total_operations }}</span>
      <span>{{ t('framework.debug.network.success', '成功') }} {{ summary.successful_operations }}</span>
      <span>{{ t('framework.debug.network.failed', '失败') }} {{ summary.failed_operations }}</span>
      <span>{{ t('framework.debug.network.connections', '连接') }} {{ summary.active_connections }}</span>
      <span>{{ t('framework.debug.network.queue', '队列') }} {{ summary.queue_depth }}</span>
      <span>{{ t('framework.debug.network.reconnects', '重连') }} {{ summary.reconnect_count }}</span>
      <span>{{ t('framework.debug.network.dropped', '丢弃') }} {{ summary.dropped_count }}</span>
      <span>{{ t('framework.debug.network.activationQueue', '激活队列') }} {{ summary.activation_queue_depth || 0 }}</span>
      <span>{{ t('framework.debug.network.activationDropped', '激活丢弃') }} {{ summary.activation_dropped_count || 0 }}</span>
      <span>{{ t('framework.debug.network.queueEvents', '队列事件') }} {{ summary.queue_events?.length || 0 }}</span>
      <span v-if="summary.recent_errors?.length">{{ t('framework.debug.network.recentError', '最近错误') }} {{ summary.recent_errors[summary.recent_errors.length - 1]?.error_code || '-' }}</span>
    </div>
    <div class="dnp-filters">
      <input v-model="query" :placeholder="t('framework.debug.network.search', '搜索 URL、节点或操作')">
      <input v-model="nodeFilter" data-testid="network-node-filter" :placeholder="t('framework.debug.network.nodeFilter', '节点 ID')">
      <input v-model="operationFilter" data-testid="network-operation-filter" :placeholder="t('framework.debug.network.operationFilter', '操作 ID')">
      <input v-model="connectionFilter" data-testid="network-connection-filter" :placeholder="t('framework.debug.network.connectionFilter', '连接 ID')">
      <input v-model="sessionFilter" data-testid="network-session-filter" :placeholder="t('framework.debug.network.sessionFilter', '会话 ID')">
      <input v-model="epochFilter" data-testid="network-epoch-filter" inputmode="numeric" :placeholder="t('framework.debug.network.epochFilter', 'epoch')">
      <input v-model="sequenceFilter" data-testid="network-sequence-filter" inputmode="numeric" :placeholder="t('framework.debug.network.sequenceFilter', '序号')">
      <input v-model="eventKindFilter" data-testid="network-event-kind-filter" :placeholder="t('framework.debug.network.eventKindFilter', '事件类型')">
      <select v-model="statusFilter" data-testid="network-status-filter">
        <option value="">{{ t('framework.debug.network.allStatuses', '全部状态') }}</option>
        <option value="running">running</option><option value="succeeded">succeeded</option>
        <option value="failed">failed</option><option value="cancelled">cancelled</option>
        <option value="connecting">connecting</option><option value="connected">connected</option>
        <option value="disconnected">disconnected</option><option value="closed">closed</option>
      </select>
      <select v-model="protocolFilter" data-testid="network-protocol-filter">
        <option value="">{{ t('framework.debug.network.allProtocols', '全部协议') }}</option>
        <option value="sse">SSE</option><option value="websocket">WebSocket</option>
        <option value="graphql">GraphQL</option><option value="graphql_subscription">GraphQL Subscription</option>
        <option value="http">HTTP</option><option value="browser">Browser</option>
      </select>
      <label class="dnp-check"><input v-model="onlyErrors" data-testid="network-only-errors" type="checkbox">{{ t('framework.debug.network.onlyErrors', '仅错误') }}</label>
      <label class="dnp-check"><input v-model="onlyActiveConnections" data-testid="network-only-active" type="checkbox">{{ t('framework.debug.network.onlyActive', '仅活跃连接') }}</label>
      <label class="dnp-check"><input v-model="onlyExecutionActivations" data-testid="network-only-activation" type="checkbox">{{ t('framework.debug.network.onlyActivation', '仅执行激活') }}</label>
      <label class="dnp-time">{{ t('framework.debug.network.fromTime', '从') }}<input v-model="fromTime" data-testid="network-from-time" type="datetime-local"></label>
      <label class="dnp-time">{{ t('framework.debug.network.toTime', '到') }}<input v-model="toTime" data-testid="network-to-time" type="datetime-local"></label>
    </div>
    <div v-if="!sessionId" class="dnp-empty">{{ t('framework.debug.network.noSession', '暂无活动 Debug 会话') }}</div>
    <div v-else class="dnp-content">
      <aside class="dnp-list">
        <button v-for="trace in filteredTraces" :key="traceRowKey(trace)" :data-trace-id="trace.trace_id" :class="['dnp-row', { active: isSelectedRow(trace) }]" @click="selectTrace(trace)">
          <span><strong>{{ trace._record_kind === 'message' ? trace.event_kind : trace.operation?.method || trace.protocol || trace.event_kind || 'network' }}</strong><small>{{ trace.status || trace.connection_state }}</small></span>
          <span class="dnp-url">{{ trace.operation?.url || trace.connection_id || trace.node_id || '-' }}</span>
          <time>{{ formatTime(trace.started_at) }}</time>
        </button>
        <div v-if="!filteredTraces.length" class="dnp-empty">{{ t('framework.debug.network.empty', '暂无网络记录') }}</div>
      </aside>
      <section v-if="selected" class="dnp-detail">
        <div v-if="detailLoading" class="dnp-muted">{{ t('framework.debug.network.loadingDetail', '加载详情…') }}</div>
        <dl class="dnp-grid">
          <div><dt>{{ t('framework.debug.network.field.operation', '操作') }}</dt><dd>{{ selected.operation_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.status', '状态') }}</dt><dd>{{ selected.status }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.methodUrl', '方法 / URL') }}</dt><dd>{{ selected.operation?.method }} {{ selected.operation?.url }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.duration', '耗时') }}</dt><dd>{{ selected.duration_ms ?? '-' }} ms</dd></div>
          <div><dt>{{ t('framework.debug.network.field.response', '响应') }}</dt><dd>{{ selected.operation?.response_status ?? '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.retry', '重试') }}</dt><dd>{{ selected.operation?.retry_attempt ?? 0 }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.finalUrl', '最终 URL') }}</dt><dd>{{ selected.operation?.final_url || selected.operation?.url || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.redirects', '重定向') }}</dt><dd>{{ selected.operation?.redirects?.length || 0 }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.node', '节点') }}</dt><dd>{{ selected.node_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.session', '会话') }}</dt><dd>{{ selected.debug_session_id || selected.operation?.debug_session_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.connection', '连接') }}</dt><dd>{{ selected.connections?.[0]?.connection_id || selected.connection_id || '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.epoch', 'Epoch / 序号') }}</dt><dd>{{ selected.connections?.[0]?.connection_epoch ?? selected.connection_epoch ?? '-' }} / {{ selected.messages?.[0]?.sequence_id ?? selected.sequence_id ?? '-' }}</dd></div>
          <div><dt>{{ t('framework.debug.network.field.debugEventIndex', 'Debug 事件索引') }}</dt><dd>{{ selected.debug_event_index ?? selected.connections?.[0]?.debug_event_index ?? selected.messages?.[0]?.debug_event_index ?? '-' }}</dd></div>
        </dl>
        <section v-if="selected.operation" class="dnp-metadata">
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.requestHeaders', '请求头') }}</strong>
            <pre data-testid="trace-request-headers">{{ jsonText(selected.operation.request_headers) }}</pre>
          </section>
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.queryParams', '查询参数') }}</strong>
            <pre data-testid="trace-request-query">{{ jsonText(selected.operation.request_query) }}</pre>
          </section>
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.responseHeaders', '响应头') }}</strong>
            <pre data-testid="trace-response-headers">{{ jsonText(selected.operation.response_headers) }}</pre>
          </section>
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.redirects', '重定向链') }}</strong>
            <pre data-testid="trace-redirects">{{ jsonText(selected.operation.redirects || []) }}</pre>
          </section>
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.proxy', '代理') }}</strong>
            <pre data-testid="trace-proxy">{{ jsonText(selected.operation.proxy) }}</pre>
          </section>
          <section class="dnp-subsection">
            <strong>{{ t('framework.debug.network.tls', 'TLS') }}</strong>
            <pre data-testid="trace-tls">{{ jsonText(selected.operation.tls) }}</pre>
          </section>
        </section>
        <div class="dnp-detail-actions">
          <button v-if="selected.node_id || selected.operation?.node_id" data-action="locate-network-node" class="dnp-locate" @click="locateSelectedNode">{{ t('framework.debug.network.locateNode', '定位图节点') }}</button>
          <button v-if="selected.debug_event_index != null || selected.connections?.some((item) => item.debug_event_index != null) || selected.messages?.some((item) => item.debug_event_index != null)" data-action="locate-debug-event" class="dnp-locate" @click="locateSelectedEvent">{{ t('framework.debug.network.locateDebugEvent', '定位 Debug 事件') }}</button>
        </div>
        <section class="dnp-body-block">
          <button data-action="toggle-request-body" @click="toggleBody('request')">{{ requestBodyExpanded ? '▾' : '▸' }} {{ t('framework.debug.network.requestBody', '请求体') }}</button>
          <div v-if="bodyPayload('request')" data-testid="trace-request-body-summary" class="dnp-body-summary">{{ payloadSummary(bodyPayload('request')) }}</div>
          <pre v-if="requestBodyExpanded" data-testid="trace-request-body">{{ displayBody('request') }}</pre>
        </section>
        <section class="dnp-body-block">
          <button data-action="toggle-response-body" @click="toggleBody('response')">{{ responseBodyExpanded ? '▾' : '▸' }} {{ t('framework.debug.network.responseBody', '响应体') }}</button>
          <div v-if="bodyPayload('response')" data-testid="trace-response-body-summary" class="dnp-body-summary">{{ payloadSummary(bodyPayload('response')) }}</div>
          <pre v-if="responseBodyExpanded" data-testid="trace-response-body">{{ displayBody('response') }}</pre>
        </section>
        <section v-if="selected.connections?.length" class="dnp-subsection">
          <strong>{{ t('framework.debug.network.connectionsDetail', '连接') }}</strong>
          <div v-for="connection in selected.connections" :key="connection.connection_id" class="dnp-connection-summary">
            <span>{{ connection.connection_id }}</span>
            <span>{{ connection.connection_state || '-' }}</span>
            <span>{{ t('framework.debug.network.connectionQueue', '队列') }} {{ connection.queue_depth ?? 0 }}</span>
            <span>{{ t('framework.debug.network.connectionActivationQueue', '激活队列') }} {{ connection.activation_queue_depth ?? 0 }}</span>
            <span>{{ t('framework.debug.network.connectionEpoch', 'Epoch') }} {{ connection.connection_epoch ?? '-' }}</span>
            <span>{{ t('framework.debug.network.connectionReconnects', '重连') }} {{ connection.reconnect_count ?? 0 }}</span>
            <span v-if="connection.reconnect_reason" data-testid="connection-reconnect-reason">{{ t('framework.debug.network.connectionReconnectReason', '重连原因') }} {{ connection.reconnect_reason }}</span>
            <span>{{ t('framework.debug.network.connectionDropped', '丢弃') }} {{ connection.dropped_count ?? 0 }}</span>
          </div>
          <pre>{{ JSON.stringify(selected.connections, null, 2) }}</pre>
        </section>
        <section v-if="selected.messages?.length" class="dnp-body-block">
          <button data-action="toggle-messages" @click="toggleMessages">{{ messagesExpanded ? '▾' : '▸' }} {{ t('framework.debug.network.messages', '消息') }}</button>
          <pre v-if="messagesExpanded" data-testid="trace-message-body">{{ displayMessages() }}</pre>
        </section>
      </section>
      <div v-else class="dnp-empty dnp-detail-empty">{{ t('framework.debug.network.selectPrompt', '选择网络记录查看详情') }}</div>
    </div>
  </div>
</template>

<style scoped>
.dnp-root { height: 100%; min-width: 620px; overflow: auto; padding: var(--space-md); color: var(--text-primary); }
.dnp-toolbar, .dnp-summary, .dnp-filters { display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap; }
.dnp-toolbar { min-height: 30px; border-bottom: 1px solid var(--border-subtle); }
.dnp-title { font-weight: 600; }.dnp-session, .dnp-muted { color: var(--text-disabled); font-family: var(--font-mono); font-size: var(--text-caption); }
.dnp-summary { padding: var(--space-sm) 0; color: var(--text-secondary); font-size: var(--text-caption); }.dnp-summary span + span { padding-left: var(--space-sm); border-left: 1px solid var(--border-subtle); }
.dnp-filters { padding-bottom: var(--space-sm); }.dnp-filters input, .dnp-filters select { min-height: 28px; border: 1px solid var(--border-default); background: var(--bg-input); color: var(--text-primary); border-radius: var(--radius-sm); padding: 3px 6px; font: inherit; }
.dnp-filters input { flex: 1; min-width: 180px; }.dnp-content { display: grid; grid-template-columns: minmax(250px, 34%) minmax(0, 1fr); min-height: 260px; border-top: 1px solid var(--border-subtle); }.dnp-list { overflow: auto; border-right: 1px solid var(--border-subtle); }.dnp-row { width: 100%; display: flex; flex-direction: column; align-items: stretch; gap: 3px; padding: var(--space-sm); border: 0; border-bottom: 1px solid var(--border-subtle); background: transparent; color: inherit; cursor: pointer; text-align: left; }.dnp-row:hover, .dnp-row.active { background: var(--bg-hover); }.dnp-row > span:first-child { display: flex; justify-content: space-between; gap: var(--space-sm); }.dnp-row small, .dnp-row time { color: var(--text-disabled); font: var(--text-caption) var(--font-mono); }.dnp-url { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: var(--text-caption) var(--font-mono); }.dnp-detail { min-width: 0; overflow: auto; padding: var(--space-md); }.dnp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }.dnp-grid > div { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: var(--space-sm); padding: var(--space-sm) 0; border-bottom: 1px solid var(--border-subtle); }.dnp-grid dt { color: var(--text-disabled); font-size: var(--text-caption); }.dnp-grid dd { margin: 0; overflow-wrap: anywhere; font: var(--text-caption) var(--font-mono); }.dnp-body-block, .dnp-subsection { padding-top: var(--space-md); }.dnp-body-block button { border: 0; background: transparent; color: var(--text-secondary); cursor: pointer; padding: 0; font: inherit; }.dnp-body-block pre, .dnp-subsection pre { max-height: 260px; overflow: auto; margin: var(--space-xs) 0 0; padding: var(--space-sm); background: var(--bg-secondary); border: 1px solid var(--border-subtle); white-space: pre-wrap; overflow-wrap: anywhere; font: var(--text-caption) var(--font-mono); }.dnp-empty { padding: var(--space-md); color: var(--text-disabled); font-size: var(--text-caption); }.dnp-detail-empty { align-self: center; text-align: center; }.dnp-error { padding: var(--space-xs) 0; color: var(--state-error); font-size: var(--text-caption); }
.dnp-check, .dnp-time { display: inline-flex; align-items: center; gap: var(--space-xs); color: var(--text-secondary); font-size: var(--text-caption); white-space: nowrap; }.dnp-check input { min-height: auto; flex: none; }.dnp-time input { min-width: 150px; }.dnp-locate { margin-top: var(--space-md); border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; padding: 3px 8px; border-radius: var(--radius-sm); font: inherit; }.dnp-locate:hover { background: var(--bg-hover); }
.dnp-detail-actions { display: flex; flex-wrap: wrap; gap: var(--space-sm); }.dnp-body-summary { margin-top: var(--space-xs); color: var(--text-disabled); font: var(--text-caption) var(--font-mono); overflow-wrap: anywhere; }
.dnp-connection-summary { display: flex; flex-wrap: wrap; gap: var(--space-sm); margin-top: var(--space-xs); color: var(--text-secondary); font: var(--text-caption) var(--font-mono); }.dnp-connection-summary span + span { padding-left: var(--space-sm); border-left: 1px solid var(--border-subtle); }
@media (max-width: 760px) { .dnp-root { min-width: 0; }.dnp-content { grid-template-columns: minmax(170px, 40%) minmax(0, 1fr); }.dnp-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
