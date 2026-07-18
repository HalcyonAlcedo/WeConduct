<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useCompilationStore } from '@/stores/compilationStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useDebugStore } from '@/stores/debugStore'
import SummaryTab from '@/components/output/summary/SummaryTab.vue'
import DiagnosticsTab from '@/components/output/diagnostics/DiagnosticsTab.vue'
import GraphTab from '@/components/output/graph/GraphTab.vue'
import HistoryTab from '@/components/output/history/HistoryTab.vue'
import RuntimeTab from '@/components/output/runtime/RuntimeTab.vue'
import DebugTab from '@/components/output/debug/DebugTab.vue'
import HostInfoTab from '@/components/output/host/HostInfoTab.vue'
import { t } from '@/i18n'

const compilation = useCompilationStore()
const runtimeStore = useRuntimeStore()
const debugStore = useDebugStore()

type TabId = 'summary' | 'diagnostics' | 'graph' | 'history' | 'runtime' | 'debug' | 'host'
const activeTab = ref<TabId>('summary')
watch(() => runtimeStore.runtimeTabRequest, () => { activeTab.value = 'runtime' })

function tabClass(tab: TabId) {
  return {
    'ot-tab': true,
    'ot-tab-active': activeTab.value === tab,
  }
}

function isNonUserFacingDiagnostic(candidate: { category: string; severity: string }) {
  return candidate.category.endsWith('.completed') && candidate.severity === 'info'
}

const compilationDiagnosticCount = computed(() =>
  compilation.diagnosticGroups
    .filter((group) => !isNonUserFacingDiagnostic(group))
    .reduce((sum, group) => sum + group.count, 0),
)
const runtimeDiagnosticCount = computed(() =>
  runtimeStore.runtimeDiagnosticGroups.reduce((sum, group) => sum + group.count, 0),
)
const debugDiagnosticCount = computed(() =>
  (debugStore.activeSession?.diagnostic_links || [])
    .filter((group) => !isNonUserFacingDiagnostic(group))
    .length,
)
const diagCount = computed(() => {
  const total = compilationDiagnosticCount.value + runtimeDiagnosticCount.value + debugDiagnosticCount.value
  if (total === 0) return ''
  return `(C${compilationDiagnosticCount.value}/R${runtimeDiagnosticCount.value}/D${debugDiagnosticCount.value})`
})
</script>

<template>
  <div class="output-panel">
    <!-- Tabs -->
    <div class="ot-tabs">
      <button :class="tabClass('summary')" @click="activeTab = 'summary'">{{ t('framework.output.tabs.summary', '概要') }}</button>
      <button :class="tabClass('diagnostics')" @click="activeTab = 'diagnostics'">{{ t('framework.output.tabs.diagnostics', '诊断') }} {{ diagCount }}</button>
      <button :class="tabClass('graph')" @click="activeTab = 'graph'">{{ t('framework.output.tabs.graph', '图模型') }}</button>
      <button :class="tabClass('history')" @click="activeTab = 'history'">{{ t('framework.output.tabs.history', '历史') }}</button>
      <button :class="tabClass('runtime')" @click="activeTab = 'runtime'">Runtime</button>
      <button :class="tabClass('debug')" @click="activeTab = 'debug'">Debug</button>
      <button :class="tabClass('host')" @click="activeTab = 'host'">Host</button>
    </div>

    <!-- Tab Content -->
    <div class="ot-content">
      <SummaryTab v-if="activeTab === 'summary'" />
      <DiagnosticsTab v-if="activeTab === 'diagnostics'" />
      <GraphTab v-if="activeTab === 'graph'" />
      <HistoryTab v-if="activeTab === 'history'" />
      <RuntimeTab v-if="activeTab === 'runtime'" />
      <DebugTab v-if="activeTab === 'debug'" />
      <HostInfoTab v-if="activeTab === 'host'" />
    </div>
  </div>
</template>

<style scoped>
.output-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel);
}

.ot-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  padding: 0 var(--space-sm);
  background: var(--bg-panel-header);
}

.ot-tab {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 100ms var(--ease-out);
}
.ot-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.ot-tab-active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}

.ot-content {
  flex: 1;
  overflow-y: auto;
  animation: tab-switch 150ms var(--ease-out);
}
@keyframes tab-switch {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
