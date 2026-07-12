<script setup lang="ts">
import { onMounted } from 'vue'
import { useDockStore } from '@/stores/dockStore'
import { useResourceStore } from '@/stores/resourceStore'
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

onMounted(() => {
  resource.refreshAll()
  dock.register({ id: 'graph', title: '节点图编辑器' })
  dock.register({ id: 'components', title: '组件库' })
  dock.register({ id: 'metadata', title: '元数据编辑' })
  dock.register({ id: 'source', title: '源输入' })
  dock.register({ id: 'output', title: '输出' })
  dock.register({ id: 'resources', title: '资源管理' })
  dock.register({ id: 'tasks', title: '任务执行' })
  dock.register({ id: 'preferences', title: '首选项' })
  dock.register({ id: 'projectSettings', title: '项目设置' })
  dock.register({ id: 'packageManager', title: '.wcrun 包管理' })
  dock.register({ id: 'debugVariables', title: 'Debug 变量' })
  dock.register({ id: 'debugTimeline', title: 'Debug 事件' })
  dock.register({ id: 'debugSnapshots', title: 'Debug 快照' })

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
