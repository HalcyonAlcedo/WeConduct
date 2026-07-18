import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFontScaleStore } from './fontScaleStore'

describe('fontScaleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.documentElement.style.removeProperty('--font-scale')
  })

  it('defaults to 1.0 and applies the --font-scale variable', () => {
    const store = useFontScaleStore()
    expect(store.scale).toBe(1.0)
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1')
  })

  it('persists an explicit scale and applies it live', () => {
    const store = useFontScaleStore()
    store.setScale(1.25)
    expect(store.scale).toBe(1.25)
    expect(localStorage.getItem('weconduct-font-scale')).toBe('1.25')
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1.25')
  })

  it('clamps out-of-range values', () => {
    const store = useFontScaleStore()
    store.setScale(99)
    expect(store.scale).toBe(2.0)
    store.setScale(0.01)
    expect(store.scale).toBe(0.5)
  })

  it('seeds from config only without a local override', () => {
    const store = useFontScaleStore()
    store.initFromConfig(1.5)
    expect(store.scale).toBe(1.5)
    // Explicit user choice becomes a local override.
    store.setScale(1.0)
    store.initFromConfig(1.5)
    expect(store.scale).toBe(1.0)
  })
})
