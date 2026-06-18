/** WeConduct — Theme Store
 *  Manages light/dark theme with localStorage persistence and system preference detection.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'weconduct-theme'

function getSystemPreference(): ThemeMode {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getStoredTheme(): ThemeMode | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch { /* localStorage unavailable */ }
  return null
}

function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', mode)
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(getStoredTheme() ?? getSystemPreference())

  // Apply on init
  applyTheme(mode.value)

  // Listen for system preference changes
  if (typeof window !== 'undefined') {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (getStoredTheme() === null) {
        mode.value = e.matches ? 'dark' : 'light'
      }
    })
  }

  function toggle() {
    mode.value = mode.value === 'light' ? 'dark' : 'light'
    try {
      localStorage.setItem(STORAGE_KEY, mode.value)
    } catch { /* ignore */ }
  }

  function setTheme(m: ThemeMode) {
    mode.value = m
    try {
      localStorage.setItem(STORAGE_KEY, m)
    } catch { /* ignore */ }
  }

  // Reactive application of theme
  watch(mode, (m) => applyTheme(m), { immediate: true })

  return { mode, toggle, setTheme }
})
