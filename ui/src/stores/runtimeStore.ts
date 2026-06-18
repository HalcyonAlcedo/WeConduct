/** WeConduct — Shared Runtime/Debug Session Store
 *  Bridges TaskExecutionPanel, RuntimeTab, DebugTab so output tabs
 *  automatically reflect latest sessions from the task execution panel.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchRuntimeSessions, fetchRuntimeSession, fetchDebugSessions, fetchDebugSession, postRuntimeStart, postRuntimeRun } from '@/services/api'
import type { RuntimeSessionSummary, RuntimeSessionDetailResponse, DebugSessionSummary, DebugSessionDetailResponse } from '@/types/domains/api'

export const useRuntimeStore = defineStore('runtime', () => {
  const rtSessions = ref<RuntimeSessionSummary[]>([])
  const dbSessions = ref<DebugSessionSummary[]>([])
  const activeRt = ref<RuntimeSessionDetailResponse | null>(null)
  const activeDb = ref<DebugSessionDetailResponse | null>(null)

  async function refreshAll() {
    try { const r = await fetchRuntimeSessions(); rtSessions.value = r.sessions } catch {}
    try { const r = await fetchDebugSessions(); dbSessions.value = r.sessions } catch {}
  }
  async function loadRtDetail(id: string) { try { activeRt.value = await fetchRuntimeSession(id) } catch {} }
  async function loadDbDetail(id: string) { try { activeDb.value = await fetchDebugSession(id) } catch {} }
  function setActiveRt(detail: RuntimeSessionDetailResponse) { activeRt.value = detail }
  function setActiveDb(detail: DebugSessionDetailResponse) { activeDb.value = detail }

  /** One-click start + run: prepare, start session, run, return result.
   *  When project is loaded and graph is clean, uses saved graph (no payload).
   *  Only passes graph_document for unsaved/dirty in-memory graphs. */
  async function startAndRun(graphDocument?: Record<string, unknown>, isDirty?: boolean): Promise<{ success: boolean; message: string }> {
    try {
      const body = (graphDocument && isDirty) ? { graph_document: graphDocument } : undefined
      const r = await postRuntimeStart(body)
      if (!r.runtime_session.session_id) {
        setActiveRt(r)
        return { success: false, message: '无会话 ID' }
      }
      setActiveRt(r)
      await refreshAll()
      const runResult = await postRuntimeRun(r.runtime_session.session_id)
      setActiveRt(runResult)
      await refreshAll()
      const failCount = runResult.node_states?.filter((n: any) => n.node_status === 'failed').length || 0
      return {
        success: failCount === 0,
        message: failCount ? `${failCount} 节点失败` : `${runResult.node_states?.length || 0} 节点完成`,
      }
    } catch (e: any) {
      if (e?.body) setActiveRt(e.body as any)
      return { success: false, message: e?.body?.details?.primary_diagnostic?.message || e?.body?.message || e?.body?.error || e?.message || '运行失败' }
    }
  }

  return { rtSessions, dbSessions, activeRt, activeDb, refreshAll, loadRtDetail, loadDbDetail, setActiveRt, setActiveDb, startAndRun }
})
