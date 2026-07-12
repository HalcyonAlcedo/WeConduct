/** WeConduct — Shared Runtime/Debug Session Store
 *  Bridges TaskExecutionPanel, RuntimeTab, DebugTab so output tabs
 *  automatically reflect latest sessions from the task execution panel.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchRuntimeSessions,
  fetchRuntimeSession,
  postRuntimeStart,
  postRuntimeRun,
  postRuntimeAbort,
  getRuntimeStreamUrl,
  buildRuntimeProgressFromSession,
} from '@/services/api'
import type {
  RuntimeSessionSummary,
  RuntimeSessionDetailResponse,
  RuntimeProgress,
  RuntimeStreamSnapshot,
} from '@/types/domains/api'
import type { Diagnostic } from '@/types/domains/diagnostics'
import { useProjectDiagnosticsStore } from './projectDiagnosticsStore'

type RuntimeLiveStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'aborting'
  | 'aborted'
  | 'settling'
  | 'completed'
  | 'failed'
  | 'disconnected'
  | 'error'

function isTerminalRuntimeStatus(status: unknown): boolean {
  return status === 'completed' || status === 'failed' || status === 'aborted'
}

function getRuntimeSessionStatus(detail: RuntimeSessionDetailResponse | null | undefined) {
  return detail?.runtime_session?.status ?? detail?.status ?? null
}

function buildTerminalRunResult(
  detail: RuntimeSessionDetailResponse,
  status = getRuntimeSessionStatus(detail),
): { success: boolean; message: string } | null {
  const failedNodeCount = detail.node_states?.filter((node: any) => node.node_status === 'failed').length || 0
  if (status === 'completed') {
    return {
      success: failedNodeCount === 0,
      message: failedNodeCount ? `${failedNodeCount} 节点失败` : `${detail.node_states?.length || 0} 节点完成`,
    }
  }
  if (status === 'failed') {
    return {
      success: false,
      message: failedNodeCount ? `${failedNodeCount} 节点失败` : '运行失败',
    }
  }
  if (status === 'aborted') {
    return { success: false, message: '运行已终止' }
  }
  return null
}

export const useRuntimeStore = defineStore('runtime', () => {
  const rtSessions = ref<RuntimeSessionSummary[]>([])
  const activeRt = ref<RuntimeSessionDetailResponse | null>(null)
  const runtimeProgress = ref<RuntimeProgress | null>(null)
  const runtimeLiveConnected = ref(false)
  const runtimeLiveStatus = ref<RuntimeLiveStatus>('idle')
  const isRunStarting = ref(false)
  const isAbortGuarded = ref(false)
  let abortGuardTimer: ReturnType<typeof setTimeout> | null = null
  let cancelRuntimeReconciliation: (() => void) | null = null
  const activeRuntimeStatus = computed(() => activeRt.value?.runtime_session?.status ?? null)
  const isRuntimeActive = computed(() =>
    isRunStarting.value
      || ['preparing', 'ready', 'running', 'aborting'].includes(activeRuntimeStatus.value ?? '')
      || ['connecting', 'streaming', 'aborting', 'settling'].includes(runtimeLiveStatus.value)
  )
  const canAbortRuntime = computed(() =>
    isRuntimeActive.value
      && !isRunStarting.value
      && !isAbortGuarded.value
      && runtimeLiveStatus.value !== 'aborting'
      && runtimeLiveStatus.value !== 'settling'
      && activeRuntimeStatus.value !== 'aborting'
      && !!activeRt.value?.runtime_session?.session_id
  )

  function clearAbortGuard() {
    if (abortGuardTimer) clearTimeout(abortGuardTimer)
    abortGuardTimer = null
    isAbortGuarded.value = false
  }

  function armAbortGuard() {
    clearAbortGuard()
    isAbortGuarded.value = true
    abortGuardTimer = setTimeout(() => {
      abortGuardTimer = null
      isAbortGuarded.value = false
    }, 600)
  }
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
  let settledRunResult: { success: boolean; message: string } | null = null

  function resolvePendingRun(result: { success: boolean; message: string }) {
    clearAbortGuard()
    if (pendingRunResolver) {
      const resolver = pendingRunResolver
      pendingRunResolver = null
      settledRunResult = null
      resolver(result)
      return
    }
    settledRunResult = result
  }

  async function refreshAll() {
    try {
      const r = await fetchRuntimeSessions()
      rtSessions.value = r.sessions
    } catch {}
  }

  async function loadRtDetail(id: string) {
    try {
      setActiveRt(await fetchRuntimeSession(id))
    } catch {}
  }

  function setActiveRt(detail: RuntimeSessionDetailResponse) {
    const runtimeStatus = getRuntimeSessionStatus(detail)
    activeRt.value = runtimeStatus ? { ...detail, status: runtimeStatus } : detail
    const projectDiagnostics = useProjectDiagnosticsStore()
    projectDiagnostics.ingestCatalog(activeRt.value.diagnostics, { source: 'runtime', operation: 'runtime.session' })
    projectDiagnostics.ingestCatalog(activeRt.value.diagnostic_events, { source: 'runtime', operation: 'runtime.session' })
    // Only update progress from node_states if there is actual data (avoids overwriting SSE summary)
    const nodeStates = Array.isArray(activeRt.value.node_states) ? activeRt.value.node_states : []
    const hasNodeData = nodeStates.length > 0
    if (hasNodeData || !runtimeProgress.value) {
      runtimeProgress.value = buildRuntimeProgressFromSession(activeRt.value)
    }
  }

  function unsubscribeRuntimeSession() {
    cancelRuntimeReconciliation?.()
    cancelRuntimeReconciliation = null
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
    runtimeLiveStatus.value = 'streaming'
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
    const runtimeStatus = getRuntimeSessionStatus(snapshot)
    if (isTerminalRuntimeStatus(runtimeStatus)) return
    setActiveRt(snapshot)
    runtimeLiveConnected.value = true
    runtimeLiveStatus.value = 'streaming'
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
    const isCurrentStream = () => runtimeEventSource === eventSource && subscribedRuntimeSessionId === sessionId
    let reconcileTimer: ReturnType<typeof setTimeout> | null = null
    let reconcileInFlight: Promise<void> | null = null

    const cancelReconciliation = () => {
      if (reconcileTimer) clearTimeout(reconcileTimer)
      reconcileTimer = null
    }
    cancelRuntimeReconciliation = cancelReconciliation

    const scheduleReconciliation = () => {
      if (!isCurrentStream() || reconcileTimer) return
      reconcileTimer = setTimeout(() => {
        reconcileTimer = null
        void reconcileFromBackend()
      }, 300)
    }

    const reconcileFromBackend = async () => {
      if (!isCurrentStream()) return
      if (reconcileInFlight) return reconcileInFlight
      reconcileInFlight = (async () => {
        try {
          const latest = await fetchRuntimeSession(sessionId)
          if (!isCurrentStream()) return
          setActiveRt(latest)
          const latestStatus = getRuntimeSessionStatus(latest)
          if (isTerminalRuntimeStatus(latestStatus)) {
            runtimeLiveStatus.value = latestStatus as RuntimeLiveStatus
            const terminalResult = buildTerminalRunResult(latest, latestStatus)
            unsubscribeRuntimeSession()
            if (terminalResult) resolvePendingRun(terminalResult)
            return
          }
          scheduleReconciliation()
        } catch {
          if (!isCurrentStream()) return
          runtimeLiveStatus.value = 'error'
          scheduleReconciliation()
        }
      })().finally(() => {
        reconcileInFlight = null
      })
      return reconcileInFlight
    }

    const requestTerminalReconciliation = () => {
      if (!isCurrentStream()) return
      runtimeLiveConnected.value = false
      runtimeLiveStatus.value = 'settling'
      cancelReconciliation()
      void reconcileFromBackend()
    }

    eventSource.addEventListener('runtime.snapshot', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      const payload = JSON.parse(event.data) as RuntimeStreamSnapshot
      const runtimeStatus = getRuntimeSessionStatus(payload)
      if (isTerminalRuntimeStatus(runtimeStatus)) {
        requestTerminalReconciliation()
        return
      }
      cancelReconciliation()
      applyRuntimeSnapshot(payload)
    }) as EventListener)

    eventSource.addEventListener('runtime.summary', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      cancelReconciliation()
      const payload = JSON.parse(event.data) as RuntimeProgress
      applyRuntimeSummary(payload)
    }) as EventListener)

    eventSource.addEventListener('runtime.node', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      cancelReconciliation()
      const payload = JSON.parse(event.data)
      applyRuntimeNode(payload)
    }) as EventListener)

    eventSource.addEventListener('runtime.completed', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      JSON.parse(event.data)
      requestTerminalReconciliation()
    }) as EventListener)

    eventSource.addEventListener('runtime.failed', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      JSON.parse(event.data)
      requestTerminalReconciliation()
    }) as EventListener)

    eventSource.addEventListener('runtime.aborting', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      const payload = JSON.parse(event.data) as { abort_reason?: string }
      runtimeLiveStatus.value = 'aborting'
      if (activeRt.value) {
        activeRt.value = {
          ...activeRt.value,
          runtime_session: {
            ...activeRt.value.runtime_session,
            status: 'aborting',
            abort_reason: payload.abort_reason ?? 'user_abort',
          },
        }
      }
    }) as EventListener)

    eventSource.addEventListener('runtime.aborted', ((event: MessageEvent) => {
      if (!isCurrentStream()) return
      JSON.parse(event.data)
      requestTerminalReconciliation()
    }) as EventListener)

    eventSource.onerror = async () => {
      if (!isCurrentStream()) return
      runtimeLiveConnected.value = false
      runtimeLiveStatus.value = 'disconnected'
      cancelReconciliation()
      await reconcileFromBackend()
    }
  }

  /** One-click start + run: prepare, start session, subscribe stream, run, return result.
   *  When project is loaded and graph is clean, uses saved graph (no payload).
   *  Only passes graph_document for unsaved/dirty in-memory graphs. */
  async function startAndRun(
    graphDocument?: Record<string, unknown>,
    isDirty?: boolean,
  ): Promise<{ success: boolean; message: string; securityBlocked?: boolean }> {
    if (isRunStarting.value) {
      return { success: false, message: '运行正在启动，请稍候' }
    }
    if (isRuntimeActive.value) {
      return { success: false, message: '已有运行中的任务，请先终止或等待完成' }
    }
    isRunStarting.value = true
    clearAbortGuard()
    settledRunResult = null
    // Trigger output panel + diagnostics tab
    requestRuntimeTab()
    try {
      const body = (graphDocument && isDirty) ? { graph_document: graphDocument } : undefined
      const r = await postRuntimeStart(body)
      if (!r.runtime_session.session_id) {
        isRunStarting.value = false
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
      isRunStarting.value = false
      armAbortGuard()
      const acceptedStatus = getRuntimeSessionStatus(runAccepted)
      const terminalResult = buildTerminalRunResult(runAccepted, acceptedStatus)
      if (terminalResult) {
        clearAbortGuard()
        await refreshAll()
        return terminalResult
      }

      return await new Promise<{ success: boolean; message: string }>((resolve) => {
        pendingRunResolver = async (result) => {
          await refreshAll()
          resolve(result)
        }
        if (settledRunResult) {
          const result = settledRunResult
          settledRunResult = null
          resolvePendingRun(result)
        }
      })
    } catch (e: any) {
      isRunStarting.value = false
      clearAbortGuard()
      pendingRunResolver = null
      settledRunResult = null
      if (e?.body) setActiveRt(e.body as any)
      useProjectDiagnosticsStore().ingestApiError(e, { source: 'runtime', operation: 'runtime.start_and_run' })
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

  async function abortActiveRun(reason = 'user_abort'): Promise<{ success: boolean; message: string }> {
    const currentRuntime = activeRt.value
    const sessionId = currentRuntime?.runtime_session?.session_id
    if (!currentRuntime || !sessionId || !isRuntimeActive.value) {
      return { success: false, message: '当前没有可终止的运行任务' }
    }
    if (!canAbortRuntime.value) {
      return { success: false, message: isRunStarting.value ? '运行正在启动，请稍候' : '当前暂不可终止' }
    }
    runtimeLiveStatus.value = 'aborting'
    activeRt.value = {
      ...currentRuntime,
      runtime_session: {
        ...currentRuntime.runtime_session,
        status: 'aborting',
        abort_reason: reason,
      },
    }
    try {
      const result = await postRuntimeAbort(sessionId, reason)
      setActiveRt(result)
      if (result.runtime_session.status === 'aborted') {
        runtimeLiveStatus.value = 'aborted'
        unsubscribeRuntimeSession()
        resolvePendingRun({ success: false, message: '运行已终止' })
      }
      await refreshAll()
      return {
        success: result.runtime_session.status === 'aborted',
        message: result.runtime_session.status === 'aborted' ? '运行已终止' : '正在终止运行任务',
      }
    } catch (error: any) {
      runtimeLiveStatus.value = 'error'
      useProjectDiagnosticsStore().ingestApiError(error, { source: 'runtime', operation: 'runtime.abort' })
      return { success: false, message: error?.body?.message || error?.message || '终止失败' }
    }
  }

  return {
    rtSessions,
    activeRt,
    runtimeProgress,
    runtimeLiveConnected,
    runtimeLiveStatus,
    isRunStarting,
    isRuntimeActive,
    canAbortRuntime,
    refreshAll,
    loadRtDetail,
    setActiveRt,
    subscribeRuntimeSession,
    unsubscribeRuntimeSession,
    startAndRun,
    abortActiveRun,
    runtimeTabRequest,
    requestRuntimeTab,
    runtimeDiagnosticGroups,
    hasRuntimeDiagnostics,
    getRuntimeDiagnosticEntries,
  }
})
