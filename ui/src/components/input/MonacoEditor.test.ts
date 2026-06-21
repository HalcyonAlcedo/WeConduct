import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import MonacoEditor from './MonacoEditor.vue'

type MockEditor = {
  getValue: ReturnType<typeof vi.fn>
  setValue: ReturnType<typeof vi.fn>
  updateOptions: ReturnType<typeof vi.fn>
  onDidChangeModelContent: ReturnType<typeof vi.fn>
  dispose: ReturnType<typeof vi.fn>
}

let mockEditor: MockEditor
let mutationObserverCallback: MutationCallback | null = null

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
}

class MockMutationObserver {
  constructor(callback: MutationCallback) {
    mutationObserverCallback = callback
  }

  observe = vi.fn()
  disconnect = vi.fn()
}

vi.mock('monaco-editor', () => ({
  editor: {
    create: vi.fn(() => mockEditor),
    setTheme: vi.fn(),
  },
}))

describe('MonacoEditor', () => {
  beforeEach(() => {
    mockEditor = {
      getValue: vi.fn(() => 'initial'),
      setValue: vi.fn(),
      updateOptions: vi.fn(),
      onDidChangeModelContent: vi.fn(),
      dispose: vi.fn(),
    }
    mutationObserverCallback = null
    vi.stubGlobal('MutationObserver', MockMutationObserver)
    document.documentElement.setAttribute('data-theme', 'light')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('在 readOnly 变化时同步更新 Monaco 实例选项', async () => {
    const readOnly = ref(false)
    const Host = defineComponent({
      components: { MonacoEditor },
      setup() {
        return { readOnly }
      },
      template: '<MonacoEditor model-value="demo" :read-only="readOnly" />',
    })

    mount(Host)
    await nextTick()
    await vi.dynamicImportSettled()
    await flushPromises()

    expect(mockEditor.updateOptions).not.toHaveBeenCalled()

    readOnly.value = true
    await nextTick()
    await flushPromises()

    expect(mockEditor.updateOptions).toHaveBeenCalledWith({ readOnly: true })
  })

  it('在主题变更时调用 monaco.editor.setTheme', async () => {
    const monaco = await import('monaco-editor')
    mount(MonacoEditor, {
      props: {
        modelValue: 'demo',
      },
    })
    await nextTick()
    await vi.dynamicImportSettled()
    await flushPromises()

    document.documentElement.setAttribute('data-theme', 'dark')
    mutationObserverCallback?.([] as MutationRecord[], {} as MutationObserver)

    expect(monaco.editor.setTheme).toHaveBeenCalledWith('vs-dark')
  })
})
