<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useThemeStore } from '@/stores/themeStore'
import { useDockStore } from '@/stores/dockStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import { useUpdateStore } from '@/stores/updateStore'
import {
  postProjectNew, postProjectOpen, postProjectSave, postProjectSaveAs,
  fetchProject, fetchGraphDocument, fetchRecentProjects, postRecentProjectRemove,
  postFileDialog, postReadFile, postGraphUpgradeApply, postGraphUpgradeRecheck,
} from '@/services/api'
import type { RecentProject, PendingGraphUpgrade } from '@/types/domains/api'
import WebControlConverter from '@/components/shells/WebControlConverter.vue'

const workspace = useWorkspaceStore()
const compilation = useCompilationStore()
const theme = useThemeStore()
const dock = useDockStore()
const graphWs = useGraphWorkspaceStore()
const runtime = useRuntimeStore()
const resource = useResourceStore()
const toast = useToastStore()
const updateStore = useUpdateStore()

/** Unified post-project-open state refresh: sync all stores */
async function applyOpenedProject() {
  await workspace.refreshSnapshot()
  compilation.clearSource() // prevent stale source from previous project
          graphWs.clearAllDrafts() // prevent old project drafts from leaking
          await graphWs.loadGraph(undefined, { forceRefresh: true })
  // Explicit sync (not just 800ms watcher delay)
  if (graphWs.graphModel) await graphWs.syncSource()
  runtime.refreshAll()
  resource.refreshAll()
  await graphWs.refreshGraphDocuments()
      const upgrade = workspace.snapshot?.project?.pending_graph_upgrade
    if (upgrade) { upgradeInfo.value = upgrade; showUpgradeDialog.value = true }
    closeDialog()
}

const activeMenu = ref<string | null>(null)
const activeDialog = ref<string | null>(null)
const dialogInput = ref('')
const dialogLoading = ref(false)
const recentProjects = ref<RecentProject[]>([])
function toggleMenu(menu: string) { activeMenu.value = activeMenu.value === menu ? null : menu }
function closeMenu() { activeMenu.value = null }
function closeDialog() { activeDialog.value = null }

const pendingConfirm = ref<(() => void) | null>(null)
const showConverter = ref(false)
const showUpgradeDialog = ref(false)
const upgradeInfo = ref<PendingGraphUpgrade | null>(null)

// Global watch: auto-show upgrade dialog when pending_graph_upgrade appears
watch(() => workspace.snapshot?.project?.pending_graph_upgrade, (pending) => {
  if (pending) { upgradeInfo.value = pending; showUpgradeDialog.value = true }
}, { immediate: true })

const dialogPath = ref('')
const defaultReleaseUrl = 'https://github.com/HalcyonAlcedo/WeConduct/releases'

function openReleasePage() {
  const releaseUrl = updateStore.status?.release_url || defaultReleaseUrl
  window.open(releaseUrl, '_blank', 'noopener,noreferrer')
}

function handleUpdateAvailable(event: Event) {
  const detail = (event as CustomEvent).detail as Record<string, unknown> | null
  const latestVersion = typeof detail?.latest_version === 'string' ? detail.latest_version : '未知版本'
  const currentVersion = typeof detail?.current_version === 'string'
    ? detail.current_version
    : (workspace.health?.api_version ?? '未知版本')
  toast.info(`发现新版本 ${latestVersion}`, `当前版本 ${currentVersion}`)
}

