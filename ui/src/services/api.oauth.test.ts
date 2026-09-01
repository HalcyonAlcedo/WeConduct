import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchOAuthFlow,
  postOAuthAuthorization,
  postOAuthDevice,
  postOAuthFlowCancel,
  postOAuthFlowSubmit,
} from './api'

describe('interactive OAuth api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ flow_id: 'flow-1', status: 'waiting_input' }),
    }))
  })

  it('starts authorization code flow through the internal workbench route', async () => {
    await postOAuthAuthorization({
      authorization_url: 'https://example.test/authorize',
      token_url: 'https://example.test/token',
      client_id: 'client',
      redirect_uri: 'http://127.0.0.1/callback',
      scope_id: 'session-1',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/oauth/authorization',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('uses the flow id path for read, submit and cancel', async () => {
    await fetchOAuthFlow('flow-1')
    await postOAuthFlowSubmit('flow-1', { values: { code: 'callback' } })
    await postOAuthFlowCancel('flow-1')

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      '/api/workbench/oauth/flow-1',
      expect.anything(),
    )
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      '/api/workbench/oauth/flow-1/submit',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      '/api/workbench/oauth/flow-1/cancel',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('starts device code flow through the internal workbench route', async () => {
    await postOAuthDevice({
      device_authorization_url: 'https://example.test/device',
      token_url: 'https://example.test/token',
      client_id: 'client',
      scope_id: 'session-1',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/oauth/device',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
