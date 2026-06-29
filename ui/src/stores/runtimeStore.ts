/** WeConduct — Shared Runtime/Debug Session Store
 *  Bridges TaskExecutionPanel, RuntimeTab, DebugTab so output tabs
 *  automatically reflect latest sessions from the task execution panel.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchRuntimeSessions,
  fetchRuntimeSession,
  fetchDebugSessions,
  fetchDebugSession,
  postRuntimeStart,
  postRuntimeRun,
  getRuntimeStreamUrl,
  buildRuntimeProgressFromSession,
} from '@/services/api'
import type {
  RuntimeSessionSummary,
  RuntimeSessionDetailResponse,
  RuntimeProgress,
  RuntimeStreamSnapshot,
  DebugSessionSummary,
  DebugSessionDetailResponse,
} from '@/types/domains/api'
import type { Diagnostic } from '@/types/domains/diagnostics'

type RuntimeLiveStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'disconnected'
  | 'error'

function isTerminalRuntimeStatus(status: unknown): boolean {
  return status === 'completed' || status === 'failed'
}

export const useRuntimeStore = defineStore('runtime', () => {
  const rtSessions = ref<RuntimeSessionSummary[]>([])
  const dbSessions = ref<DebugSessionSummary[]>([])
  const activeRt = ref<RuntimeSessionDetailResponse | null>(null)
  const activeDb = ref<DebugSessionDetailResponse | null>(null)
  const runtimeProgress = ref<RuntimeProgress | null>(null)
  const runtimeLiveConnected = ref(false)
  const runtimeLiveStatus = ref<RuntimeLiveStatus>('idle')
  /** Bump to request OutputPanel to switch to Runtime tab */
  const runtimeTabRequest = ref(0)
  function requestRuntimeTab() { runtimeTabRequest.value++ }

  /** Extract raw runtime events that carry diagnostic info.
   *  Priority: diagnostic_events → event_log (filter diagnostic.raised) → result.failure_reason */
  function extractRuntimeDiagnosticEvents(): Array<Record<string, unknown>> {
    const rt = activeRt.value
    if (!rt) return []
    // 1. diagnostic_events field
    const diagEvents = rt.diagnostic_events
    if (Array.isArray(diagEvents) && diagEvents.length) return diagEvents as Array<Record<string, unknown>>
    // 2. event_log filtered for diagnostic.raised
    const eventLog = rt.event_log
    if (Array.isArray(eventLog)) {
      const diagEntries = eventLog.filter((e: any) => e?.event_kind === 'diagnostic.raised')
      if (diagEntries.length) return diagEntries as Array<Record<string, unknown>>
    }
    // 3. result.failure_reason as fallback
    const result = rt.result as Record<string, unknown> | undefined
    if (result?.failure_reason || result?.message) {
      return [{
        message: result.failure_reason || result.message,
        severity: rt.status === 'failed' ? 'error' : 'info',
        error_code: 'runtime.result',
      }]
    }
    return []
  }

  /** Normalize a runtime event into a Diagnostic-compatible shape */
  function normalizeRuntimeEvent(e: Record<string, unknown>, idx: number): Diagnostic {
    const sessionId = activeRt.value?.runtime_session?.session_id || ''
    const nodeId = String(e.node_id || '')
    return {
      diagnostic_id: String(e.diagnostic_id || `runtime:${sessionId}:${idx}`),
      stage: (e.stage || 'runtime') as Diagnostic['stage'],
      category: String(e.error_code || e.event_kind || e.category || 'runtime.node_failed'),
      severity: (e.severity || 'error') as Diagnostic['severity'],
      message: String(e.message || ''),
      object_ref: nodeId ? `node:${nodeId}` : null,
      trace_ref: null,
      stage_extension: {
        graph_ref: nodeId ? { node_id: nodeId } : null,
        session_id: sessionId || null,
        node_kind: e.node_kind ?? null,
        event_kind: e.event_kind ?? null,
        recorded_at: e.recorded_at ?? null,
        error_code: e.error_code ?? null,
      },
      degraded_extension: null,
    }
  }

  /** Runtime diagnostics from activeRt, for the Diagnostics tab. */
  const runtimeDiagnosticGroups = computed(() => {
    const events = extractRuntimeDiagnosticEvents()
    if (!events.length) return []
    const map = new Map<string, { stage: string; category: string; severity: string; count: number; message: string }>()
    for (const e of events) {
      const stage = String(e.stage || 'runtime')
      const category = String(e.error_code || e.event_kind || e.category || 'runtime')
      const severity = String(e.severity || 'error')
      const message = String(e.message || '')
      const key = `${stage}|${category}|${severity}|${message}`
      const existing = map.get(key)
      if (existing) { existing.count++ }
      else map.set(key, { stage, category, severity, count: 1, message })
    }
    return [...map.values()]
  })

  const hasRuntimeDiagnostics = computed(() => runtimeDiagnosticGroups.value.length > 0)

  function getRuntimeDiagnosticEntries(): Diagnostic[] {
    return extractRuntimeDiagnosticEvents().map((e, i) => normalizeRuntimeEvent(e, i))
  }

  let runtimeEventSource: EventSource | null = null
  let subscribedRuntimeSessionId: string | null = null
  let pendingRunResolver: ((result: { success: boolean; message: string }) => void) | null = null

  function resolvePendingRun(result: { success: boolean; message: string }) {
    if (pendingRunResolver) {
      const resolver = pendingRunResolver
      pendingRunResolver = null
      resolver(result)
    }
  }

  async function refreshAll() {
    try {
      const r = await fetchRuntimeSessions()
      rtSessions.value = r.sessions
    } catch {}
    try {
      const r = await fetchDebugSessions()
      dbSessions.value = r.sessions
    } catch {}
  }

  async function loadRtDetail(id: string) {
    try {
      activeRt.value = await fetchRuntimeSession(id)
      if (activeRt.value) {
        runtimeProgress.value = buildRuntimeProgressFromSession(activeRt.value)
      }
    } catch {}
  }

  async function loadDbDetail(id: string) {
    try {
      activeDb.value = await fetchDebugSession(id)
    } catch {}
  }

  function setActiveRt(detail: RuntimeSessionDetailResponse) {
    activeRt.value = detail
    // Only update progress from node_states if there is actual data (avoids overwriting SSE summary)
    const nodeStates = Array.isArray(detail.node_states) ? detail.node_states : []
    const hasNodeData = nodeStates.length > 0
    if (hasNodeData || !runtimeProgress.value) {
      runtimeProgress.value = buildRuntimeProgressFromSession(detail)
    }
  }

  function setActiveDb(detail: DebugSessionDetailResponse) {
    activeDb.value = detail
  }

  function unsubscribeRuntimeSession() {
    if (runtimeEventSource) {
      runtimeEventSource.close()
      runtimeEventSource = null
    }
    subscribedRuntimeSessionId = null
    runtimeLiveConnected.value = false
    if (!isTerminalRuntimeStatus(runtimeLiveStatus.value)) {
      runtimeLiveStatus.value = 'idle'
    }
  }

  function applyRuntimeSummary(summary: RuntimeProgress) {
    runtimeProgress.value = summary
    runtimeLiveConnected.value = true
    runtimeLiveStatus.value = isTerminalRuntimeStatus(summary.status)
      ? (summary.status as RuntimeLiveStatus)
      : 'streaming'
  }

  /** Incrementally update activeRt.node_states from runtime.node SSE event */
  function applyRuntimeNode(payload: { session_id?: string; node_id?: string; node_status?: string; started_at?: string; completed_at?: string; output?: unknown; error?: unknown; node_kind?: string; display_name?: string }) {
    if (!payload.node_id || !activeRt.value) return
    const ns = activeRt.value.node_states ? [...activeRt.value.node_states] : []
    const idx = ns.findIndex((n: any) => n.node_id === payload.node_id)
    if (idx >= 0) {
      ns[idx] = { ...ns[idx], ...payload }
    } else {
      ns.push({
        node_id: payload.node_id,
        node_status: payload.node_status || 'running',
        started_at: payload.started_at || null,
        completed_at: payload.completed_at || null,
        output: payload.output ?? null,
        error: payload.error ?? null,
        node_kind: payload.node_kind || null,
        display_name: payload.display_name || payload.node_id,
      } as any)
    }
    activeRt.value = { ...activeRt.value, node_states: ns }
    // Append local event_log entry for node state transitions
    const eventKind = payload.node_status === 'running' ? 'node.started'
      : payload.node_status === 'completed' ? 'node.completed'
      : payload.node_status === 'failed' ? 'node.failed'
      : null
    if (eventKind) {
      const log = activeRt.value.event_log ? [...activeRt.value.event_log] : []
      log.push({ event_kind: eventKind, node_id: payload.node_id, node_status: payload.node_status, recorded_at: new Date().toISOString(), message: payload.error || payload.output || '' })
      activeRt.value = { ...activeRt.value, event_log: log }
    }
    // Update progress
    runtimeProgress.value = buildRuntimeProgressFromSession(activeRt.value)
  }

  function applyRuntimeSnapshot(snapshot: RuntimeStreamSnapshot) {
    setActiveRt(snapshot)
    runtimeLiveConnected.value = true
    runtimeLiveStatus.value = isTerminalRuntimeStatus(snapshot.status)
      ? (snapshot.status as RuntimeLiveStatus)
      : 'streaming'
    if (snapshot.status === 'completed') {
      const failCount = snapshot.node_states?.filter((n: any) => n.node_status === 'failed').length || 0
      resolvePendingRun({
        success: failCount === 0,
        message: failCount ? `${failCount} 节点失败` : `${snapshot.node_states?.length || 0} 节点完成`,
      })
    } else if (snapshot.status === 'failed') {
      const failCount = snapshot.node_states?.filter((n: any) => n.node_status === 'failed').length || 0
      resolvePendingRun({
        success: false,
        message: failCount ? `${failCount} 节点失败` : '运行失败',
      })
    }
  }

  function subscribeRuntimeSession(sessionId: string) {
    if (!sessionId) return
    if (subscribedRuntimeSessionId === sessionId && runtimeEventSource) return
    unsubscribeRuntimeSession()
    subscribedRuntimeSessionId = sessionId
    runtimeLiveStatus.value = 'connecting'
    runtimeLiveConnected.value = false

    const eventSource = new EventSource(getRuntimeStreamUrl(sessionId))
    runtimeEventSource = eventSource

    eventSource.addEventListener('runtime.snapshot', ((event: MessageEvent) => {
      const payload = JSON.parse(event.data) as RuntimeStreamSnapshot
      applyRuntimeSnapshot(payload)
      if (isTerminalRuntimeStatus(payload.status)) {
        unsubscribeRuntimeSession()
        runtimeLiveStatus.value = payload.status as RuntimeLiveStatus
      }
    }) as EventListener)

    eventSource.addEventListener('runtime.summary', ((event: MessageEvent) => {
      const payload = JSON.parse(event.data) as RuntimeProgress
      applyRuntimeSummary(payload)
    }) as EventListener)

    eventSource.addEventListener('runtime.node', ((event: MessageEvent) => {
      const payload = JSON.parse(event.data)
      applyRuntimeNode(payload)
    }) as EventListener)

    eventSource.addEventListener('runtime.completed', ((event: MessageEvent) => {
      const payload = JSON.parse(event.data) as RuntimeStreamSnapshot
      applyRuntimeSnapshot(payload)
      unsubscribeRuntimeSession()
      runtimeLiveStatus.value = 'completed'
    }) as EventListener)

    eventSource.addEventListener('runtime.failed', ((event: MessageEvent) => {
      const payload = JSON.parse(event.data) as RuntimeStreamSnapshot
      applyRuntimeSnapshot(payload)
      unsubscribeRuntimeSession()
      runtimeLiveStatus.value = 'failed'
    }) as EventListener)

    eventSource.onerror = async () => {
      runtimeLiveConnected.value = false
      if (runtimeLiveStatus.value === 'completed' || runtimeLiveStatus.value === 'failed') {
        return
      }
      runtimeLiveStatus.value = 'error'
      if (sessionId) {
        try {
          const latest = await fetchRuntimeSession(sessionId)
          setActiveRt(latest)
          if (isTerminalRuntimeStatus(latest.status)) {
            runtimeLiveStatus.value = latest.status as RuntimeLiveStatus
            unsubscribeRuntimeSession()
            return
          }
          runtimeLiveStatus.value = 'disconnected'
          resolvePendingRun({ success: false, message: '实时连接中断' })
        } catch {
          runtimeLiveStatus.value = 'error'
          resolvePendingRun({ success: false, message: '实时连接错误' })
        }
      }
    }
  }

  /** One-click start + run: prepare, start session, subscribe stream, run, return result.
   *  When project is loaded and graph is clean, uses saved graph (no payload).
   *  Only passes graph_document for unsaved/dirty in-memory graphs. */
  async function startAndRun(
    graphDocument?: Record<string, unknown>,
    isDirty?: boolean,
  ): Promise<{ success: boolean; message: string; securityBlocked?: boolean }> {
    // Trigger output panel + diagnostics tab
    requestRuntimeTab()
    try {
      const body = (graphDocument && isDirty) ? { graph_document: graphDocument } : undefined
      const r = await postRuntimeStart(body)
      if (!r.runtime_session.session_id) {
        setActiveRt(r)
        // Check for security requirement blockage
        const secSummary = (r as any).security_requirement_summary
        if (secSummary && !secSummary.ready) {
          const fields = secSummary.blocked_entries?.map((e: any) => e.display_name).join('、') || ''
          return { success: false, message: `安全设置不足（${fields}），请在项目设置中一键开启`, securityBlocked: true }
        }
        // Check diagnostics for security requirement blocked
        const diags = (r as any).diagnostics?.entries || []
        const secDiag = diags.find((d: any) => d.category === 'package.security.requirement_blocked')
        if (secDiag) {
          return { success: false, message: `安全设置不足（${secDiag.display_name || '未知项'}），请在项目设置中一键开启`, securityBlocked: true }
        }
        return { success: false, message: r.status === 'diagnostic_blocked' ? '启动被阻断，请检查诊断信息' : '无会话 ID' }
      }
      setActiveRt(r)
      await refreshAll()
      subscribeRuntimeSession(r.runtime_session.session_id)
      const runAccepted = await postRuntimeRun(r.runtime_session.session_id)
      setActiveRt(runAccepted)
      if (runAccepted.status === 'completed' || runAccepted.status === 'failed') {
        await refreshAll()
        const failCount = runAccepted.node_states?.filter((n: any) => n.node_status === 'failed').length || 0
        return {
          success: failCount === 0,
          message: failCount ? `${failCount} 节点失败` : `${runAccepted.node_states?.length || 0} 节点完成`,
        }
      }

      return await new Promise<{ success: boolean; message: string }>((resolve) => {
        pendingRunResolver = async (result) => {
          await refreshAll()
          resolve(result)
        }
      })
    } catch (e: any) {
      pendingRunResolver = null
      if (e?.body) setActiveRt(e.body as any)
      return {
        success: false,
        message:
          e?.body?.details?.primary_diagnostic?.message ||
          e?.body?.message ||
          e?.body?.error ||
          e?.message ||
          '运行失败',
      }
    }
  }

  return {
    rtSessions,
    dbSessions,
    activeRt,
    activeDb,
    runtimeProgress,
    runtimeLiveConnected,
    runtimeLiveStatus,
    refreshAll,
    loadRtDetail,
    loadDbDetail,
    setActiveRt,
    setActiveDb,
    subscribeRuntimeSession,
    unsubscribeRuntimeSession,
    startAndRun,
    runtimeTabRequest,
    requestRuntimeTab,
    runtimeDiagnosticGroups,
    hasRuntimeDiagnostics,
    getRuntimeDiagnosticEntries,
  }
})
