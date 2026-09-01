import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchDebugHistorySessionNetwork,
  fetchDebugHistorySessionNetworkSummary,
  fetchDebugSessionNetworkTraceBody,
} from './api'

describe('debug network api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ summary: { total_operations: 0 }, traces: [] }),
    }))
  })

  it('history network list 请求使用 /api/workbench/debug/history/{id}/network', async () => {
    await fetchDebugHistorySessionNetwork('dbg-history-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/debug/history/dbg-history-1/network',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('history network summary 请求使用 /api/workbench/debug/history/{id}/network/summary', async () => {
    await fetchDebugHistorySessionNetworkSummary('dbg-history-1')

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/debug/history/dbg-history-1/network/summary',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('正文请求可按 part 只读取请求体', async () => {
    await fetchDebugSessionNetworkTraceBody('dbg-1', 'trace-1', 'request')

    expect(fetch).toHaveBeenCalledWith(
      '/api/workbench/debug/dbg-1/network/trace-1/body?part=request',
      expect.objectContaining({
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
})
