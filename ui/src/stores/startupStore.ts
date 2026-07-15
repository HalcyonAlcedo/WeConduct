/** WeConduct — Startup Store
 *  Drives the dedicated startup-error experience. When workspace initialization
 *  fails, this store fetches structured diagnostics from the backend and derives
 *  an overall severity (严重 / 故障 / 异常). If the backend is fully unreachable,
 *  it falls back to a client-side "critical" classification so the user still
 *  gets an actionable screen instead of a blank window.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchStartupDiagnostics, postStartupRecover, ApiError } from '@/services/api'
import type {
  StartupDiagnosticsResponse,
  StartupSeverity,
  StartupSubsystemDiagnostic,
  StartupRecoverResult,
} from '@/types/domains/api'

export type StartupPhase = 'idle' | 'diagnosing' | 'blocked' | 'recovering' | 'recovered'

export const useStartupStore = defineStore('startup', () => {
  // --- State ---
  const phase = ref<StartupPhase>('idle')
  const report = ref<StartupDiagnosticsResponse | null>(null)
  /** The raw error that triggered diagnosis (used for the critical fallback). */
  const triggerError = ref<{ message: string; status: number | null; code: string | null } | null>(null)
  const recoverResults = ref<StartupRecoverResult[]>([])
  const recoverError = ref<string | null>(null)

  // --- Getters ---
  const severity = computed<StartupSeverity>(() => report.value?.overall_severity ?? 'ok')
  const hasBlockingError = computed(() => phase.value === 'blocked')
  const subsystems = computed<StartupSubsystemDiagnostic[]>(() => report.value?.subsystems ?? [])
  const problemSubsystems = computed(() =>
    subsystems.value.filter(s => s.severity !== 'ok'),
  )
  const recoverableTargets = computed<string[]>(() => report.value?.recoverable_targets ?? [])
  const canRecover = computed(() => recoverableTargets.value.length > 0)
  /** 异常 can be dismissed to force-start; critical cannot. */
  const canForceStart = computed(() => severity.value === 'anomaly')

  function extractErrorInfo(err: unknown) {
    if (err instanceof ApiError) {
      const body = (err.body && typeof err.body === 'object' ? err.body : {}) as Record<string, unknown>
      return {
        message: err.message,
        status: err.status,
        code: typeof body.error === 'string' ? body.error : null,
      }
    }
    return {
      message: err instanceof Error ? err.message : String(err ?? '未知错误'),
      status: null,
      code: null,
    }
  }

  /**
   * Build a client-side "critical" report used when the backend cannot even be
   * reached (transport error) — the diagnostics endpoint itself is unavailable.
   */
  function buildCriticalFallback(): StartupDiagnosticsResponse {
    const info = triggerError.value
    return {
      generated_at: new Date().toISOString(),
      overall_severity: 'critical',
      recoverable_targets: [],
      subsystems: [
        {
          subsystem: 'backend',
          label: '后端服务',
          location: window.location.origin || 'http://127.0.0.1',
          status: 'unreachable',
          severity: 'critical',
          error_code: info?.code ?? 'backend_unreachable',
          message: info?.message
            ? `无法连接后端服务：${info.message}`
            : '无法连接后端服务，程序无法启动',
          recoverable: false,
          recovery_target: 'backend',
        },
      ],
    }
  }

  /**
   * Diagnose why startup failed. Called by App.vue after workspace.initialize()
   * throws. Backend-first: fetch structured diagnostics; on transport failure,
   * fall back to a critical classification.
   */
  async function diagnose(err?: unknown): Promise<void> {
    if (err !== undefined) triggerError.value = extractErrorInfo(err)
    phase.value = 'diagnosing'
    recoverError.value = null
    try {
      const data = await fetchStartupDiagnostics()
      // We only reach diagnose() because startup failed. If every probed file is
      // healthy, the failure lies elsewhere (backend/unknown) — escalate to
      // critical and surface the trigger error rather than showing "正常".
      if (data.overall_severity === 'ok') {
        report.value = {
          ...data,
          overall_severity: 'critical',
          subsystems: [buildCriticalFallback().subsystems[0], ...data.subsystems],
        }
      } else {
        report.value = data
      }
    } catch (fetchErr) {
      // Diagnostics endpoint unreachable → backend is truly down.
      if (err === undefined) triggerError.value = extractErrorInfo(fetchErr)
      report.value = buildCriticalFallback()
    }
    phase.value = 'blocked'
  }

  /**
   * Recover the given targets (or all recoverable targets) by asking the backend
   * to back up and reset the corrupt files. Returns true on success.
   */
  async function recover(targets?: string[]): Promise<boolean> {
    phase.value = 'recovering'
    recoverError.value = null
    try {
      const result = await postStartupRecover(targets)
      recoverResults.value = result.results
      phase.value = 'recovered'
      return true
    } catch (err) {
      recoverError.value = extractErrorInfo(err).message
      phase.value = 'blocked'
      return false
    }
  }

  function reset() {
    phase.value = 'idle'
    report.value = null
    triggerError.value = null
    recoverResults.value = []
    recoverError.value = null
  }

  return {
    phase,
    report,
    triggerError,
    recoverResults,
    recoverError,
    severity,
    hasBlockingError,
    subsystems,
    problemSubsystems,
    recoverableTargets,
    canRecover,
    canForceStart,
    diagnose,
    recover,
    reset,
  }
})
