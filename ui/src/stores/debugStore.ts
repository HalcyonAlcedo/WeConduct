import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchDebugSessions,
  fetchDebugHistorySessions,
  fetchDebugSession,
  fetchDebugHistorySession,
  fetchDebugProjection,
  fetchDebugEvents,
  postDebugPrepare,
  postDebugStart,
  postDebugContinue,
  postDebugStepOver,
  postDebugStepInto,
  postDebugStepOut,
  postDebugPause,
  postDebugAbort,
  postDebugVariablesApply,
  postDebugNodeDebuggerApply,
} from '@/services/api'
import type {
  DebugSessionSummary,
  DebugSessionDetailResponse,
  DebugHistorySummaryResponse,
  DebugHistorySessionResponse,
  DebugProjection,
  DebugProjectionResponse,
  DebugEventsResponse,
  DebugEvent,
  DebugControlResponse,
  DebugSessionDocument,
  DebugVariablesApplyRequest,
} from '@/types/domains/api'
import { useProjectDiagnosticsStore } from './projectDiagnosticsStore'

const ACTIVE_DEBUG_STATUSES = ['preparing', 'running', 'paused', 'stepping'] as const
const TERMINAL_DEBUG_STATUSES = ['completed', 'failed', 'cancelled', 'aborted', 'incomplete'] as const

