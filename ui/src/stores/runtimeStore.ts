/** WeConduct — Shared Runtime/Debug Session Store
 *  Bridges TaskExecutionPanel, RuntimeTab, DebugTab so output tabs
 *  automatically reflect latest sessions from the task execution panel.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
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
    runtimeProgress.value = buildRuntimeProgressFromSession(detail)
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
  ): Promise<{ success: boolean; message: string }> {
    try {
      const body = (graphDocument && isDirty) ? { graph_document: graphDocument } : undefined
      const r = await postRuntimeStart(body)
      if (!r.runtime_session.session_id) {
        setActiveRt(r)
        return { success: false, message: '无会话 ID' }
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
  }
})
