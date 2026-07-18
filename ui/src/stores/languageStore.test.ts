import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiMocks = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number
    body: unknown
    constructor(status: number, body: unknown) { super('mock'); this.status = status; this.body = body }
  }
  return {
    fetchLanguages: vi.fn(),
    fetchLanguagePack: vi.fn(),
    ApiError: MockApiError,
  }
})

vi.mock('@/services/api', () => ({
  fetchLanguages: apiMocks.fetchLanguages,
  fetchLanguagePack: apiMocks.fetchLanguagePack,
  ApiError: apiMocks.ApiError,
}))

import { useLanguageStore } from './languageStore'
import { i18n, resourceLocale, SOURCE_LOCALE, t, tr } from '@/i18n'

describe('languageStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    try { localStorage.clear() } catch { /* jsdom */ }
    // Reset i18n back to the source locale + empty messages between tests.
    i18n.global.locale.value = SOURCE_LOCALE
    resourceLocale.value = SOURCE_LOCALE
    i18n.global.setLocaleMessage('en-US', {})
    i18n.global.setLocaleMessage('ja-JP', {})
    apiMocks.fetchLanguages.mockResolvedValue({ languages: [] })
    apiMocks.fetchLanguagePack.mockResolvedValue({ locale: 'en-US', messages: {} })
  })

  it('默认停留在源语言（无需语言包）', () => {
    const store = useLanguageStore()
    expect(store.locale).toBe(SOURCE_LOCALE)
    expect(i18n.global.locale.value).toBe(SOURCE_LOCALE)
  })

  it('refreshAvailable 拉取可用语言列表', async () => {
    apiMocks.fetchLanguages.mockResolvedValue({
      languages: [{ locale: 'en-US', display_name: 'English' }],
    })
    const store = useLanguageStore()
    await store.refreshAvailable()
    expect(store.available).toEqual([{ locale: 'en-US', display_name: 'English' }])
  })

  it('setLocale 加载语言包并切换 vue-i18n locale', async () => {
    apiMocks.fetchLanguagePack.mockResolvedValue({
      locale: 'en-US',
      messages: { framework: { commandBar: { menu: { file: 'File' } } } },
    })
    const store = useLanguageStore()
    const ok = await store.setLocale('en-US')

    expect(ok).toBe(true)
    expect(i18n.global.locale.value).toBe('en-US')
    // Translation now resolves via the pack; fallback is ignored.
    expect(t('framework.commandBar.menu.file', '文件')).toBe('File')
    // Persisted as an explicit override.
    expect(localStorage.getItem('weconduct-language')).toBe('en-US')
  })

  it('缺失键回退到硬编码中文', async () => {
    apiMocks.fetchLanguagePack.mockResolvedValue({
      locale: 'en-US',
      messages: { framework: { commandBar: { menu: { file: 'File' } } } },
    })
    const store = useLanguageStore()
    await store.setLocale('en-US')
    // A key the pack does not define falls back to the Chinese literal.
    expect(t('framework.commandBar.menu.missing', '缺失')).toBe('缺失')
  })

  it('语言包加载失败时停留在源语言', async () => {
    apiMocks.fetchLanguagePack.mockRejectedValue(new apiMocks.ApiError(404, { error: 'not_found' }))
    const store = useLanguageStore()
    const ok = await store.setLocale('fr-FR')

    expect(ok).toBe(false)
    expect(i18n.global.locale.value).toBe(SOURCE_LOCALE)
    // The user's choice is still persisted so a later pack install picks it up.
    expect(localStorage.getItem('weconduct-language')).toBe('fr-FR')
  })

  it('initFromConfig 用配置默认值播种（无本地覆盖时）', async () => {
    apiMocks.fetchLanguagePack.mockResolvedValue({
      locale: 'en-US',
      messages: { framework: {} },
    })
    const store = useLanguageStore()
    await store.initFromConfig('en-US')
    expect(store.locale).toBe('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
  })

  it('initFromConfig 本地覆盖优先于配置默认值', async () => {
    localStorage.setItem('weconduct-language', SOURCE_LOCALE)
    const store = useLanguageStore()
    await store.initFromConfig('en-US')
    // Local override (zh-CN) wins over the config default (en-US).
    expect(store.locale).toBe(SOURCE_LOCALE)
    expect(i18n.global.locale.value).toBe(SOURCE_LOCALE)
  })

  it('setResourceLocale 只影响资源语言，不影响界面语言', async () => {
    apiMocks.fetchLanguagePack.mockResolvedValue({
      locale: 'en-US',
      messages: { nodegraph: { execution: { label: 'Execution Node' } } },
    })
    const store = useLanguageStore()
    const ok = await store.setResourceLocale('en-US')

    expect(ok).toBe(true)
    expect(store.resource).toBe('en-US')
    expect(resourceLocale.value).toBe('en-US')
    // UI locale is untouched — the two axes are independent.
    expect(i18n.global.locale.value).toBe(SOURCE_LOCALE)
    expect(localStorage.getItem('weconduct-resource-language')).toBe('en-US')
    // tr() resolves via the resource pack; t() still falls back to Chinese.
    expect(tr('nodegraph.execution.label', '执行节点')).toBe('Execution Node')
    expect(t('nodegraph.execution.label', '执行节点')).toBe('执行节点')
  })

  it('界面语言与资源语言可设为不同 locale', async () => {
    apiMocks.fetchLanguagePack.mockImplementation(async (loc: string) => {
      if (loc === 'en-US') return { locale: 'en-US', messages: { framework: { a: 'EN' } } }
      return { locale: 'ja-JP', messages: { nodegraph: { b: 'JA' } } }
    })
    const store = useLanguageStore()
    await store.setLocale('en-US')
    await store.setResourceLocale('ja-JP')

    expect(i18n.global.locale.value).toBe('en-US')
    expect(resourceLocale.value).toBe('ja-JP')
    expect(t('framework.a', '甲')).toBe('EN')
    expect(tr('nodegraph.b', '乙')).toBe('JA')
  })

  it('initFromConfig 同时播种界面语言与资源语言', async () => {
    apiMocks.fetchLanguagePack.mockResolvedValue({
      locale: 'en-US',
      messages: { framework: {} },
    })
    const store = useLanguageStore()
    await store.initFromConfig('en-US', 'en-US')
    expect(store.locale).toBe('en-US')
    expect(store.resource).toBe('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
    expect(resourceLocale.value).toBe('en-US')
  })
})
