/** WeConduct — Font Scale Store
 *  Applies a uniform UI font-size multiplier via the --font-scale CSS variable
 *  (consumed by the --text-* tokens in tokens.css).
 *  - `scale` is the multiplier (e.g. 1.0 = 100%, 1.25 = 125%).
 *  - Persisted locally; the config default (program_settings.font_scale) seeds
 *    it on boot ONLY when the user has no explicit local override.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'weconduct-font-scale'
const MIN_SCALE = 0.5
const MAX_SCALE = 2.0
const DEFAULT_SCALE = 1.0

function clampScale(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SCALE
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

function getStoredScale(): number | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === null) return null
    const parsed = Number.parseFloat(stored)
    return Number.isFinite(parsed) ? clampScale(parsed) : null
  } catch { /* localStorage unavailable */ }
  return null
}

function applyScale(scale: number) {
  if (typeof document === 'undefined') return
  document.documentElement.style.setProperty('--font-scale', String(scale))
}

export const useFontScaleStore = defineStore('fontScale', () => {
  const scale = ref<number>(getStoredScale() ?? DEFAULT_SCALE)

  applyScale(scale.value)

  function persist(value: number) {
    try { localStorage.setItem(STORAGE_KEY, String(value)) } catch { /* ignore */ }
  }

  /** Set an explicit user scale (persisted as a local override). */
  function setScale(value: number) {
    const next = clampScale(value)
    scale.value = next
    applyScale(next)
    persist(next)
  }

  /**
   * Seed from the config default (program_settings.font_scale). No-op when the
   * user already has a local override, so an explicit choice always wins.
   */
  function initFromConfig(configScale: number | null | undefined) {
    if (getStoredScale() !== null) return
    if (typeof configScale === 'number' && Number.isFinite(configScale)) {
      const next = clampScale(configScale)
      scale.value = next
      applyScale(next)
    }
  }

  // Reactive safety net (covers any programmatic scale mutation).
  watch(scale, (s) => applyScale(s))

  return { scale, setScale, initFromConfig }
})
