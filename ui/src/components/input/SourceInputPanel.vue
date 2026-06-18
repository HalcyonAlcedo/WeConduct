<script setup lang="ts">
import { computed } from 'vue'
import { useCompilationStore } from '@/stores/compilationStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import MonacoEditor from '@/components/input/MonacoEditor.vue'

const compilation = useCompilationStore()
const workspace = useWorkspaceStore()
const graphWs = useGraphWorkspaceStore()

const stages = ['parse', 'bind', 'validate', 'normalize', 'lower', 'emit'] as const

function onSourceChange(value: string) {
  compilation.setSource(value)
}

function onClear() {
  compilation.clearSource()
}

/** Rich stage state: considers both backend status and diagnostic severities */
function stageClass(stage: string) {
  const baseStatus = compilation.stageStatuses[stage as typeof stages[number]]
  if (baseStatus === 'pending') return { 'pi-dot': true, 'pi-idle': true }
  if (baseStatus === 'skipped') return { 'pi-dot': true, 'pi-skipped': true }
  if (baseStatus === 'failed') {
    // Check if there's a fatal diagnostic for this stage
    const hasFatal = compilation.stageDiagnostics(stage).some(d => d.severity === 'fatal')
    return { 'pi-dot': true, 'pi-failed': true, 'pi-fatal': hasFatal }
  }
  if (baseStatus === 'succeeded') {
    const diags = compilation.stageDiagnostics(stage)
    const hasError = diags.some(d => d.severity === 'error')
    const hasDegraded = diags.some(d => d.severity === 'degraded')
    const hasWarning = diags.some(d => d.severity === 'warning')
    if (hasError) return { 'pi-dot': true, 'pi-degraded': true }
    if (hasDegraded) return { 'pi-dot': true, 'pi-degraded': true }
    if (hasWarning) return { 'pi-dot': true, 'pi-warning': true }
    return { 'pi-dot': true, 'pi-succeeded': true }
  }
  return { 'pi-dot': true, 'pi-idle': true }
}

function stageRunning(stage: string): boolean {
  return compilation.isCompiling && compilation.stageStatuses[stage as typeof stages[number]] === 'pending'
    && stages.slice(0, stages.indexOf(stage as typeof stages[number])).every(
      s => compilation.stageStatuses[s] === 'succeeded'
    )
}

const sourceKinds = workspace.availableSourceKinds.length > 0
  ? workspace.availableSourceKinds
  : ['native_flow']

function onKindChange(e: Event) {
  const target = e.target as HTMLSelectElement
  compilation.setSourceKind(target.value)
}

const syncStatus = computed(() => graphWs.syncStatus)
</script>

<template>
  <div class="source-panel">
    <div class="sp-toolbar">
      <select
        class="sp-select"
        :value="compilation.sourceKind"
        @change="onKindChange"
      >
        <option v-for="k in sourceKinds" :key="k" :value="k">{{ k }}</option>
      </select>
      <span class="sp-status" v-if="compilation.inputState === 'valid'">✓ 就绪</span>
      <span class="sp-status empty" v-else>空</span>
      <span v-if="syncStatus !== 'idle'" class="sp-sync-status" :class="'sync-'+syncStatus">{{ syncStatus === 'syncing' ? '⟳' : syncStatus === 'synced' ? '✓' : syncStatus === 'failed' ? '✕' : '⟳' }}</span>
      <button class="sp-btn-ghost" @click="graphWs.syncSource()" :disabled="syncStatus === 'syncing'" title="从节点图同步源码">🔄 同步</button>
      <button class="sp-btn-ghost" @click="onClear">清空</button>
    </div>

    <div class="sp-editor-wrap">
      <MonacoEditor
        :model-value="compilation.sourceText"
        :language="compilation.sourceKind === 'webcontrol_main_flow' ? 'yaml' : 'json'"
        @update:model-value="onSourceChange"
      />
    </div>

    <div class="sp-pipeline">
      <div
        v-for="stage in stages"
        :key="stage"
        :class="stageClass(stage)"
      >
        <span v-if="stageRunning(stage)" class="pi-running-dot stage-running"></span>
        <span class="pi-label">{{ stage }}</span>
      </div>
    </div>

    <div class="sp-statusbar">
      <span>字数: {{ compilation.sourceText.length }}</span>
      <span class="sp-sb-div">|</span>
      <span>行: {{ compilation.sourceText ? compilation.sourceText.split('\n').length : 0 }}</span>
      <span class="sp-sb-div">|</span>
      <span>编码: UTF-8</span>
      <span class="sp-sb-div">|</span>
      <span>光标: Ln 1, Col 1</span>
    </div>

    <div class="sp-actions">
      <button
        class="sp-btn-compile"
        :disabled="!compilation.canCompile"
        @click="compilation.compile()"
      >
        {{ compilation.isCompiling ? '编译中…' : '▶ 编译' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.source-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel);
}

