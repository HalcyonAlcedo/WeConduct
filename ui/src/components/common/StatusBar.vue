<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'

const workspace = useWorkspaceStore()
const compilation = useCompilationStore()

const statusText = computed(() => {
  if (!workspace.isConnected) return '✕ 离线'
  if (compilation.isCompiling) return '◉ 编译中…'
  if (compilation.compilePhase === 'completed') return '✓ 编译成功'
  if (compilation.compilePhase === 'failed') return '✕ 编译失败'
  return '✓ 就绪'
})

const statusClass = computed(() => {
  if (!workspace.isConnected) return 'status-error'
  if (compilation.isCompiling) return 'status-warning'
  if (compilation.compilePhase === 'completed') return 'status-success'
  if (compilation.compilePhase === 'failed') return 'status-error'
  return ''
})

const projectLabel = computed(() => {
  return workspace.projectName ?? '—'
})

const compileCountLabel = computed(() => {
  const n = workspace.compileCounter
  return n > 0 ? `编译 #${n}` : '未编译'
})

const lastCompileTimeLabel = computed(() => {
  const t = workspace.lastCompileTime
  if (!t) return null
  // Format ISO datetime to a shorter form
  try {
    const d = new Date(t)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return t.slice(0, 19)
  }
})

const diagCount = computed(() => {
  const view = compilation.view
  if (!view) return 0
  return view.diagnostic_summary?.total_count ?? 0
})

const sourceLines = computed(() => {
  const text = compilation.sourceText
  if (!text) return '—'
  return `Ln ${text.split('\n').length}`
})

const productLabel = computed(() => {
  return 'WeConduct'
})
</script>

<template>
  <footer class="statusbar" role="contentinfo">
    <span :class="['status-left', statusClass]">{{ statusText }}</span>
    <span class="status-flex"></span>
    <span class="status-item">{{ compileCountLabel }}</span>
    <span v-if="lastCompileTimeLabel" class="status-divider">|</span>
    <span v-if="lastCompileTimeLabel" class="status-item">{{ lastCompileTimeLabel }}</span>
    <span class="status-divider">|</span>
    <span class="status-item">{{ projectLabel }}</span>
    <span class="status-divider">|</span>
    <span class="status-item">诊断: {{ diagCount }}</span>
    <span class="status-divider">|</span>
    <span class="status-item">{{ sourceLines }}</span>
    <span class="status-divider">|</span>
    <span class="status-item status-product">{{ productLabel }}</span>
  </footer>
</template>

<style scoped>
.statusbar {
  display: flex;
  align-items: center;
  height: var(--statusbar-height);
  background: var(--bg-statusbar);
  border-top: 1px solid var(--border-subtle);
  padding: 0 var(--space-md);
  font-family: var(--font-ui);
  font-size: var(--text-small);
  color: var(--text-secondary);
  flex-shrink: 0;
  gap: var(--space-sm);
  user-select: none;
}

.status-flex {
  flex: 1;
}

.status-left {
  font-weight: 500;
}

.status-left.status-success { color: var(--state-success); }
.status-left.status-warning { color: var(--state-warning); }
.status-left.status-error   { color: var(--state-error); }

.status-item {
  color: var(--text-secondary);
}

.status-product {
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.02em;
}

.status-divider {
  color: var(--border-default);
}
</style>
