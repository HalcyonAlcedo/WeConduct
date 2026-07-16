/** WeConduct — Theme Store
 *  Manages theme preference (light/dark/system) with localStorage persistence.
 *  - `preference` is the user's chosen setting: 'light' | 'dark' | 'system'.
 *  - `mode` is the resolved applied theme: 'light' | 'dark'.
 *  When preference is 'system', mode follows the OS and updates live.
 *  The config default (program_settings.theme) seeds preference on boot ONLY
 *  when the user has no explicit local override.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'
export type ThemePreference = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'weconduct-theme'

function getSystemPreference(): ThemeMode {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getStoredPreference(): ThemePreference | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch { /* localStorage unavailable */ }
  return null
}

function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', mode)
}

function resolveMode(preference: ThemePreference): ThemeMode {
  return preference === 'system' ? getSystemPreference() : preference
}

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(getStoredPreference() ?? 'system')
  const mode = ref<ThemeMode>(resolveMode(preference.value))

  applyTheme(mode.value)

  // Follow OS changes while preference is 'system'.
  if (typeof window !== 'undefined') {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (preference.value === 'system') {
        mode.value = e.matches ? 'dark' : 'light'
      }
    })
  }

  function persist(p: ThemePreference) {
    try { localStorage.setItem(STORAGE_KEY, p) } catch { /* ignore */ }
  }

  /** Set an explicit user preference (persisted as a local override). */
  function setPreference(p: ThemePreference) {
    preference.value = p
    mode.value = resolveMode(p)
    persist(p)
  }

  /** Toolbar toggle: flip the resolved light/dark and pin it as an explicit override. */
  function toggle() {
    setPreference(mode.value === 'light' ? 'dark' : 'light')
  }

  /**
   * Seed from the config default (program_settings.theme). No-op when the user
   * already has a local override, so an explicit choice always wins.
   */
  function initFromConfig(configTheme: string | null | undefined) {
    if (getStoredPreference() !== null) return
    if (configTheme === 'light' || configTheme === 'dark' || configTheme === 'system') {
      preference.value = configTheme
      mode.value = resolveMode(configTheme)
    }
  }

  watch(mode, (m) => applyTheme(m), { immediate: true })

  return { mode, preference, toggle, setPreference, initFromConfig }
})
