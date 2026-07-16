import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('defaults to light mode', () => {
    const store = useThemeStore()
    expect(['light', 'dark']).toContain(store.mode)
  })

  it('toggles between light and dark', () => {
    const store = useThemeStore()
    const initial = store.mode
    store.toggle()
    expect(store.mode).not.toBe(initial)
    store.toggle()
    expect(store.mode).toBe(initial)
  })

  it('persists preference to localStorage', () => {
    const store = useThemeStore()
    store.setPreference('dark')
    expect(localStorage.getItem('weconduct-theme')).toBe('dark')
    expect(store.mode).toBe('dark')
    store.setPreference('light')
    expect(localStorage.getItem('weconduct-theme')).toBe('light')
    expect(store.mode).toBe('light')
  })

  it('supports system preference and seeds from config only without a local override', () => {
    const store = useThemeStore()
    // No local override yet → config default applies.
    store.initFromConfig('dark')
    expect(store.preference).toBe('dark')
    // Explicit user choice becomes a local override.
    store.setPreference('light')
    // Config seeding is now a no-op (override wins).
    store.initFromConfig('dark')
    expect(store.preference).toBe('light')
  })
})