export const useDebugStore = defineStore('debug', () => {
  const sessions = ref<DebugSessionSummary[]>([])
  const historySessions = ref<Record<string, unknown>[]>([])
  const historySummary = ref<DebugHistorySummaryResponse['summary'] | null>(null)
  const activeSession = ref<DebugSessionDetailResponse | null>(null)
  const activeHistorySession = ref<DebugHistorySessionResponse | null>(null)
  const sessionDebuggerConfigs = ref<Record<string, Record<string, unknown>>>({})

  // 0.8.0: projection, events, control
  const projection = ref<DebugProjection | null>(null)
  const projectionVariableSnapshot = ref<Record<string, unknown> | null>(null)
  const projectionRuntimePreview = ref<Record<string, unknown> | null>(null)
  const events = ref<DebugEvent[]>([])
  const eventsTotal = ref(0)
  const eventsSessionId = ref<string | null>(null)
  const controlLoading = ref(false)

  function normalizeDebugStatus(status: unknown): string {
    return typeof status === 'string' ? status : ''
  }

  function isActiveDebugStatus(status: unknown): boolean {
    return ACTIVE_DEBUG_STATUSES.includes(normalizeDebugStatus(status) as (typeof ACTIVE_DEBUG_STATUSES)[number])
  }

  function isTerminalDebugStatus(status: unknown): boolean {
    return TERMINAL_DEBUG_STATUSES.includes(normalizeDebugStatus(status) as (typeof TERMINAL_DEBUG_STATUSES)[number])
  }

  function normalizeDebugSessionDocument<T extends Record<string, any> | null>(session: T): T {
    if (!session) return session
    return { ...session, status: normalizeDebugStatus(session.status) }
  }

  function normalizeDebugSessionSummary<T extends Record<string, any>>(session: T): T {
    return { ...session, status: normalizeDebugStatus(session.status) }
  }

  function normalizeDebugDetail<T extends Record<string, any> | null>(detail: T): T {
    if (!detail) return detail
    return {
      ...detail,
      status: normalizeDebugStatus(detail.status),
      debug_session: normalizeDebugSessionDocument(detail.debug_session),
    }
  }

  function normalizeHistorySummaryCounts(counts: Record<string, number> | undefined) {
    const normalized: Record<string, number> = {}
    for (const [status, count] of Object.entries(counts || {})) {
      const key = normalizeDebugStatus(status)
      normalized[key] = (normalized[key] || 0) + count
    }
    return normalized
  }

  function getActiveDebugStatus(): string {
    return normalizeDebugStatus(activeSession.value?.debug_session?.status || activeSession.value?.status)
  }

  function extractSessionDebuggerConfigs(detail: DebugSessionDetailResponse | null) {
    const runtimePlan = (detail as any)?.runtime_plan
    if (!Array.isArray(runtimePlan?.executable_nodes)) return null
    const configs: Record<string, Record<string, unknown>> = {}
    for (const executableNode of runtimePlan.executable_nodes) {
      const nodeId = executableNode?.node_id
      const debuggerConfig = executableNode?.node_config?.debugger
      if (typeof nodeId === 'string' && debuggerConfig && typeof debuggerConfig === 'object') {
        configs[nodeId] = { ...debuggerConfig }
      }
    }
    return configs
  }

  function setActiveSessionDetail(detail: DebugSessionDetailResponse | null) {
    const normalized = normalizeDebugDetail(detail)
    const previousSessionId = activeSession.value?.debug_session?.session_id
    const nextSessionId = normalized?.debug_session?.session_id
    const nextStatus = normalized?.debug_session?.status || normalized?.status
    const runtimeDebuggerConfigs = extractSessionDebuggerConfigs(normalized)
    if (isTerminalDebugStatus(nextStatus)) {
      sessionDebuggerConfigs.value = {}
    } else if (runtimeDebuggerConfigs) {
      sessionDebuggerConfigs.value = runtimeDebuggerConfigs
    } else if (previousSessionId !== nextSessionId) {
      sessionDebuggerConfigs.value = {}
    }
    activeSession.value = normalized
  }

  /** True when a debug session is actively locking the graph (preparing/running/paused/stepping) */
  const isDebugActive = computed(() => {
    return isActiveDebugStatus(getActiveDebugStatus())
  })

  // Project config is the fallback; paused sessions can override it without dirtying the graph.
  function getDebuggerConfig(nodeConfig?: Record<string, unknown>): Record<string, unknown> {
    return (nodeConfig?.debugger as Record<string, unknown>) || {}
  }
  function getEffectiveDebuggerConfig(
    nodeConfig?: Record<string, unknown>,
    nodeId?: string,
  ): Record<string, unknown> {
    if (nodeId && sessionDebuggerConfigs.value[nodeId]) {
      return sessionDebuggerConfigs.value[nodeId]
    }
    return getDebuggerConfig(nodeConfig)
  }
  function hasBreakpoint(nodeConfig?: Record<string, unknown>, nodeId?: string): boolean {
    return !!(getEffectiveDebuggerConfig(nodeConfig, nodeId).breakpoint as any)?.enabled
  }
  function hasRecordFrame(nodeConfig?: Record<string, unknown>, nodeId?: string): boolean {
    return !!(getEffectiveDebuggerConfig(nodeConfig, nodeId).record_frame as any)?.enabled
  }
  function toggleBreakpointConfig(nodeConfig: Record<string, unknown>): Record<string, unknown> {
    const dbg = { ...getDebuggerConfig(nodeConfig) }
    const bp = (dbg.breakpoint as any) || {}
    if (bp.enabled) {
      dbg.breakpoint = { ...bp, enabled: false }
    } else {
      dbg.breakpoint = { enabled: true, pause_timing: bp.pause_timing || 'before', hit_count: bp.hit_count ?? 0, once: bp.once ?? false }
    }
    return { ...nodeConfig, debugger: dbg }
  }
  function toggleRecordFrameConfig(nodeConfig: Record<string, unknown>): Record<string, unknown> {
    const dbg = { ...getDebuggerConfig(nodeConfig) }
    const rf = (dbg.record_frame as any) || {}
    dbg.record_frame = { ...rf, enabled: !rf.enabled }
    return { ...nodeConfig, debugger: dbg }
  }
  function setBreakpointPauseTiming(nodeConfig: Record<string, unknown>, timing: string): Record<string, unknown> {
    const dbg = { ...getDebuggerConfig(nodeConfig) }
    const bp = { ...(dbg.breakpoint || {}), pause_timing: timing, enabled: true }
    dbg.breakpoint = bp
    return { ...nodeConfig, debugger: dbg }
  }

  function isNonUserFacingDebugDiagnostic(candidate: any): boolean {
    return typeof candidate?.category === 'string'
      && candidate.category.endsWith('.completed')
      && candidate?.severity === 'info'
  }

  function extractDebugError(e: any, fallback = '请求失败'): string {
    const body = (e?.body as any) || {}
    const primary = body?.details?.primary_diagnostic
    const diagnosticLinks = Array.isArray(body?.diagnostic_links) ? body.diagnostic_links : []
    const nonUserFacingMessages = [primary, ...diagnosticLinks]
      .filter(isNonUserFacingDebugDiagnostic)
      .map((item: any) => item?.message)
      .filter((message: unknown): message is string => typeof message === 'string' && !!message)
    if (primary?.message && !isNonUserFacingDebugDiagnostic(primary)) {
      return primary.message
    }
    const message = typeof body?.message === 'string' ? body.message : ''
    if (message && !nonUserFacingMessages.includes(message)) {
      return message
    }
    const meaningfulLink = diagnosticLinks.find(
      (item: any) => item?.message && !isNonUserFacingDebugDiagnostic(item),
    )
    if (meaningfulLink?.message) {
      return meaningfulLink.message
    }
    return body?.error || e?.message || fallback
  }

  async function hydrateActiveArtifacts(
    sessionId: string,
    options: { preserveProjection?: boolean } = {},
  ) {
    const tasks: Promise<unknown>[] = [
      loadActiveSession(sessionId),
    ]
    if (!options.preserveProjection) {
      tasks.push(loadEvents(sessionId))
      tasks.push(loadProjection(sessionId, 'live'))
    }
    await Promise.all(tasks)
  }

  async function hydratePollingArtifacts(
    sessionId: string,
    pollingOwnerAtStart: string | null,
    options: { preserveProjection?: boolean } = {},
  ): Promise<boolean> {
    const detailPromise = fetchDebugSession(sessionId)
    const eventsPromise = options.preserveProjection ? null : fetchDebugEvents(sessionId)
    const projectionPromise = options.preserveProjection
      ? null
      : fetchDebugProjection(sessionId, 'live')
    const [detail, eventsPayload, projectionPayload] = await Promise.all([
      detailPromise,
      eventsPromise,
      projectionPromise,
    ])
    if (
      pollingSessionId.value !== pollingOwnerAtStart
      || (pollingOwnerAtStart !== null && pollingOwnerAtStart !== sessionId)
    ) return false

    setActiveSessionDetail(detail)
    useProjectDiagnosticsStore().ingestCatalog(activeSession.value?.diagnostic_links, {
      source: 'debug',
      operation: 'debug.session',
    })
    if (eventsPayload) {
      events.value = eventsPayload.events
      eventsTotal.value = eventsPayload.total_count
      eventsSessionId.value = eventsPayload.session_id
    }
    if (projectionPayload) {
      projection.value = projectionPayload.projection
      projectionVariableSnapshot.value = projectionPayload.variable_snapshot || null
      projectionRuntimePreview.value = projectionPayload.runtime_preview || null
    }
    return true
  }

  function clearActiveArtifacts() {
    activeSession.value = null
    sessionDebuggerConfigs.value = {}
    projection.value = null
    projectionVariableSnapshot.value = null
    projectionRuntimePreview.value = null
    events.value = []
    eventsTotal.value = 0
    eventsSessionId.value = null
  }

  function updateActiveSessionSummary(sessionId: string) {
    const status = getActiveDebugStatus()
    sessions.value = sessions.value.map((session) => (
      session.session_id === sessionId
        ? { ...session, status }
        : session
    ))
  }

  async function refreshSessions(
    preferredSessionId?: string,
    options: {
      preserveProjection?: boolean
      retainSessionId?: string
      suppressHydrate?: boolean
      suppressPollingRestart?: boolean
    } = {},
  ) {
    const [activePayload, historyPayload] = await Promise.all([
      fetchDebugSessions(),
      fetchDebugHistorySessions(),
    ])
    sessions.value = activePayload.sessions.map((session) => normalizeDebugSessionSummary(session))
    historySessions.value = historyPayload.sessions.map((session) => {
      if (session && typeof session === 'object') {
        return normalizeDebugSessionSummary(session as Record<string, unknown>)
      }
      return session
    })
    historySummary.value = {
      ...historyPayload.summary,
      debug_status_counts: normalizeHistorySummaryCounts(historyPayload.summary?.debug_status_counts),
    }

    const activeCandidates = sessions.value.filter((session) => isActiveDebugStatus(session.status))
    const preferredActive = preferredSessionId
      ? activeCandidates.find((session) => session.session_id === preferredSessionId)
      : null
    const currentPolling = pollingSessionId.value
      ? activeCandidates.find((session) => session.session_id === pollingSessionId.value)
      : null
    const currentActive = activeSession.value?.debug_session?.session_id
      ? activeCandidates.find((session) => session.session_id === activeSession.value?.debug_session?.session_id)
      : null
    const sessionToHydrate = preferredActive || currentPolling || currentActive || activeCandidates[0] || null

    if (sessionToHydrate) {
      if (!options.suppressHydrate) {
        await hydrateActiveArtifacts(sessionToHydrate.session_id, options)
      }
      if (!options.suppressPollingRestart) {
        startPolling(sessionToHydrate.session_id)
      }
      return
    }

    stopPolling()
    const currentSessionId = activeSession.value?.debug_session?.session_id
    if (
      options.retainSessionId
      && currentSessionId === options.retainSessionId
      && isTerminalDebugStatus(getActiveDebugStatus())
    ) {
      return
    }
    clearActiveArtifacts()
  }

  async function loadActiveSession(sessionId: string) {
    setActiveSessionDetail(await fetchDebugSession(sessionId))
    useProjectDiagnosticsStore().ingestCatalog(activeSession.value?.diagnostic_links, {
      source: 'debug',
      operation: 'debug.session',
    })
  }

  async function loadHistorySession(sessionId: string) {
    activeHistorySession.value = await fetchDebugHistorySession(sessionId)
  }

  async function loadProjection(sessionId: string, mode: 'live' | 'history', eventIndex?: number) {
    const r: DebugProjectionResponse = eventIndex == null
      ? await fetchDebugProjection(sessionId, mode)
      : await fetchDebugProjection(sessionId, mode, eventIndex)
    projection.value = r.projection
    projectionVariableSnapshot.value = r.variable_snapshot || null
    projectionRuntimePreview.value = r.runtime_preview || null
  }

  function clearProjection() {
    projection.value = null
    projectionVariableSnapshot.value = null
    projectionRuntimePreview.value = null
  }

  async function loadEvents(sessionId: string) {
    const r: DebugEventsResponse = await fetchDebugEvents(sessionId)
    events.value = r.events
    eventsTotal.value = r.total_count
    eventsSessionId.value = r.session_id
  }

  async function doContinue(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugContinue(sessionId)
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function doStepOver(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugStepOver(sessionId)
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function doStepInto(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugStepInto(sessionId)
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function doStepOut(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugStepOut(sessionId)
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function doPause(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugPause(sessionId, { reason: 'manual_pause' })
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function doAbort(sessionId: string): Promise<DebugSessionDocument | null> {
    controlLoading.value = true
    try {
      const r: DebugControlResponse = await postDebugAbort(sessionId, { reason: 'user_abort' })
      return normalizeDebugSessionDocument(r.debug_session)
    } finally { controlLoading.value = false }
  }

  async function applyVariables(sessionId: string, updates: Record<string, unknown>, applyMode: 'staged' | 'immediate' = 'staged') {
    const body: DebugVariablesApplyRequest = { updates, apply_mode: applyMode }
    const r = await postDebugVariablesApply(sessionId, body)
    return normalizeDebugSessionDocument(r.debug_session)
  }

  async function applyNodeDebuggerConfig(nodeId: string, debuggerConfig: Record<string, unknown>) {
    const sessionId = activeSession.value?.debug_session?.session_id
    if (!sessionId || getActiveDebugStatus() !== 'paused') {
      throw new Error('仅可在暂停中的 Debug 会话更新临时断点或记录点')
    }
    const response = normalizeDebugDetail(
      await postDebugNodeDebuggerApply(sessionId, nodeId, debuggerConfig),
    )
    setActiveSessionDetail(response)
    sessionDebuggerConfigs.value = {
      ...sessionDebuggerConfigs.value,
      [nodeId]: { ...(response?.debugger || debuggerConfig) },
    }
    return response
  }

  // --- Unified entry points (Scheme A) ---

  type DebugStartResult = { phase: 'started' | 'started_with_sync_warning' | 'failed'; sessionId?: string; startError?: string; syncError?: string }

  async function prepareDebugSession(graphBody?: Record<string, unknown>): Promise<{ phase: 'ready' | 'failed'; error?: string }> {
    try {
      const r = await postDebugPrepare(graphBody)
      if (r.status === 'ready') {
        return { phase: 'ready' }
      }
      return { phase: 'failed', error: r.status }
    } catch (e: any) {
      useProjectDiagnosticsStore().ingestApiError(e, { source: 'debug', operation: 'debug.prepare' })
      return { phase: 'failed', error: extractDebugError(e) }
    }
  }

  async function startDebugSession(graphBody?: Record<string, unknown>): Promise<DebugStartResult> {
    try {
      const r = await postDebugStart(graphBody)
      if (!r.debug_session?.session_id) return { phase: 'failed', startError: '无会话 ID' }
      const sid = r.debug_session.session_id
      try {
        await refreshSessions(sid)
        return { phase: 'started', sessionId: sid }
      } catch (e: any) {
        return { phase: 'started_with_sync_warning', sessionId: sid, syncError: extractDebugError(e, '同步失败') }
      }
    } catch (e: any) {
      useProjectDiagnosticsStore().ingestApiError(e, { source: 'debug', operation: 'debug.start' })
      return { phase: 'failed', startError: extractDebugError(e, '启动失败') }
    }
  }

  // --- Polling ---
  let pollingTimer: ReturnType<typeof setTimeout> | null = null
  const pollingSessionId = ref<string | null>(null)
  const inFlightPolls = new Map<string, Promise<void>>()

  function scheduleNextPoll(sessionId: string) {
    if (pollingSessionId.value !== sessionId || pollingTimer || inFlightPolls.has(sessionId)) {
      return
    }
    pollingTimer = setTimeout(async () => {
      pollingTimer = null
      try {
        await pollOnce(sessionId)
      } catch {
        // pollOnce already ingests diagnostics and reconciles polling state.
      }
    }, 400)
  }

  function startPolling(sessionId: string) {
    if (pollingSessionId.value === sessionId && (pollingTimer || inFlightPolls.has(sessionId))) {
      return
    }
    if (pollingSessionId.value !== sessionId) {
      stopPolling()
    }
    pollingSessionId.value = sessionId
    scheduleNextPoll(sessionId)
  }

  function stopPolling(sessionId?: string) {
    if (sessionId && pollingSessionId.value !== sessionId) return
    if (pollingTimer) { clearTimeout(pollingTimer); pollingTimer = null }
    pollingSessionId.value = null
  }

  function pollOnce(sessionId: string, options: { throwOnError?: boolean } = {}) {
    const existing = inFlightPolls.get(sessionId)
    if (existing) {
      return existing
    }

    const task = (async () => {
      const pollingOwnerAtStart = pollingSessionId.value
      try {
        const preserveProjection = projection.value?.mode === 'history'
        const isCurrentSession = await hydratePollingArtifacts(
          sessionId,
          pollingOwnerAtStart,
          { preserveProjection },
        )
        if (!isCurrentSession) return
        const st = getActiveDebugStatus()
        if (isTerminalDebugStatus(st)) {
          stopPolling(sessionId)
          await refreshSessions(sessionId, {
            retainSessionId: sessionId,
            suppressHydrate: true,
            suppressPollingRestart: true,
          })
          return
        }
        updateActiveSessionSummary(sessionId)
      } catch (error) {
        useProjectDiagnosticsStore().ingestApiError(error, { source: 'debug', operation: 'debug.poll' })
        const stillOwnsPolling = pollingSessionId.value === pollingOwnerAtStart
          && (pollingOwnerAtStart === null || pollingOwnerAtStart === sessionId)
        if (!stillOwnsPolling) return
        if (pollingOwnerAtStart === null) stopPolling()
        else stopPolling(sessionId)
        await refreshSessions().catch(() => {})
        if (!sessions.value.some(s => s.session_id === sessionId)) {
          clearActiveArtifacts()
        }
        if (options.throwOnError) throw error
      } finally {
        inFlightPolls.delete(sessionId)
        if (pollingSessionId.value === sessionId) {
          scheduleNextPoll(sessionId)
        }
      }
    })()

    inFlightPolls.set(sessionId, task)
    return task
  }

  return {
    sessions,
    historySessions,
    historySummary,
    activeSession,
    activeHistorySession,
    projection,
    projectionVariableSnapshot,
    projectionRuntimePreview,
    events,
    eventsTotal,
    eventsSessionId,
    controlLoading,
    isDebugActive,
    getDebuggerConfig,
    getEffectiveDebuggerConfig,
    hasBreakpoint,
    hasRecordFrame,
    toggleBreakpointConfig,
    setBreakpointPauseTiming,
    toggleRecordFrameConfig,
    refreshSessions,
    loadActiveSession,
    loadHistorySession,
    loadProjection,
    clearProjection,
    loadEvents,
    doContinue,
    doStepOver,
    doStepInto,
    doStepOut,
    doPause,
    doAbort,
    applyVariables,
    applyNodeDebuggerConfig,
    prepareDebugSession,
    startDebugSession,
    pollingSessionId,
    startPolling,
    stopPolling,
    pollOnce,
  }
})
