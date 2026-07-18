/** WeConduct — i18n core
 *
 *  Design: Chinese-source-as-fallback.
 *  - Every UI string is written in the component as a hardcoded Chinese literal
 *    passed to `t(key, fallbackZh)`. That literal is BOTH the zh-CN display text
 *    and the dev-readable source — no zh-CN language file is shipped.
 *  - When the active locale has a message registered for `key`, the translated
 *    text is shown; otherwise it falls back to the hardcoded Chinese.
 *  - No languages are bundled. External packs are loaded at runtime via
 *    `i18n.global.setLocaleMessage(locale, tree)` (see languageStore).
 *
 *  Result: i18n errors, missing keys, or partial packs degrade gracefully to
 *  Chinese instead of showing raw key names.
 */

import { createI18n } from 'vue-i18n'
import { ref } from 'vue'

export const SOURCE_LOCALE = 'zh-CN'

export const i18n = createI18n({
  legacy: false,
  locale: SOURCE_LOCALE,
  fallbackLocale: SOURCE_LOCALE,
  // Suppress "not found" / "fallback" console noise: missing keys are the
  // normal case (we intentionally fall back to the hardcoded literal).
  missingWarn: false,
  fallbackWarn: false,
  messages: {},
})

/**
 * The resource locale — a SEPARATE axis from the UI locale (`i18n.global.locale`).
 *
 * WeConduct has two independently-configured languages:
 * - **界面语言 (UI language, `program_settings.language`)** drives the app
 *   framework chrome via `t()` — it is `i18n.global.locale`.
 * - **资源语言 (resource language, `program_settings.resource_language`)** drives
 *   per-module / node-graph content via `tr()`. Modules follow this, NOT the UI
 *   language, so a user can run an English UI over Chinese module content (or
 *   vice-versa). The backend already uses `resource_language` for resource
 *   display names (`display_name_i18n`); `tr()` is its front-end counterpart.
 *
 * Both locales' packs are registered into the same vue-i18n message store keyed
 * by locale; `t()` reads the UI locale, `tr()` reads this one.
 */
export const resourceLocale = ref<string>(SOURCE_LOCALE)

/**
 * Translate `key`, falling back to the hardcoded Chinese source text.
 *
 * @param key        Namespaced message key, e.g. 'framework.commandBar.menu.file'
 * @param fallbackZh Hardcoded Chinese literal — shown when `key` is not
 *                   registered for the active locale (the zh-CN case, missing
 *                   translations, or i18n failure).
 * @param named      Optional named interpolation values.
 */
export function t(
  key: string,
  fallbackZh: string,
  named?: Record<string, unknown>,
): string {
  const g = i18n.global
  // On the source locale we never look up — the literal IS the text.
  if (g.locale.value === SOURCE_LOCALE) return fallbackZh
  // Targets the current UI locale, which is vue-i18n's default — no locale
  // option needed. (`t(key, object)` would treat the object as named-interp
  // values, not options, so the third-arg form is required when overriding.)
  if (!g.te(key, g.locale.value)) return fallbackZh
  return named ? g.t(key, named) : g.t(key)
}

/**
 * Translate a RESOURCE / module string against the resource locale
 * (`resourceLocale`), falling back to the hardcoded Chinese source text.
 *
 * Use this for node-graph node content and other per-module text that must
 * follow 资源语言 rather than the UI 界面语言. Identical fallback semantics to
 * `t()`, but keyed off `resourceLocale` instead of `i18n.global.locale`.
 */
export function tr(
  key: string,
  fallbackZh: string,
  named?: Record<string, unknown>,
): string {
  const g = i18n.global
  const locale = resourceLocale.value
  if (locale === SOURCE_LOCALE) return fallbackZh
  if (!g.te(key, locale)) return fallbackZh
  // Locale override must go in the 3rd (options) arg; the 2nd positional object
  // is named-interpolation values in the vue-i18n composition API.
  return named ? g.t(key, named, { locale }) : g.t(key, {}, { locale })
}

/** Vue plugin: exposes `$t2` (UI) and `$tr` (resource) in templates. */
export const i18nFallbackPlugin = {
  install(app: { config: { globalProperties: Record<string, unknown> } }) {
    app.config.globalProperties.$t2 = t
    app.config.globalProperties.$tr = tr
  },
}
