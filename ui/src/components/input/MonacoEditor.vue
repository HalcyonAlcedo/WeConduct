<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'
import type * as Monaco from 'monaco-editor'

const props = defineProps<{
  modelValue: string
  language?: string
  readOnly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const editorRef = shallowRef<Monaco.editor.IStandaloneCodeEditor | null>(null)
let monacoRef: typeof Monaco | null = null

onMounted(async () => {
  const monaco = await import('monaco-editor')
  monacoRef = monaco

  if (!containerRef.value) return

  const editor = monaco.editor.create(containerRef.value, {
    value: props.modelValue,
    language: props.language ?? 'json',
    theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'vs-dark' : 'vs',
    fontSize: 13,
    fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Consolas', 'SF Mono', monospace",
    lineNumbers: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    tabSize: 2,
    automaticLayout: true,
    readOnly: props.readOnly ?? false,
    renderLineHighlight: 'line',
    cursorBlinking: 'smooth',
    smoothScrolling: true,
    padding: { top: 12, bottom: 12 },
  })

  editor.onDidChangeModelContent(() => {
    const value = editor.getValue()
    emit('update:modelValue', value)
  })

  editorRef.value = editor
  // Expose for E2E testing
  ;(window as any).__monacoEditor = editor
})

onUnmounted(() => {
  editorRef.value?.dispose()
  if ((window as any).__monacoEditor === editorRef.value) {
    delete (window as any).__monacoEditor
  }
})

// Sync external value changes into editor
watch(() => props.modelValue, (val) => {
  const editor = editorRef.value
  if (editor && editor.getValue() !== val) {
    editor.setValue(val)
  }
})

// Sync theme changes
function updateTheme() {
  if (!monacoRef) return
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
  monacoRef.editor.setTheme(isDark ? 'vs-dark' : 'vs')
}

// Listen for theme changes on document
if (typeof window !== 'undefined') {
  const observer = new MutationObserver(() => updateTheme())
  onMounted(() => {
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  })
  onUnmounted(() => observer.disconnect())
}

defineExpose({ updateTheme })
</script>

<template>
  <div ref="containerRef" class="monaco-container"></div>
</template>

<style scoped>
.monaco-container {
  width: 100%;
  height: 100%;
  min-height: 200px;
}
</style>
