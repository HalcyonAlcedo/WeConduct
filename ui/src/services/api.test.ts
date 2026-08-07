import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  fetchConfigValues,
  fetchExternalApiPreferences,
  patchConfigValues,
  postExternalApiPreferences,
  resetConfigValues,
  postPreferences,
} from './api'

describe('ApiError', () => {
  it('prioritizes body.message over body.error', () => {
    const err = new ApiError(400, { message: 'primary message', error: 'fallback' })
    expect(err.message).toBe('primary message')
  })

  it('falls back to body.error when no message', () => {
    const err = new ApiError(500, { error: 'internal_server_error' })
    expect(err.message).toBe('internal_server_error')
  })

  it('falls back to HTTP status when neither present', () => {
    const err = new ApiError(404, {})
    expect(err.message).toBe('HTTP 404')
  })

  it('handles non-object body', () => {
    const err = new ApiError(502, 'Bad Gateway')
    expect(err.message).toBe('HTTP 502')
  })

  it('preserves status and body', () => {
    const body = { message: 'not found', path: '/api/unknown' }
    const err = new ApiError(404, body)
    expect(err.status).toBe(404)
    expect(err.body).toBe(body)
  })
})

describe('configuration API', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetchConfigValues 请求统一配置 GET scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'project', values: { identity: { name: 'demo-project' } } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchConfigValues('project')

    expect(fetchMock).toHaveBeenCalledWith('/api/workbench/config/values?scope=project', {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result).toEqual({
      scope: 'project',
      values: { identity: { name: 'demo-project' } },
    })
  })

  it('patchConfigValues 发送统一配置 PATCH body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'graph', values: { entrypoint_runtime: { initial_variables: {}, browser_config: { headless: true } } } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const body = {
      scope: 'graph' as const,
      operations: [
        {
          op: 'replace' as const,
          path: '/entrypoint_runtime/initial_variables',
          value: {},
        },
        {
          op: 'replace' as const,
          path: '/entrypoint_runtime/browser_config',
          value: { headless: true },
        },
      ],
      confirm_high_risk: false,
    }

    const result = await patchConfigValues(body)

    expect(fetchMock).toHaveBeenCalledWith('/api/workbench/config/values', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    expect(result).toEqual({
      scope: 'graph',
      values: { entrypoint_runtime: { initial_variables: {}, browser_config: { headless: true } } },
    })
  })

  it('postPreferences 将 program_settings 的 ui 域字段映射为配置操作（含 language/theme/font_scale）', async () => {
    // Regression: `language`, `theme`, `font_scale` were missing from the
    // field→domain map, so their PATCH ops were silently dropped and the value
    // never persisted (the UI select reverted to the stored zh-CN default).
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'program', values: { ui: {}, workspace: {}, updates: {} } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await postPreferences({
      section: 'program_settings',
      values: { language: 'en-US', resource_language: 'en-US', theme: 'dark', font_scale: 1.25 },
    } as any)

    const sentBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    const paths = sentBody.operations.map((o: any) => o.path).sort()
    expect(paths).toEqual(['/ui/font_scale', '/ui/language', '/ui/resource_language', '/ui/theme'])
    const langOp = sentBody.operations.find((o: any) => o.path === '/ui/language')
    expect(langOp).toMatchObject({ op: 'replace', value: 'en-US' })
  })

  it('resetConfigValues 重置指定配置作用域', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: 'graph', values: { editor_preferences: {} } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await resetConfigValues('graph')

    expect(fetchMock).toHaveBeenCalledWith('/api/workbench/config/reset', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({ scope: 'graph' }),
    })
  })
})

describe('startup diagnostics API', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.replaceState(window.history.state, document.title, window.location.pathname)
  })

  it('fetchStartupDiagnostics 携带桌面 UI 会话 Token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ overall_severity: 'ok' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    window.location.hash = '#weconduct_token=startup-ui-token'
    vi.resetModules()

    const { fetchStartupDiagnostics } = await import('./api')
    await fetchStartupDiagnostics()

    expect(fetchMock).toHaveBeenCalledWith('/api/startup/diagnostics', {
      headers: {
        'Content-Type': 'application/json',
        'X-WeConduct-Token': 'startup-ui-token',
      },
    })
  })
})

describe('external API preferences', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('专用 GET 保留可见 Token 字段', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        token: 'visible-external-token',
        token_configured: true,
        external_api_port: 2233,
        project_allowed_roots: ['C:\\projects'],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchExternalApiPreferences()

    expect(fetchMock).toHaveBeenCalledWith('/api/workbench/preferences/external-api', {
      headers: { 'Content-Type': 'application/json' },
    })
    expect(result.token).toBe('visible-external-token')
  })

  it('专用 POST 发送修改并保留返回的 Token 字段', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        token: 'updated-external-token',
        token_configured: true,
        external_api_port: 2233,
        project_allowed_roots: [],
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await postExternalApiPreferences({
      enabled: true,
      token: 'updated-external-token',
      clear_token: false,
      external_api_port: 2233,
      project_allowed_roots: [],
      confirm_high_risk: true,
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/workbench/preferences/external-api', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({
        enabled: true,
        token: 'updated-external-token',
        clear_token: false,
        external_api_port: 2233,
        project_allowed_roots: [],
        confirm_high_risk: true,
      }),
    })
    expect(result.token).toBe('updated-external-token')
  })
})