onMounted(() => {
  window.addEventListener('weconduct:update-available', handleUpdateAvailable as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('weconduct:update-available', handleUpdateAvailable as EventListener)
})

// Expose for keyboard-driven dialogs
;(window as any).__openDeleteConfirm = (cb: () => void) => { pendingConfirm.value = cb; openDialog('confirmDelete') }

async function doNew() {
  dialogLoading.value = true
  try {
    const body: any = { project_name: dialogInput.value || 'untitled' }
    if (dialogPath.value) body.project_directory = dialogPath.value
    const r = await postProjectNew(body)
    toast.success('已创建', r.project.project_name)
    // Clear cached data after new project
    compilation.clearSource()
    graphWs.reset()
    await workspace.refreshSnapshot()
    runtime.refreshAll()
    resource.refreshAll()
    await graphWs.refreshGraphDocuments()
        const upgrade = workspace.snapshot?.project?.pending_graph_upgrade
    if (upgrade) { upgradeInfo.value = upgrade; showUpgradeDialog.value = true }
    closeDialog()
  } catch(e:any){ toast.error('创建失败', e?.message) }
  finally { dialogLoading.value = false }
}
async function doOpen() { dialogLoading.value = true; try { await postProjectOpen({ project_path: dialogInput.value }); toast.success('已打开'); await applyOpenedProject() } catch(e:any){ toast.error('打开失败', e?.message) } finally { dialogLoading.value = false } }
const isWcrunPackage = computed(() => (workspace.snapshot as any)?.project_settings?.source_of_truth === 'wcrun_package')

/** Get the main graph model for project save, loading it if currently on a custom graph */
async function getMainGraphModel(): Promise<Record<string, unknown> | undefined> {
  if (!graphWs.isCustomComponentGraph) return graphWs.graphModel as Record<string, unknown> | undefined
  // Currently on a custom graph — fetch the main graph explicitly
  try {
    const doc = await fetchGraphDocument() // no document_id → main graph
    return doc.graph_model as unknown as Record<string, unknown> | undefined
  } catch { return undefined }
}

async function doSave() {
  if (isWcrunPackage.value) { toast.info('', '.wcrun 包只读 — 仅运行默认值可编辑'); return }
  dialogLoading.value = true
  try {
    const proj = await fetchProject()
    if (!proj.project.project_file_path) { closeDialog(); openDialog('saveas'); dialogLoading.value = false; return }
    const mainModel = await getMainGraphModel()
    await postProjectSave(mainModel)
    await workspace.refreshSnapshot()
    await graphWs.loadGraph(undefined, { forceRefresh: true }) // refresh view/saveRevision after project save
    toast.success('已保存');     const upgrade = workspace.snapshot?.project?.pending_graph_upgrade
    if (upgrade) { upgradeInfo.value = upgrade; showUpgradeDialog.value = true }
    closeDialog()
  } catch(e: any) {
    if (e?.body?.error === 'project.needs_save_as') { closeDialog(); openDialog('saveas') }
    else { toast.error('保存失败', e?.message) }
  }
  finally { dialogLoading.value = false }
}
async function doSaveAs() {
  if (isWcrunPackage.value) { toast.info('', '.wcrun 包只读 — 仅运行默认值可编辑'); return }
  dialogLoading.value = true
  try {
    const mainModel = await getMainGraphModel()
    await postProjectSaveAs({ project_path: dialogInput.value, graph_document: mainModel })
    await workspace.refreshSnapshot()
    await graphWs.loadGraph(undefined, { forceRefresh: true }) // refresh view/saveRevision after project save
    toast.success('已另存');     const upgrade = workspace.snapshot?.project?.pending_graph_upgrade
    if (upgrade) { upgradeInfo.value = upgrade; showUpgradeDialog.value = true }
    closeDialog()
  } catch(e:any){ toast.error('另存失败', e?.message) }
  finally { dialogLoading.value = false }
}
  async function handleGraphUpgrade(decision: 'upgrade_and_load' | 'force_load') {
    try {
      await postGraphUpgradeApply(decision)
      toast.success(decision === 'upgrade_and_load' ? '已升级' : '已强制加载')
      showUpgradeDialog.value = false
      await workspace.refreshSnapshot()
      await graphWs.loadGraph()
      if (graphWs.graphModel) await graphWs.syncSource()
      await graphWs.refreshGraphDocuments()
      runtime.refreshAll(); resource.refreshAll()
    } catch (e: any) { toast.error('操作失败', e?.message) }
  }
async function doOpenRecent(fp: string) { dialogLoading.value = true; try { await postProjectOpen({ project_path: fp }); toast.success('已打开'); await applyOpenedProject() } catch(e:any){ toast.error('打开失败', e?.message) } finally { dialogLoading.value = false } }
  async function handleManualGraphUpgrade() {
    closeMenu()
    try {
      const r = await postGraphUpgradeRecheck()
      if (r.pending_graph_upgrade) {
        upgradeInfo.value = r.pending_graph_upgrade
        showUpgradeDialog.value = true
        await workspace.refreshSnapshot()
        return
      }
      toast.info('', '当前项目没有待升级的节点图')
    } catch (e: any) {
      toast.error('重新检测失败', e?.message)
    }
  }
async function doRemoveRecent(fp: string) { try { await postRecentProjectRemove({ project_path: fp }); recentProjects.value = recentProjects.value.filter(r => r.project_path !== fp) } catch(e:any){ toast.error('移除失败', e?.message) } }

const projectLabel = computed(() => {
  if (!workspace.isConnected) return '未连接'
  const name = workspace.projectName ?? '未加载项目'
  return isWcrunPackage.value ? `📦 ${name} (只读)` : name
})

const connectionDotClass = computed(() => {
  switch (workspace.connectionState) {
    case 'connected': return 'dot-green'
    case 'connecting': return 'dot-yellow'
    case 'error': return 'dot-red'
    default: return 'dot-gray'
  }
})

async function handleOneClickRun() {
  // Ensure source is synced from graph first
  if (!compilation.sourceText.trim() && graphWs.graphModel) {
    await graphWs.syncSource()
  }
  if (!graphWs.hasGraph) { toast.info('', '当前图为空，请先添加节点'); return }
  // Auto-open task execution and output panels if not visible
  if (!dock.isPanelVisible('tasks')) dock.restorePanel('tasks')
  if (!dock.isPanelVisible('output')) dock.restorePanel('output')
  runtime.requestRuntimeTab()
  // Execute via runtime (not just compile)
  const result = await runtime.startAndRun(graphWs.graphModel as Record<string, unknown> | undefined, graphWs.isDirty)
  await resource.refreshAll()
  if (result.success) {
    toast.success('运行完成', result.message)
  } else {
    toast.error('运行失败', result.message)
  }
}

/** Open native file dialog and set path into dialogInput */
async function pickFile(mode: string) {
  try {
    const r = await postFileDialog({ mode, title: mode === 'save_file' ? '保存项目文件' : mode === 'open_folder' ? '选择项目目录' : '选择文件' })
    if (r.status === 'selected' && r.paths.length) dialogInput.value = r.paths[0]
  } catch (e: any) {
    if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器，请手动输入路径')
  }
}

/** Open native file dialog and set path into dialogPath (for project directory) */
async function pickFilePath(mode: string) {
  try {
    const r = await postFileDialog({ mode, title: '选择项目目录' })
    if (r.status === 'selected' && r.paths.length) dialogPath.value = r.paths[0]
  } catch (e: any) {
    if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器，请手动输入路径')
  }
}

const importJson = ref('')

async function doImportGraph() {
  if (!importJson.value.trim()) return
  dialogLoading.value = true
  try {
    const json = JSON.parse(importJson.value)
    await graphWs.saveGraph(json)
    toast.success('已导入', '节点图 JSON 已加载，画布已刷新')
    importJson.value = '';     const upgrade = workspace.snapshot?.project?.pending_graph_upgrade
    if (upgrade) { upgradeInfo.value = upgrade; showUpgradeDialog.value = true }
    closeDialog()
  } catch (e: any) { toast.error('导入失败', e?.message) }
  finally { dialogLoading.value = false }
}

/** Pick JSON file via native dialog, then read contents via backend */
async function pickImportFile() {
  try {
    const r = await postFileDialog({ mode: 'open_file', title: '选择节点图 JSON', file_types: ['JSON Files (*.json)'] })
    if (r.status === 'selected' && r.paths.length) {
      const file = await postReadFile({ path: r.paths[0], encoding: 'utf-8' })
      importJson.value = file.content
      toast.info('已加载', `${r.paths[0]} (${file.bytes_read} 字节)`)
    }
  } catch (e: any) {
    if (e?.status === 503) { toast.info('', '当前环境不支持文件选择器，请手动粘贴 JSON'); return }
    if (e?.body?.error) { toast.error('读取失败', e.body.message ?? e.body.error) }
  }
}

function openDialog(id: string) { activeDialog.value = id; dialogInput.value = ''; dialogPath.value = ''; importJson.value = ''; closeMenu()
  if (id === 'updateCheck') {
    updateStore.checkForUpdates(true).catch(() => {})
  }
  if (id === 'new') {
    const prefs: any = workspace.snapshot?.preferences || {}
    dialogPath.value = prefs?.program_settings?.default_project_directory || ''
  }
  if (id === 'recent') { fetchRecentProjects().then(r => recentProjects.value = r.recent_projects).catch(() => {}) }
}
</script>

<template>
  <header class="commandbar" role="banner">
    <!-- Menu Area -->
    <nav class="cmd-menu" aria-label="主菜单">
      <div class="cmd-menu-item" @mouseenter="activeMenu !== null ? activeMenu = 'file' : null">
        <button class="cmd-item" @click="toggleMenu('file')">文件</button>
        <div v-if="activeMenu === 'file'" class="cmd-dropdown" @mouseleave="closeMenu">
          <button @click="openDialog('new')">新建项目</button>
          <button @click="openDialog('open')">打开项目文件</button>
          <button @click="openDialog('recent')">最近项目</button>
          <hr>
          <button @click="openDialog('importGraph')">导入节点图 JSON</button>
          <button @click="closeMenu(); showConverter = true">转换 WebControl</button>
          <button @click="handleManualGraphUpgrade()">手动升级节点图</button>
          <hr>
          <button @click="dock.restorePanel('projectSettings'); closeMenu()">项目设置</button>
          <button @click="dock.restorePanel('packageManager'); closeMenu()">.wcrun 打包</button>
          <button @click="openDialog('save')">保存</button>
          <button @click="openDialog('saveas')">另存为</button>
          <hr>
          <button @click="dock.restorePanel('preferences'); closeMenu()">首选项</button>
        </div>
      </div>
      <div class="cmd-menu-item" @mouseenter="activeMenu !== null ? activeMenu = 'edit' : null">
        <button class="cmd-item" @click="toggleMenu('edit')">编辑</button>
        <div v-if="activeMenu === 'edit'" class="cmd-dropdown" @mouseleave="closeMenu">
          <button @click="graphWs.undo(); closeMenu()">撤销 Ctrl+Z</button>
          <button @click="graphWs.redo(); closeMenu()">重做 Ctrl+Y</button>
        </div>
      </div>
      <div class="cmd-menu-item" @mouseenter="activeMenu !== null ? activeMenu = 'view' : null">
        <button class="cmd-item" @click="toggleMenu('view')">视图</button>
        <div v-if="activeMenu === 'view'" class="cmd-dropdown" @mouseleave="closeMenu">
          <button v-for="p in dock.allPanels.filter(p => p.id !== 'preferences' && p.id !== 'projectSettings' && p.id !== 'packageManager')" :key="p.id" @click="dock.isPanelVisible(p.id) ? dock.closePanel(p.id) : dock.restorePanel(p.id); closeMenu()">
            {{ dock.isPanelVisible(p.id) ? '✓' : '○' }} {{ p.title }}
          </button>
          <hr>
          <button @click="dock.addToZone('graph','center'); dock.addToZone('components','left'); dock.addToZone('source','bottom'); dock.addToZone('output','bottom'); closeMenu()">恢复默认布局</button>
          <hr>
          <button @click="theme.toggle(); closeMenu()">
            {{ theme.mode === 'light' ? '深色主题' : '浅色主题' }}
          </button>
        </div>
      </div>
      <div class="cmd-menu-item" @mouseenter="activeMenu !== null ? activeMenu = 'compile' : null">
        <button class="cmd-item" @click="toggleMenu('compile')">编译</button>
        <div v-if="activeMenu === 'compile'" class="cmd-dropdown" @mouseleave="closeMenu">
          <button @click="handleOneClickRun(); closeMenu()">运行 Ctrl+Enter</button>
          <button @click="dock.restorePanel('preferences'); closeMenu()">编译选项</button>
        </div>
      </div>
      <div class="cmd-menu-item" @mouseenter="activeMenu !== null ? activeMenu = 'help' : null">
        <button class="cmd-item" @click="toggleMenu('help')">帮助</button>
        <div v-if="activeMenu === 'help'" class="cmd-dropdown" @mouseleave="closeMenu">
          <button @click="openDialog('about')">关于 WeConduct</button>
          <button @click="openDialog('updateCheck')">检查更新</button>
          <button @click="openDialog('shortcuts')">键盘快捷键</button>
        </div>
      </div>
    </nav>

    <!-- Toolbar Area -->
    <div class="cmd-toolbar" role="toolbar" aria-label="工具栏">
      <button class="tb-btn primary" :disabled="!graphWs.hasGraph" title="运行 (Ctrl+Enter)" @click="handleOneClickRun()">
        <span class="tb-icon">▶</span>
        运行
      </button>
      <span class="tb-brand">WeConduct</span>
      <span class="tb-divider"></span>
      <span class="tb-label">{{ projectLabel }}</span>
    </div>

    <!-- Right -->
    <div class="cmd-right">
      <button class="theme-btn" :title="theme.mode === 'light' ? '切换深色主题' : '切换浅色主题'" @click="theme.toggle()">
        {{ theme.mode === 'light' ? '☀' : '☾' }}
      </button>
      <span :class="['conn-dot', connectionDotClass]"></span>
      <span class="conn-text">{{ connectionDotClass === 'dot-green' ? '已连接' : '离线' }}</span>
    </div>

    <!-- Dialog Modals -->
    <Teleport to="body">
      <div v-if="activeDialog" class="dlg-overlay">
        <div class="dlg-box">
          <div class="dlg-header">
            <span class="dlg-title">
              <template v-if="activeDialog === 'new'">新建项目</template>
              <template v-else-if="activeDialog === 'open'">打开项目</template>
              <template v-else-if="activeDialog === 'recent'">最近项目</template>
              <template v-else-if="activeDialog === 'save'">保存</template>
              <template v-else-if="activeDialog === 'saveas'">另存为</template>
              <template v-else-if="activeDialog === 'about'">关于 WeConduct</template>
              <template v-else-if="activeDialog === 'updateCheck'">检查更新</template>
              <template v-else-if="activeDialog === 'importGraph'">导入节点图 JSON</template>
              <template v-else-if="activeDialog === 'confirmDelete'">确认删除</template>
              <template v-else-if="activeDialog === 'shortcuts'">键盘快捷键</template>
            </span>
            <button class="dlg-close" @click="closeDialog">✕</button>
          </div>
          <div class="dlg-body">
            <!-- New: project name + directory -->
            <template v-if="activeDialog === 'new'">
              <div class="dlg-field">
                <label class="dlg-field-lbl">项目名称</label>
                <input v-model="dialogInput" class="dlg-input" placeholder="输入项目名称" @keyup.enter="doNew()" />
              </div>
              <div class="dlg-field">
                <label class="dlg-field-lbl">项目目录</label>
                <div class="dlg-path-row">
                  <input v-model="dialogPath" class="dlg-input" placeholder="默认为系统首选项中的项目目录" @keyup.enter="doNew()" />
                  <button class="dlg-pick-btn" @click="pickFilePath('open_folder')" title="选择目录">📁</button>
                </div>
              </div>
              <div class="dlg-actions"><button class="dlg-act-btn" @click="doNew()" :disabled="dialogLoading">确定</button></div>
            </template>
            <!-- SaveAs: text input -->
            <template v-else-if="activeDialog === 'saveas'">
              <div class="dlg-path-row"><input v-model="dialogInput" class="dlg-input" placeholder="新文件路径，例如 I:\\...\\project.weconduct.json" @keyup.enter="doSaveAs()" /><button class="dlg-pick-btn" @click="pickFile('save_file')" title="选择文件">…</button></div>
              <div class="dlg-actions"><button class="dlg-act-btn" @click="doSaveAs()" :disabled="dialogLoading">确定</button></div>
            </template>
            <!-- Open: text input -->
            <template v-else-if="activeDialog === 'open'">
              <div class="dlg-path-row"><input v-model="dialogInput" class="dlg-input" placeholder="完整项目文件路径，例如 I:\\...\\project.weconduct.json" @keyup.enter="doOpen()" /><button class="dlg-pick-btn" @click="pickFile('open_file')" title="选择项目文件">…</button></div>
              <div class="dlg-actions"><button class="dlg-act-btn" @click="doOpen" :disabled="dialogLoading">打开项目文件</button></div>
            </template>
            <!-- Import Graph -->
            <template v-else-if="activeDialog === 'importGraph'">
              <div class="dlg-path-row"><button class="dlg-pick-btn" @click="pickImportFile">选择 JSON 文件…</button></div>
              <textarea v-model="importJson" class="dlg-textarea" placeholder="在此粘贴节点图 JSON（GraphModel），或点击上方按钮选择 JSON 文件..." rows="8"></textarea>
              <div class="dlg-actions"><button class="dlg-act-btn" @click="doImportGraph" :disabled="dialogLoading || !importJson.trim()">导入</button></div>
            </template>
            <!-- Save: confirm -->
            <template v-else-if="activeDialog === 'save'">
              <p>保存当前项目</p>
              <div class="dlg-actions"><button class="dlg-act-btn" @click="doSave" :disabled="dialogLoading">保存</button></div>
            </template>
            <!-- Recent -->
            <template v-else-if="activeDialog === 'recent'">
              <div v-if="!recentProjects.length" class="dlg-meta">暂无最近项目</div>
              <div v-for="r in recentProjects" :key="r.project_path" class="dlg-recent-row">
                <div class="dlg-recent-info" @click="doOpenRecent(r.project_path)">
                  <span class="dlg-recent-name">{{ r.project_name }}</span>
                  <span class="dlg-recent-path" :title="r.project_path">{{ r.project_path }}</span>
                </div>
                <button class="dlg-recent-rm" @click.stop="doRemoveRecent(r.project_path)" title="从列表中移除">✕</button>
              </div>
            </template>
            <!-- About -->
            <template v-else-if="activeDialog === 'about'">
              <p><strong>WeConduct</strong></p>
              <p class="dlg-meta">版本: {{ workspace.health?.api_version ?? '0.7.3' }}</p>
              <p class="dlg-meta">更新状态: {{ updateStore.status?.check_status ?? 'idle' }}</p>
              <p class="dlg-meta">最新版本: {{ updateStore.status?.latest_version ?? '—' }}</p>
              <p class="dlg-meta">最近检查: {{ updateStore.status?.last_checked_at ?? '—' }}</p>
              <p class="dlg-meta">运行模式: {{ workspace.health?.host_mode ?? '—' }}</p>
              <p class="dlg-meta">工作区会话: {{ workspace.health?.workspace_session_id ?? '—' }}</p>
              <div class="dlg-actions">
                <button class="dlg-act-btn" @click="openReleasePage">打开发布页面</button>
              </div>
              <template v-if="workspace.projectName">
                <hr class="dlg-hr">
                <p class="dlg-meta"><strong>项目: {{ workspace.projectName }}</strong></p>
                <p class="dlg-meta">Schema: {{ workspace.projectFileSchemaVersion || workspace.snapshot?.project?.project_file_schema_version || '—' }}</p>
                <p class="dlg-meta">类型: {{ workspace.isDirectoryProject ? '目录化项目 (新)' : '单体文件 (旧)' }}</p>
                <p class="dlg-meta" v-if="workspace.mainGraphPath">主图: {{ workspace.mainGraphPath }}</p>
                <p class="dlg-meta" v-if="workspace.projectResourcesIndexPath">资源索引: {{ workspace.projectResourcesIndexPath }}</p>
              </template>
            </template>
            <template v-else-if="activeDialog === 'updateCheck'">
              <p class="dlg-meta">当前版本: {{ updateStore.status?.current_version ?? workspace.health?.api_version ?? '—' }}</p>
              <p class="dlg-meta">最新版本: {{ updateStore.status?.latest_version ?? '—' }}</p>
              <p class="dlg-meta">状态: {{ updateStore.isChecking ? 'checking' : (updateStore.status?.check_status ?? 'idle') }}</p>
              <p class="dlg-meta">最近检查: {{ updateStore.status?.last_checked_at ?? '—' }}</p>
              <p class="dlg-meta" v-if="updateStore.status?.check_error">错误: {{ updateStore.status?.check_error }}</p>
              <div class="dlg-actions">
                <button class="dlg-act-btn" @click="updateStore.checkForUpdates(true)" :disabled="updateStore.isChecking">
                  {{ updateStore.isChecking ? '检查中…' : '重新检查' }}
                </button>
                <button class="dlg-act-btn" @click="openReleasePage">打开发布页面</button>
              </div>
            </template>
            <!-- Confirm Delete -->
            <template v-else-if="activeDialog === 'confirmDelete'">
              <p>确定删除选中的节点及其关联连线？此操作可撤销。</p>
              <div class="dlg-actions">
                <button class="dlg-act-btn" style="background:var(--state-error);border-color:var(--state-error)" @click="pendingConfirm?.(); closeDialog()">删除</button>
                <button class="dlg-act-btn" style="background:transparent;color:var(--text-secondary);border-color:var(--border-default)" @click="closeDialog()">取消</button>
              </div>
            </template>
            <!-- Shortcuts -->
            <template v-else-if="activeDialog === 'shortcuts'">
              <div class="dlg-kv"><kbd>Ctrl+Enter</kbd><span>运行</span></div>
              <div class="dlg-kv"><kbd>Ctrl+Z</kbd><span>撤销</span></div>
              <div class="dlg-kv"><kbd>Ctrl+Y</kbd><span>重做</span></div>
              <div class="dlg-kv"><kbd>Ctrl+K</kbd><span>清空源输入</span></div>
              <div class="dlg-kv"><kbd>Ctrl+S</kbd><span>保存</span></div>
              <div class="dlg-kv"><kbd>Ctrl+O</kbd><span>打开项目</span></div>
              <div class="dlg-kv"><kbd>Ctrl+N</kbd><span>新建项目</span></div>
              <div class="dlg-kv"><kbd>Ctrl+B</kbd><span>打开组件库</span></div>
              <div class="dlg-kv"><kbd>Ctrl+E</kbd><span>打开源输入</span></div>
            </template>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- WebControl Converter -->
    <WebControlConverter v-if="showConverter" @close="showConverter = false" />
    <Teleport to="body"><div v-if="showUpgradeDialog" class="upg-overlay"><div class="upg-box"><div class="upg-hd">节点图版本升级</div><div class="upg-body"><p>图数据版本 <strong>{{ upgradeInfo?.compatibility?.graph_data_version }}</strong> → 程序版本 <strong>{{ upgradeInfo?.compatibility?.current_app_version }}</strong></p><p class="upg-meta">创建时版本: {{ upgradeInfo?.compatibility?.built_with_app_version }} · 最低加载: {{ upgradeInfo?.compatibility?.minimum_loader_app_version }}</p><div v-if="upgradeInfo?.documents?.length"><p class="upg-meta">涉及文档:</p><div v-for="d in upgradeInfo.documents" :key="d.document_id" class="upg-doc-item">{{ d.display_name || d.document_id }} <small>({{ d.document_role }})</small></div></div><template v-if="upgradeInfo?.status === 'upgrade_available'"><div class="upg-actions"><button class="upg-btn upg-btn-primary" @click="handleGraphUpgrade('upgrade_and_load')">升级并加载</button><button class="upg-btn" @click="handleGraphUpgrade('force_load')">跳过升级</button></div></template><template v-else><div class="upg-actions"><button class="upg-btn upg-btn-primary" @click="handleGraphUpgrade('force_load')">强制加载</button><button class="upg-btn" @click="showUpgradeDialog = false">取消</button></div></template></div></div></div></Teleport>
  </header>
</template>

<style scoped>
.commandbar {
  display: flex; align-items: center;
  height: var(--commandbar-height); background: var(--bg-commandbar);
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 var(--space-md); gap: var(--space-lg); flex-shrink: 0; user-select: none;
  -webkit-app-region: drag;
}

.cmd-menu { display: flex; gap: 2px; -webkit-app-region: no-drag; position: relative; }

.cmd-menu-item { position: relative; }

.cmd-item {
  padding: 4px 10px; border: none; background: transparent;
  color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-body);
  cursor: pointer; border-radius: var(--radius-sm); line-height: 1.4;
}
.cmd-item:hover { background: var(--bg-hover); }

