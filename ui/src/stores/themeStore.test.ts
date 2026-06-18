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
    store.setTheme('dark')
    expect(localStorage.getItem('weconduct-theme')).toBe('dark')
    store.setTheme('light')
    expect(localStorage.getItem('weconduct-theme')).toBe('light')
  })
})
