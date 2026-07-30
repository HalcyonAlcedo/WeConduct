import { beforeEach, describe, expect, it } from 'vitest'

import { SOURCE_LOCALE, i18n, resourceLocale, t, tr } from './index'

describe('i18n fallback interpolation', () => {
  beforeEach(() => {
    i18n.global.locale.value = SOURCE_LOCALE
    resourceLocale.value = SOURCE_LOCALE
    i18n.global.setLocaleMessage('en-US', {})
  })

  it('中文源文本会替换命名参数', () => {
    expect(t('framework.runtime.progress.completed', '完成 {n}', { n: 3 })).toBe('完成 3')
  })

  it('外部语言包缺少翻译键时会替换 fallback 命名参数', () => {
    i18n.global.locale.value = 'en-US'

    expect(t('framework.runtime.progress.events', '事件 {n}', { n: 8 })).toBe('事件 8')
  })

  it('资源语言源文本会替换命名参数', () => {
    expect(tr('nodegraph.base.branchLabel', '分支 {n}', { n: 2 })).toBe('分支 2')
  })

  it('已安装语言包仍优先于中文 fallback 并替换命名参数', () => {
    i18n.global.setLocaleMessage('en-US', {
      framework: { runtime: { progress: { completed: 'Completed {n}' } } },
    })
    i18n.global.locale.value = 'en-US'

    expect(t('framework.runtime.progress.completed', '完成 {n}', { n: 5 })).toBe('Completed 5')
  })
})