.cmd-dropdown {
  position: absolute; top: 100%; left: 0; z-index: 100;
  min-width: 180px; background: var(--bg-panel);
  border: 1px solid var(--border-default); border-radius: var(--radius-md);
  box-shadow: var(--shadow-menu); padding: var(--space-xs);
}
.cmd-dropdown button {
  display: block; width: 100%; padding: 5px 10px; border: none; background: transparent;
  color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-body);
  cursor: pointer; border-radius: var(--radius-sm); text-align: left; line-height: 1.4;
}
.cmd-dropdown button:hover { background: var(--bg-hover); }
.cmd-dropdown hr { margin: var(--space-xs) 0; border: none; border-top: 1px solid var(--border-subtle); }

.cmd-toolbar { display: flex; align-items: center; gap: var(--space-sm); flex: 1; -webkit-app-region: no-drag; }

.tb-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px;
  border: 1px solid var(--border-default); background: var(--bg-panel);
  color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-body);
  cursor: pointer; border-radius: var(--radius-sm); line-height: 1.4;
  transition: background 100ms var(--ease-out);
}
.tb-btn:hover:not(:disabled) { background: var(--bg-hover); }
.tb-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tb-btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.tb-btn.primary:hover:not(:disabled) { background: var(--accent-hover); }

