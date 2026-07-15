import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const api = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    body: unknown
    constructor(status: number, body: unknown) {
      super(typeof body === 'object' && body && 'message' in (body as any) ? String((body as any).message) : `HTTP ${status}`)
      this.name = 'ApiError'
      this.status = status
      this.body = body
    }
  }
  return {
    fetchStartupDiagnostics: vi.fn(),
    postStartupRecover: vi.fn(),
    FakeApiError,
  }
})

const FakeApiError = api.FakeApiError

vi.mock('@/services/api', () => ({
  fetchStartupDiagnostics: api.fetchStartupDiagnostics,
  postStartupRecover: api.postStartupRecover,
  ApiError: api.FakeApiError,
}))

import { useStartupStore } from './startupStore'

function faultReport() {
  return {
    generated_at: '2026-07-15T00:00:00Z',
    overall_severity: 'fault',
    recoverable_targets: ['workspace_state', 'preferences'],
    subsystems: [
      {
        subsystem: 'workspace_state',
        label: '工作区状态',
        location: 'C:/x/workspace-state.json',
        status: 'invalid',
        severity: 'fault',
        error_code: 'workspace_state_invalid',
        message: 'workspace state missing required key: security_settings',
        recoverable: true,
        recovery_target: 'workspace_state',
      },
    ],
  }
}

describe('startupStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('classifies a fault report from the backend and exposes recovery affordances', async () => {
    api.fetchStartupDiagnostics.mockResolvedValue(faultReport())
    const store = useStartupStore()

    await store.diagnose(new FakeApiError(500, { error: 'workspace_state_invalid', message: 'boom' }))

    expect(store.phase).toBe('blocked')
    expect(store.severity).toBe('fault')
    expect(store.hasBlockingError).toBe(true)
    expect(store.canRecover).toBe(true)
    expect(store.canForceStart).toBe(false)
    expect(store.problemSubsystems).toHaveLength(1)
    expect(store.triggerError?.code).toBe('workspace_state_invalid')
  })

  it('falls back to a critical classification when the diagnostics endpoint is unreachable', async () => {
    api.fetchStartupDiagnostics.mockRejectedValue(new Error('Failed to fetch'))
    const store = useStartupStore()

    await store.diagnose(new Error('Failed to fetch'))

    expect(store.severity).toBe('critical')
    expect(store.canRecover).toBe(false)
    expect(store.canForceStart).toBe(false)
    expect(store.subsystems[0].subsystem).toBe('backend')
  })

  it('escalates an all-ok probe to critical since startup still failed', async () => {
    api.fetchStartupDiagnostics.mockResolvedValue({
      generated_at: '2026-07-15T00:00:00Z',
      overall_severity: 'ok',
      recoverable_targets: [],
      subsystems: [],
    })
    const store = useStartupStore()

    await store.diagnose(new Error('snapshot failed'))

    expect(store.severity).toBe('critical')
    expect(store.subsystems[0].subsystem).toBe('backend')
  })

  it('treats an anomaly-only report as force-startable', async () => {
    api.fetchStartupDiagnostics.mockResolvedValue({
      generated_at: '2026-07-15T00:00:00Z',
      overall_severity: 'anomaly',
      recoverable_targets: ['graph_preferences'],
      subsystems: [
        {
          subsystem: 'graph_preferences',
          label: '图编辑器配置',
          location: 'C:/x/graph-preferences.json',
          status: 'invalid_json',
          severity: 'anomaly',
          error_code: 'graph_preferences_invalid_json',
          message: 'bad json',
          recoverable: true,
          recovery_target: 'graph_preferences',
        },
      ],
    })
    const store = useStartupStore()

    await store.diagnose(new Error('init failed'))

    expect(store.severity).toBe('anomaly')
    expect(store.canForceStart).toBe(true)
  })

  it('recover() calls the backend and returns success', async () => {
    api.fetchStartupDiagnostics.mockResolvedValue(faultReport())
    api.postStartupRecover.mockResolvedValue({
      status: 'recovered',
      results: [
        { target: 'workspace_state', status: 'reset', location: 'C:/x/workspace-state.json', backup_path: 'C:/x/ws.bak', message: 'ok' },
      ],
    })
    const store = useStartupStore()
    await store.diagnose()

    const ok = await store.recover()

    expect(ok).toBe(true)
    expect(store.phase).toBe('recovered')
    expect(store.recoverResults).toHaveLength(1)
  })

  it('recover() surfaces an error and stays blocked on failure', async () => {
    api.fetchStartupDiagnostics.mockResolvedValue(faultReport())
    api.postStartupRecover.mockRejectedValue(new FakeApiError(500, { message: 'reset failed' }))
    const store = useStartupStore()
    await store.diagnose()

    const ok = await store.recover()

    expect(ok).toBe(false)
    expect(store.phase).toBe('blocked')
    expect(store.recoverError).toBe('reset failed')
  })
})
