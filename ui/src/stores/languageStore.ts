/** WeConduct — Language Store
 *
 *  Manages TWO independently-configured locales for the Chinese-source-as-fallback
 *  i18n system (see @/i18n):
 *  - **界面语言 (UI locale, `locale`)** drives the app framework chrome via `t()`.
 *    It is `i18n.global.locale`.
 *  - **资源语言 (resource locale, `resource`)** drives per-module / node-graph
 *    content via `tr()`, tracked by the `resourceLocale` ref in @/i18n. Modules
 *    follow this axis, NOT the UI language, so a user can run an English UI over
 *    Chinese module content (or vice-versa).
 *
 *  Shared design (both axes):
 *  - No languages are bundled. Available locales are discovered at runtime from
 *    the program's `languages/` directory via the backend.
 *  - The source locale (zh-CN) needs no pack: every string has a hardcoded
 *    Chinese literal, so selecting zh-CN just uses the literal.
 *  - Selecting a non-source locale fetches its merged message tree and registers
 *    it with `i18n.global.setLocaleMessage` (keyed by locale — both axes share
 *    the same message store). A failed/missing pack degrades gracefully to the
 *    source locale and shows the hardcoded Chinese.
 *  - Each axis persists the user's explicit choice to its own localStorage key;
 *    the config default only seeds it when there is no local override, so an
 *    explicit choice always wins — mirrors themeStore.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { i18n, resourceLocale, SOURCE_LOCALE } from '@/i18n'
import { fetchLanguages, fetchLanguagePack, ApiError, type LanguageManifest } from '@/services/api'

const STORAGE_KEY = 'weconduct-language'
const RESOURCE_STORAGE_KEY = 'weconduct-resource-language'

function getStored(key: string): string | null {
  try {
    const stored = localStorage.getItem(key)
    if (typeof stored === 'string' && stored.trim()) return stored
  } catch { /* localStorage unavailable */ }
  return null
}

export const useLanguageStore = defineStore('language', () => {
  // Active UI locale — starts on the source; the literal IS the text until a pack loads.
  const locale = ref<string>(getStored(STORAGE_KEY) ?? SOURCE_LOCALE)
  // Active resource locale (independent of the UI locale).
  const resource = ref<string>(getStored(RESOURCE_STORAGE_KEY) ?? SOURCE_LOCALE)
  const available = ref<LanguageManifest[]>([])
  // Locales whose pack has already been fetched + registered this session.
  const loaded = ref<Set<string>>(new Set([SOURCE_LOCALE]))
  const loading = ref(false)

  function persist(key: string, value: string) {
    try { localStorage.setItem(key, value) } catch { /* ignore */ }
  }

  /** Refresh the discovered language list from the program's `languages/` dir. */
  async function refreshAvailable(): Promise<void> {
    try {
      const result = await fetchLanguages()
      available.value = result.languages
    } catch {
      available.value = []
    }
  }

  /**
   * Fetch + register a locale's pack with vue-i18n. No-op for the source locale
   * (needs no pack) or an already-loaded locale. Returns true when the locale is
   * usable (source, freshly loaded, or previously loaded); false on failure.
   * Both axes call this — the pack is shared, keyed by locale.
   */
  async function ensurePackLoaded(target: string): Promise<boolean> {
    if (target === SOURCE_LOCALE) return true
    if (loaded.value.has(target)) return true
    try {
      const pack = await fetchLanguagePack(target)
      i18n.global.setLocaleMessage(target, pack.messages as Record<string, unknown>)
      loaded.value.add(target)
      return true
    } catch (err) {
      // 404 = no such pack (removed on disk); anything else = transport/parse.
      if (!(err instanceof ApiError)) { /* swallow: degrade to source */ }
      return false
    }
  }

  /** Apply the UI locale to vue-i18n, loading its pack first. Falls back to source. */
  async function applyUiLocale(target: string): Promise<boolean> {
    if (target === SOURCE_LOCALE) {
      i18n.global.locale.value = SOURCE_LOCALE
      return true
    }
    const ok = await ensurePackLoaded(target)
    i18n.global.locale.value = ok ? target : SOURCE_LOCALE
    return ok
  }

  /** Apply the resource locale (drives `tr()`), loading its pack first. */
  async function applyResourceLocale(target: string): Promise<boolean> {
    if (target === SOURCE_LOCALE) {
      resourceLocale.value = SOURCE_LOCALE
      return true
    }
    const ok = await ensurePackLoaded(target)
    resourceLocale.value = ok ? target : SOURCE_LOCALE
    return ok
  }

  /**
   * Set an explicit UI locale (persisted as a local override) and apply it.
   * Returns false when the pack could not be loaded (locale left on source).
   */
  async function setLocale(target: string): Promise<boolean> {
    locale.value = target
    persist(STORAGE_KEY, target)
    loading.value = true
    try {
      return await applyUiLocale(target)
    } finally {
      loading.value = false
    }
  }

  /** Set an explicit resource locale (persisted as a local override) and apply it. */
  async function setResourceLocale(target: string): Promise<boolean> {
    resource.value = target
    persist(RESOURCE_STORAGE_KEY, target)
    loading.value = true
    try {
      return await applyResourceLocale(target)
    } finally {
      loading.value = false
    }
  }

  /**
   * Boot-time seed: pull the available list, then activate both effective locales
   * (local override if present, else the config default, else source). Never
   * throws — a broken pack or missing endpoint just leaves that axis on the source.
   */
  async function initFromConfig(
    configLocale: string | null | undefined,
    configResourceLocale?: string | null | undefined,
  ): Promise<void> {
    await refreshAvailable()
    const resolve = (override: string | null, configured: string | null | undefined) =>
      override ??
      (typeof configured === 'string' && configured.trim() ? configured : SOURCE_LOCALE)
    const effectiveUi = resolve(getStored(STORAGE_KEY), configLocale)
    const effectiveResource = resolve(getStored(RESOURCE_STORAGE_KEY), configResourceLocale)
    locale.value = effectiveUi
    resource.value = effectiveResource
    loading.value = true
    try {
      await Promise.all([
        applyUiLocale(effectiveUi),
        applyResourceLocale(effectiveResource),
      ])
    } finally {
      loading.value = false
    }
  }

  return {
    locale,
    resource,
    available,
    loading,
    refreshAvailable,
    setLocale,
    setResourceLocale,
    initFromConfig,
  }
})
