<script setup lang="ts">
import { onMounted, watchEffect } from 'vue'
import { useDockStore } from '@/stores/dockStore'
import { useResourceStore } from '@/stores/resourceStore'
import { t } from '@/i18n'
import DockLayout from '@/components/panels/DockLayout.vue'
import SourceInputPanel from '@/components/input/SourceInputPanel.vue'
import OutputPanel from '@/components/output/OutputPanel.vue'
import ComponentLibraryPanel from '@/components/shells/ComponentLibraryPanel.vue'
import MetadataEditorPanel from '@/components/shells/MetadataEditorPanel.vue'
import ResourceManagerPanel from '@/components/shells/ResourceManagerPanel.vue'
import TaskExecutionPanel from '@/components/shells/TaskExecutionPanel.vue'
import GraphCanvasPanel from '@/components/output/graph/GraphCanvasPanel.vue'
import PreferencesPanel from '@/components/shells/PreferencesPanel.vue'
import ProjectSettingsPanel from '@/components/shells/ProjectSettingsPanel.vue'
import PackagePanel from '@/components/shells/PackagePanel.vue'
import DebugVariablesPanel from '@/components/output/debug/DebugVariablesPanel.vue'
import DebugTimelinePanel from '@/components/output/debug/DebugTimelinePanel.vue'
import DebugSnapshotsPanel from '@/components/output/debug/DebugSnapshotsPanel.vue'

const dock = useDockStore()
const resource = useResourceStore()

// Panel id → localized title. A function (re-invoked inside watchEffect) so the
// `t()` calls re-resolve when the UI locale changes; titles are stored strings
// in the dock store, so we must actively push updates rather than rely on them
// re-rendering.
function panelTitles(): Record<string, string> {
  return {
    graph: t('framework.workbench.panel.graph', '节点图编辑器'),
    components: t('framework.workbench.panel.components', '组件库'),
    metadata: t('framework.workbench.panel.metadata', '元数据编辑'),
    source: t('framework.workbench.panel.source', '源输入'),
    output: t('framework.workbench.panel.output', '输出'),
    resources: t('framework.workbench.panel.resources', '资源管理'),
    tasks: t('framework.workbench.panel.tasks', '任务执行'),
    preferences: t('framework.workbench.panel.preferences', '首选项'),
    projectSettings: t('framework.workbench.panel.projectSettings', '项目设置'),
    packageManager: t('framework.workbench.panel.packageManager', '.wcrun 包管理'),
    debugVariables: t('framework.workbench.panel.debugVariables', 'Debug 变量'),
    debugTimeline: t('framework.workbench.panel.debugTimeline', 'Debug 事件'),
    debugSnapshots: t('framework.workbench.panel.debugSnapshots', 'Debug 快照'),
  }
}

onMounted(() => {
  resource.refreshAll()
  for (const [id, title] of Object.entries(panelTitles())) {
    dock.register({ id, title })
  }

  // Re-localize titles live when the UI language changes (watchEffect tracks the
  // reactive locale via the t() calls inside panelTitles()).
  watchEffect(() => {
    for (const [id, title] of Object.entries(panelTitles())) {
      dock.setPanelTitle(id, title)
    }
  })

  // Default layout
  if (dock.zones.center.panels.length === 0) {
    dock.addToZone('graph', 'center')
    dock.addToZone('components', 'left')
    dock.addToZone('source', 'bottom')
    dock.addToZone('output', 'bottom')
  }
})
</script>

<template>
  <DockLayout>
    <template #graph><GraphCanvasPanel /></template>
    <template #components><ComponentLibraryPanel /></template>
    <template #metadata><MetadataEditorPanel /></template>
    <template #source><SourceInputPanel /></template>
    <template #output><OutputPanel /></template>
    <template #resources><ResourceManagerPanel /></template>
    <template #tasks><TaskExecutionPanel /></template>
    <template #preferences><PreferencesPanel /></template>
    <template #projectSettings><ProjectSettingsPanel /></template>
    <template #packageManager><PackagePanel /></template>
    <template #debugVariables><DebugVariablesPanel /></template>
    <template #debugTimeline><DebugTimelinePanel /></template>
    <template #debugSnapshots><DebugSnapshotsPanel /></template>
  </DockLayout>
</template>