.tb-icon { font-size: 10px; }
.tb-divider { width: 1px; height: 20px; background: var(--border-default); }
.tb-brand { font-size: var(--text-body); font-weight: 700; color: var(--text-primary); letter-spacing: 0.02em; }
.tb-label { font-size: var(--text-body); color: var(--text-secondary); }

.cmd-right { display: flex; align-items: center; gap: var(--space-xs); flex-shrink: 0; -webkit-app-region: no-drag; }

.conn-dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-green  { background: var(--state-success); }
.dot-yellow { background: var(--state-warning); }
.dot-red    { background: var(--state-error); }
.dot-gray   { background: var(--text-disabled); }
.conn-text { font-size: var(--text-small); color: var(--text-secondary); }

.theme-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-default); background: var(--bg-panel);
  border-radius: var(--radius-sm); cursor: pointer; font-size: 11px; font-weight: 600;
  line-height: 1; margin-right: var(--space-sm); transition: background 100ms var(--ease-out);
  font-family: var(--font-ui); color: var(--text-secondary);
}
.theme-btn:hover { background: var(--bg-hover); }

/* Dialog overlay */
.dlg-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center;
}
.dlg-box {
  background: var(--bg-panel); border: 1px solid var(--border-default);
  border-radius: var(--radius-lg); min-width: 360px; max-width: 500px;
  box-shadow: var(--shadow-menu);
}
.dlg-header {
  display: flex; align-items: center; padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--border-subtle);
}
.dlg-title { font-size: var(--text-body); font-weight: 600; color: var(--text-primary); }
.dlg-close { margin-left: auto; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; cursor: pointer; color: var(--text-disabled); font-size: 12px; border-radius: var(--radius-sm); }
.dlg-close:hover { background: var(--bg-hover); color: var(--text-primary); }
.dlg-body { padding: var(--space-lg); font-size: var(--text-body); color: var(--text-secondary); }
.dlg-meta { font-size: var(--text-small); color: var(--text-disabled); margin-top: var(--space-xs); }
.dlg-about p { margin-bottom: var(--space-xs); }
.dlg-hr { margin: var(--space-sm) 0; border: none; border-top: 1px solid var(--border-subtle); }
.dlg-shortcuts { display: flex; flex-direction: column; gap: var(--space-sm); }
.dlg-kv { display: flex; gap: var(--space-lg); align-items: center; }
.dlg-kv kbd { padding: 2px 8px; background: var(--bg-panel-header); border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: var(--text-small); color: var(--text-primary); }
.dlg-placeholder p { margin-bottom: var(--space-xs); }
.dlg-input { width: 100%; padding: 4px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-body); margin-bottom: var(--space-sm); }
.dlg-actions { display: flex; gap: var(--space-sm); }
.dlg-act-btn { padding: 4px 16px; border: 1px solid var(--accent); background: var(--accent); color: #fff; cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); }
.dlg-act-btn:hover:not(:disabled) { background: var(--accent-hover); }
.dlg-act-btn:disabled { opacity: 0.5; }
.dlg-recent-row { display: flex; align-items: center; gap: var(--space-sm); padding: 6px 8px; border-radius: var(--radius-sm); transition: background 80ms; }
.dlg-recent-row:hover { background: var(--bg-hover); }
.dlg-recent-row + .dlg-recent-row { border-top: 1px solid var(--border-subtle); }
.dlg-recent-info { flex: 1; min-width: 0; cursor: pointer; }
.dlg-recent-info:hover .dlg-recent-name { color: var(--accent); }
.dlg-recent-name { display: block; font-size: var(--text-body); font-weight: 500; color: var(--text-primary); line-height: 1.4; }
.dlg-recent-path { display: block; font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; margin-top: 1px; }
.dlg-recent-rm { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; border-radius: var(--radius-sm); flex-shrink: 0; }
.dlg-recent-rm:hover { color: var(--state-error); background: rgba(208,112,96,0.08); }
.dlg-sm-btn { width: 18px; height: 18px; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; border-radius: 2px; }
.dlg-sm-btn:hover { color: var(--state-error); background: rgba(208,112,96,0.08); }
.dlg-path-row { display: flex; gap: var(--space-xs); margin-bottom: var(--space-sm); }
.dlg-path-row .dlg-input { flex: 1; margin-bottom: 0; }
.dlg-pick-btn { padding: 4px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); }
.dlg-pick-btn:hover { background: var(--bg-hover); }
.dlg-textarea { width: 100%; padding: 6px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-mono); font-size: 12px; resize: vertical; margin-bottom: var(--space-sm); }
.dlg-field { margin-bottom: var(--space-sm); }
.dlg-field-lbl { display: block; font-size: var(--text-small); color: var(--text-secondary); margin-bottom: 2px; }
.dlg-field .dlg-path-row { margin-bottom: 0; }
.dlg-field .dlg-input { margin-bottom: 0; }

</style>

<!-- Upgrade dialog styles: non-scoped so Teleport renders correctly -->
<style>
.upg-overlay {
  position: fixed; inset: 0; z-index: 4000;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
}
.upg-box {
  background: var(--bg-panel);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  min-width: 360px; max-width: 480px;
  box-shadow: var(--shadow-menu);
}
.upg-hd {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  font-weight: 600; color: var(--accent);
}
.upg-body { padding: 12px 14px; font-size: var(--text-small); }
.upg-actions { display: flex; gap: 8px; margin-top: 12px; }
.upg-btn {
  padding: 4px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  cursor: pointer; font-size: var(--text-small);
}
.upg-btn-primary {
  border-color: var(--accent);
  background: var(--accent); color: #fff;
}
.upg-meta { font-size: var(--text-caption); color: var(--text-disabled); margin-top: 4px; }
.upg-doc-item { font-size: var(--text-caption); padding: 2px 0; }
</style>
