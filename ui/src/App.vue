<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useGraphStore } from '@/stores/graphStore'
import { useDockStore } from '@/stores/dockStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useToastStore } from '@/stores/toastStore'
import { useUpdateStore } from '@/stores/updateStore'
import { useStartupStore } from '@/stores/startupStore'
import { useThemeStore } from '@/stores/themeStore'
import { useKeyboard } from '@/composables/useKeyboard'
import CommandBar from '@/components/commandbar/CommandBar.vue'
import StatusBar from '@/components/common/StatusBar.vue'
import ToastContainer from '@/components/common/ToastContainer.vue'
import StartupErrorScreen from '@/components/common/StartupErrorScreen.vue'

const workspace = useWorkspaceStore()
const theme = useThemeStore()
const compilation = useCompilationStore()
const graphWs = useGraphWorkspaceStore()
const graphStore = useGraphStore()
const toast = useToastStore()
const updateStore = useUpdateStore()
const startup = useStartupStore()

/** When true, the app was force-started despite a non-blocking startup anomaly. */
const forceStarted = ref(false)
function shouldConfirmDeleteNode(): boolean {
  return ((workspace.snapshot as any)?.graph_workspace?.graph_preferences?.confirm_delete_node) !== false
}

useKeyboard([
  { key: 'Enter', ctrl: true, handler: async () => {
    if (!graphWs.hasGraph) { toast.info('', '当前图为空'); return }
    const runtime = useRuntimeStore()
    if (runtime.isRuntimeActive) { toast.info('任务运行中', '请使用终止按钮结束当前任务'); return }
    if (!compilation.sourceText.trim() && graphWs.graphModel) await graphWs.syncSource()
    const result = await runtime.startAndRun(graphWs.graphModel as Record<string, unknown> | undefined, graphWs.isDirty)
    if (result.success) toast.success('运行完成', result.message)
    else toast.error('运行失败', result.message)
  }, ignoreInput: false },
  { key: 'k', ctrl: true, handler: () => compilation.clearSource(), ignoreInput: true },
  { key: 'z', ctrl: true, handler: () => graphWs.undo(), ignoreInput: false },
  { key: 'y', ctrl: true, handler: () => graphWs.redo(), ignoreInput: false },
  { key: 's', ctrl: true, handler: () => toast.info('保存', '请使用 文件 → 保存'), ignoreInput: true },
  { key: 'c', ctrl: true, handler: () => { if (window.getSelection()?.toString()) return; const node = graphStore.selectedNode; if (node && graphWs.graphModel) { const n = graphWs.graphModel.nodes.find(n => n.node_id === node); if (n) { (window as any).__copiedNode = JSON.parse(JSON.stringify(n)); toast.info('已复制', n.display_name || n.node_id) } } }, ignoreInput: true },
  { key: 'v', ctrl: true, handler: async () => { if (window.getSelection()?.toString()) return; const copy = (window as any).__copiedNode; if (copy && graphWs.graphModel) { const newNodeId = await graphWs.pasteNode(copy); if (newNodeId) { graphStore.selectNode(newNodeId); toast.info('已粘贴', copy.display_name || newNodeId) } } }, ignoreInput: true },
  { key: 'b', ctrl: true, handler: () => { const dock = useDockStore(); dock.restorePanel('components'); }, ignoreInput: true },
  { key: 'Delete', handler: () => {
    const sel = graphStore.selectedNode
    if (sel && graphWs.graphModel) {
      if (!shouldConfirmDeleteNode()) {
        graphWs.removeNode(sel)
        graphStore.selectNode(null)
        toast.success('已删除', sel)
        return
      }
      ;(window as any).__openDeleteConfirm?.(() => {
        graphWs.removeNode(sel)
        graphStore.selectNode(null)
        toast.success('已删除', sel)
      })
    }
  }, ignoreInput: true },
  { key: 'e', ctrl: true, handler: () => { const dock = useDockStore(); dock.restorePanel('source'); }, ignoreInput: true },
])

function beforeUnload(e: BeforeUnloadEvent) {
  if (graphWs.isDirty) {
    e.preventDefault()
    e.returnValue = ''
  }
}

/** Post-connection bootstrap: update check + full workspace restore. */
async function runWorkbenchBootstrap() {
  // Seed theme from the configured default (no-op if the user has a local override).
  theme.initFromConfig((workspace.snapshot?.preferences as any)?.program_settings?.theme)
  await updateStore.fetchStatus().catch(() => {})
  const shouldCheckUpdates = !!(workspace.snapshot?.preferences as any)?.program_settings?.check_updates_on_startup
  if (shouldCheckUpdates) {
    const status = await updateStore.checkForUpdates(false).catch(() => null)
    if (status?.update_available) {
      window.dispatchEvent(new CustomEvent('weconduct:update-available', { detail: status }))
    }
  }
  // Full workspace restore: if project already loaded, sync graph + source
  if (workspace.snapshot?.project?.loaded) {
    await graphWs.loadGraph()
    if (graphWs.graphModel && !compilation.sourceText.trim()) {
      await graphWs.syncSource()
    }
    const runtime = useRuntimeStore()
    await runtime.refreshAll()
  }
}

/** Attempt to connect; on failure, run startup diagnostics to drive the error screen. */
async function attemptStartup() {
  await workspace.initialize()
  if (workspace.connectionState === 'error') {
    await startup.diagnose(workspace.initError)
    return
  }
  startup.reset()
  await runWorkbenchBootstrap()
}

/** 重试 / 恢复后重启：clear connection state and re-run the whole startup flow. */
async function handleRestart() {
  forceStarted.value = false
  workspace.reset()
  startup.reset()
  await attemptStartup()
}

/** 强行启动（异常）：dismiss the blocking screen and proceed into the app. */
async function handleForceStart() {
  forceStarted.value = true
  startup.reset()
  await runWorkbenchBootstrap()
}

onMounted(async () => {
  await attemptStartup()
  window.addEventListener('beforeunload', beforeUnload)
})
onUnmounted(() => { window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <StartupErrorScreen
    v-if="startup.hasBlockingError"
    @restart="handleRestart"
    @force-start="handleForceStart"
  />
  <div v-else class="app-shell">
    <CommandBar />
    <main class="app-main">
      <router-view />
    </main>
    <StatusBar />
    <ToastContainer />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow: hidden;
}
</style>
