import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  fetchUpdateStatus: vi.fn(),
  postUpdateCheck: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  fetchUpdateStatus: apiMocks.fetchUpdateStatus,
  postUpdateCheck: apiMocks.postUpdateCheck,
}))

import { fetchUpdateStatus, postUpdateCheck } from '@/services/api'
import { useUpdateStore } from './updateStore'

describe('updateStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads idle status from backend', async () => {
    vi.mocked(fetchUpdateStatus).mockResolvedValue({
      source: 'github_releases',
      repository: 'HalcyonAlcedo/WeConduct',
      current_version: '0.7.1',
      latest_version: null,
      update_available: false,
      release_name: null,
      release_url: 'https://github.com/HalcyonAlcedo/WeConduct/releases',
      published_at: null,
      release_notes_excerpt: null,
      last_checked_at: null,
      check_status: 'idle',
      check_error: null,
    })

    const store = useUpdateStore()
    await store.fetchStatus()

    expect(store.status?.current_version).toBe('0.7.1')
    expect(store.status?.check_status).toBe('idle')
  })

  it('runs forced check and stores update result', async () => {
    vi.mocked(postUpdateCheck).mockResolvedValue({
      source: 'github_releases',
      repository: 'HalcyonAlcedo/WeConduct',
      current_version: '0.7.1',
      latest_version: '0.7.2',
      update_available: true,
      release_name: '0.7.2',
      release_url: 'https://github.com/HalcyonAlcedo/WeConduct/releases/tag/v0.7.2',
      published_at: '2026-06-28T10:00:00Z',
      release_notes_excerpt: 'Body',
      last_checked_at: '2026-06-28T11:00:00Z',
      check_status: 'ok',
      check_error: null,
    })

    const store = useUpdateStore()
    await store.checkForUpdates(true)

    expect(postUpdateCheck).toHaveBeenCalledWith({ force: true })
    expect(store.status?.latest_version).toBe('0.7.2')
    expect(store.status?.update_available).toBe(true)
  })
})