.sp-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.sp-select {
  padding: 2px 6px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: var(--text-small);
  height: 24px;
}

.sp-status {
  font-size: var(--text-small);
  color: var(--state-success);
  font-weight: 500;
}
.sp-status.empty {
  color: var(--text-disabled);
}

.sp-btn-ghost {
  padding: 2px 8px;
  border: 1px solid var(--border-default);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-size: var(--text-small);
  font-family: var(--font-ui);
}
.sp-btn-ghost:hover {
  background: var(--bg-hover);
}
.sp-btn-ghost:first-of-type {
  margin-left: auto;
}

.sp-editor-wrap {
  flex: 1;
  overflow: hidden;
}

.sp-pipeline {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-xl);
  padding: var(--space-sm) var(--space-md);
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.pi-dot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 48px;
}

.pi-label {
  font-size: 9px;
  color: var(--text-disabled);
  text-transform: lowercase;
}

.pi-dot::before {
  content: '';
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.pi-idle::before     { background: var(--text-disabled); opacity: 0.35; }
.pi-succeeded::before { background: var(--state-success); }
.pi-warning::before   { background: var(--state-warning); }
.pi-degraded::before  { content: '▲'; background: none; color: var(--state-degraded); font-size: 9px; line-height: 10px; text-align: center; }
.pi-failed::before    { content: '✕'; background: none; color: var(--state-error); font-size: 7px; line-height: 10px; font-weight: 700; text-align: center; }
.pi-fatal::before     { content: '✕'; background: none; color: var(--state-fatal); font-size: 7px; line-height: 10px; font-weight: 700; text-align: center; }
.pi-skipped::before   { background: var(--text-disabled); opacity: 0.15; }

.pi-running-dot {
  position: absolute;
  top: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3B82F6;
}

.sp-statusbar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 2px var(--space-md);
  font-size: var(--text-caption);
  color: var(--text-disabled);
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.sp-sb-div { color: var(--border-default); }

.sp-actions {
  padding: var(--space-sm) var(--space-md);
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
  display: flex;
  gap: var(--space-sm);
}

.sp-btn-compile {
  flex: 1;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--accent);
  color: #fff;
  font-family: var(--font-ui);
  font-size: var(--text-body);
  font-weight: 600;
  cursor: pointer;
  transition: background 100ms var(--ease-out);
}
.sp-btn-compile:hover:not(:disabled) {
  background: var(--accent-hover);
}
.sp-btn-compile:disabled { opacity: 0.4; cursor: not-allowed; }
.sp-sync-status { font-size: var(--text-caption); margin-right: 2px; }
.sync-syncing { color: var(--state-info); animation: stage-pulse 0.8s ease-in-out infinite; }
.sync-synced { color: var(--state-success); }
.sync-failed { color: var(--state-error); }
.sync-stale { color: var(--state-warning); }
</style>
