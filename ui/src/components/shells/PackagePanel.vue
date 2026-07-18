<script setup lang="ts">
import { ref, computed } from 'vue'
import { postPackagePreflight, postPackageBuild, fetchPackageInspect, postPackageLoad, postPackageUnload, postPackageBindExternal, postFileDialog, postSecurityEnableRequired } from '@/services/api'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import { t } from '@/i18n'
import type { PackagePreflightResponse, SecurityRequirementSummary, PackageBuildResult, LoadResultSummary } from '@/types/domains/api'

const workspace = useWorkspaceStore()
const graphWs = useGraphWorkspaceStore()
const compilation = useCompilationStore()
const runtime = useRuntimeStore()
const resource = useResourceStore()
const toast = useToastStore()

const active = ref<'preflight' | 'inspect' | 'bind'>('preflight')
const packagePath = ref('')
const outputPath = ref('')
const loading = ref('')
const preflightResult = ref<PackagePreflightResponse | null>(null)
const buildResult = ref<PackageBuildResult | null>(null)
const inspectResult = ref<Record<string, unknown> | null>(null)
const loadResult = ref<LoadResultSummary | null>(null)
const bindResourceId = ref('')
const bindValue = ref('')

const secDialog = ref<SecurityRequirementSummary | null>(null)
const secEnabling = ref(false)

function dismissSecDialog() { secDialog.value = null }
async function enableSecurityAndClose() {
  secEnabling.value = true
  try {
    await postSecurityEnableRequired({ confirm_high_risk: true })
    toast.success(t('framework.packageManager.toast.securityEnabled', '已放行该包所需权限'))
    await workspace.refreshSnapshot()
    secDialog.value = null
  } catch (e: any) {
    toast.error(t('framework.packageManager.toast.securityEnableFailed', '放行失败'), e?.message)
  } finally { secEnabling.value = false }
}

function resolveDefaultOutputPath() {
  const snapshot = workspace.snapshot as any
  const projectFilePath = typeof snapshot?.project?.project_file_path === 'string'
    ? snapshot.project.project_file_path
    : ''
  const defaultOutputName = typeof snapshot?.project_settings?.package_default_output_name === 'string'
    ? snapshot.project_settings.package_default_output_name
    : typeof snapshot?.project_settings?.packaging?.default_output_name === 'string'
      ? snapshot.project_settings.packaging.default_output_name
      : ''
  if (projectFilePath && defaultOutputName) {
    const slashIndex = Math.max(projectFilePath.lastIndexOf('\\'), projectFilePath.lastIndexOf('/'))
    if (slashIndex >= 0) return `${projectFilePath.slice(0, slashIndex + 1)}${defaultOutputName}`
  }
  return outputPath.value || defaultOutputName || ''
}

async function pickFile(target: 'package' | 'output') {
  try {
    const r = await postFileDialog({
      mode: target === 'package' ? 'open_file' : 'save_file',
      title: target === 'package' ? t('framework.packageManager.fileDialog.pickWcrun', '选择 .wcrun 文件') : t('framework.packageManager.fileDialog.pickOutput', '选择 .wcrun 输出路径'),
      default_path: target === 'output' ? resolveDefaultOutputPath() : outputPath.value || '',
      file_types: target === 'output' ? ['WeConduct Runtime Package (*.wcrun)'] : ['WeConduct Runtime Package (*.wcrun)'],
    })
    if (r.status === 'selected' && r.paths.length) {
      if (target === 'package') packagePath.value = r.paths[0]
      else outputPath.value = r.paths[0]
    }
  } catch { toast.info('', t('framework.packageManager.toast.fileDialogUnavailable', '文件选择器不可用')) }
}

async function doPreflight() {
  loading.value = 'preflight'
  try {
    preflightResult.value = await postPackagePreflight({
      mode: 'wcrun',
      source_of_truth: 'saved_project_only',
    })
    toast.success(t('framework.packageManager.toast.preflightDone', '校验完成'), preflightResult.value.summary.blocking ? t('framework.packageManager.toast.hasBlocking', '存在阻断项') : t('framework.packageManager.toast.passed', '通过'))
  }
  catch (e: any) { toast.error(t('framework.packageManager.toast.preflightFailed', '校验失败'), e?.message) }
  finally { loading.value = '' }
}

function fmtBytes(b?: number): string {
  if (b == null) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

async function doBuild() {
  if (!outputPath.value) { toast.info('', t('framework.packageManager.toast.selectOutputPath', '请选择输出路径')); return }
  loading.value = 'build'
  try {
    buildResult.value = await postPackageBuild({ output_path: outputPath.value, mode: 'wcrun', source_of_truth: 'saved_project_only' })
    toast.success(t('framework.packageManager.toast.buildDone', '打包完成'), buildResult.value.package?.output_path || '')
  } catch (e: any) { toast.error(t('framework.packageManager.toast.buildFailed', '打包失败'), e?.message); buildResult.value = null }
  finally { loading.value = '' }
}

async function doInspect() {
  if (!packagePath.value) { toast.info('', t('framework.packageManager.toast.selectWcrunFile', '请选择 .wcrun 文件')); return }
  loading.value = 'inspect'
  inspectResult.value = null
  try { inspectResult.value = await fetchPackageInspect(packagePath.value) as unknown as Record<string, unknown>; toast.success(t('framework.packageManager.toast.inspectDone', '检查完成')) }
  catch (e: any) { toast.error(t('framework.packageManager.toast.inspectFailed', '检查失败'), e?.message); inspectResult.value = null }
  finally { loading.value = '' }
}

async function doLoad() {
  if (!packagePath.value) { toast.info('', t('framework.packageManager.toast.selectWcrunFile', '请选择 .wcrun 文件')); return }
  loading.value = 'load'
  loadResult.value = null
  try {
    const result = await postPackageLoad(packagePath.value)
    // Check security requirements FIRST — before any async ops that could throw and skip this check
    const secSummary = result.security_requirement_summary
    if (secSummary && !secSummary.ready) {
      secDialog.value = secSummary
    }
    await workspace.refreshSnapshot()
    compilation.clearSource() // clear stale source BEFORE loading new graph
    await graphWs.loadGraph()
    if (graphWs.graphModel) await graphWs.syncSource()
    runtime.refreshAll()
    resource.refreshAll()
    loadResult.value = result.load_result_summary || null
    toast.success(t('framework.packageManager.toast.loaded', '已加载'), t('framework.packageManager.toast.workspaceSwitched', '工作区已切换为 wcrun_package'))
  } catch (e: any) { toast.error(t('framework.packageManager.toast.loadFailed', '加载失败'), e?.message); loadResult.value = null }
  finally { loading.value = '' }
}

async function doUnload() {
  loading.value = 'unload'
  try {
    await postPackageUnload()
    await workspace.refreshSnapshot()
    compilation.clearSource()
    await graphWs.loadGraph()
    if (graphWs.graphModel) await graphWs.syncSource()
    runtime.refreshAll()
    resource.refreshAll()
    inspectResult.value = null; loadResult.value = null
    toast.success(t('framework.packageManager.toast.unloaded', '已卸载'))
  } catch (e: any) { toast.error(t('framework.packageManager.toast.unloadFailed', '卸载失败'), e?.message) }
  finally { loading.value = '' }
}

async function doBind() {
  if (!bindResourceId.value || !bindValue.value) { toast.info('', t('framework.packageManager.toast.fillResourceIdAndValue', '请填写 resource_id 和值')); return }
  loading.value = 'bind'
  try {
    await postPackageBindExternal({ resource_id: bindResourceId.value, value: bindValue.value })
    toast.success(t('framework.packageManager.toast.bound', '已绑定'))
    await workspace.refreshSnapshot()
    bindResourceId.value = ''; bindValue.value = ''
  } catch (e: any) { toast.error(t('framework.packageManager.toast.bindFailed', '绑定失败'), e?.message) }
  finally { loading.value = '' }
}

const sourceLabel = computed(() => (workspace.snapshot as any)?.project_settings?.source_of_truth === 'wcrun_package' ? t('framework.packageManager.header.sourceWcrun', '📦 .wcrun 包') : t('framework.packageManager.header.sourceProject', '📁 项目'))
const isWcrun = computed(() => (workspace.snapshot as any)?.project_settings?.source_of_truth === 'wcrun_package')

const isBuilding = computed(() => loading.value === 'build')
const isLoadingPackage = computed(() => loading.value === 'load')
const busyTitle = computed(() => isBuilding.value ? t('framework.packageManager.busy.buildingTitle', '正在构建 .wcrun 包') : t('framework.packageManager.busy.loadingTitle', '正在加载 .wcrun 包'))
const busyDesc = computed(() => isBuilding.value ? t('framework.packageManager.busy.buildingDesc', '正在收集项目数据并写入包文件，请稍候') : t('framework.packageManager.busy.loadingDesc', '正在读取包内容并恢复运行会话，请稍候'))

</script>
<template>
  <div class="pkp-root">
    <div class="pkp-box">
        <div class="pkp-hd">
          <span>{{ t('framework.packageManager.header.title', '.wcrun 包管理') }}</span>
          <span class="pkp-source">{{ sourceLabel }}</span>
        </div>
        <div class="pkp-body">
          <div class="pkp-nav">
            <button :class="['pkp-nav-item', { active: active === 'preflight' }]" @click="active = 'preflight'">{{ t('framework.packageManager.nav.preflight', '校验 & 构建') }}</button>
            <button :class="['pkp-nav-item', { active: active === 'inspect' }]" @click="active = 'inspect'">{{ t('framework.packageManager.nav.inspect', '检查 & 加载') }}</button>
            <button :class="['pkp-nav-item', { active: active === 'bind' }]" @click="active = 'bind'">{{ t('framework.packageManager.nav.bind', '外部绑定') }}</button>
          </div>
          <div class="pkp-content">
            <!-- Busy indicator -->
            <div v-if="isBuilding || isLoadingPackage" class="pkp-busy">
              <div class="pkp-busy-bar"><div class="pkp-busy-track" /></div>
              <div class="pkp-busy-title">{{ busyTitle }}</div>
              <div class="pkp-busy-desc">{{ busyDesc }}</div>
            </div>
            <!-- Preflight & Build -->
            <template v-if="active === 'preflight'">
              <button class="pkp-btn" @click="doPreflight" :disabled="!!loading">{{ t('framework.packageManager.preflight.runButton', '🔍 打包前校验') }}</button>
              <div v-if="preflightResult" class="pkp-result">
                <div class="pkp-summary">
                  <span :class="preflightResult.summary.blocking ? 'pkp-block' : 'pkp-ok'">{{ preflightResult.summary.blocking ? t('framework.packageManager.preflight.blocking', '⛔ 有阻断') : t('framework.packageManager.preflight.passed', '✅ 通过') }}</span>
                  <span>{{ t('framework.packageManager.preflight.errors', '错误') }} {{ preflightResult.summary.error_count }} · {{ t('framework.packageManager.preflight.warnings', '警告') }} {{ preflightResult.summary.warning_count }} · {{ t('framework.packageManager.preflight.info', '信息') }} {{ preflightResult.summary.info_count ?? 0 }}</span>
                </div>
                <div v-for="e in preflightResult.entries" :key="e.diagnostic_id" class="pkp-entry" :class="'sev-'+e.severity">
                  <span class="pkp-entry-sev">{{ e.severity }}</span>
                  <span class="pkp-entry-msg">{{ e.message }}</span>
                  <span v-if="e.node_id" class="pkp-entry-ref">→ {{ e.node_id }}</span>
                  <span v-else-if="e.setting_field" class="pkp-entry-ref">→ {{ e.setting_field }}</span>
                  <span v-else-if="e.resource_id" class="pkp-entry-ref">→ {{ e.resource_id }}</span>
                </div>
              </div>
              <hr style="margin:12px 0;border-color:var(--border-subtle)">
              <div class="pkp-row"><input v-model="outputPath" class="pkp-input" :placeholder="t('framework.packageManager.build.outputPathPlaceholder', '输出路径，如 I:\\output\\demo.wcrun')" /><button class="pkp-pick" @click="pickFile('output')">…</button></div>
              <button class="pkp-btn pkp-btn-build" @click="doBuild" :disabled="!!loading">{{ t('framework.packageManager.build.buildButton', '📦 构建 .wcrun') }}</button>
              <!-- Build result block -->
              <div v-if="buildResult" class="pkp-result" style="margin-top:12px">
                <div class="pkp-summary"><span class="pkp-ok">{{ t('framework.packageManager.buildResult.success', '✅ 构建成功') }}</span></div>
                <div class="pkp-info-grid">
                  <div><span>{{ t('framework.packageManager.buildResult.outputPath', '输出路径') }}</span><code class="pkp-info-path">{{ buildResult.package?.output_path || buildResult.output_path || '—' }}</code></div>
                  <div><span>{{ t('framework.packageManager.buildResult.packageSize', '包大小') }}</span><code>{{ fmtBytes(buildResult.package?.written_bytes) }}</code></div>
                  <div><span>{{ t('framework.packageManager.buildResult.entryCount', '条目数') }}</span><code>{{ buildResult.package?.entry_count ?? '—' }}</code></div>
                  <div v-if="buildResult.package_info"><span>{{ t('framework.packageManager.buildResult.packageVersion', '包版本') }}</span><code>{{ buildResult.package_info.package_version || '—' }}</code></div>
                  <div v-if="buildResult.package_summary?.package_identity"><span>{{ t('framework.packageManager.buildResult.packageName', '包名') }}</span><code>{{ buildResult.package_summary.package_identity.package_name || '—' }}</code></div>
                  <div v-if="buildResult.package_summary?.entrypoint"><span>{{ t('framework.packageManager.buildResult.entrypointGraph', '入口图') }}</span><code>{{ buildResult.package_summary.entrypoint.graph_id || '—' }}</code></div>
                  <div v-if="buildResult.package_summary?.graph_summary"><span>{{ t('framework.packageManager.buildResult.graphCount', '图数量') }}</span><code>{{ buildResult.package_summary.graph_summary.graph_count ?? '—' }} {{ t('framework.packageManager.buildResult.graphUnit', '张') }}</code></div>
                  <div v-if="buildResult.resource_summary"><span>{{ t('framework.packageManager.buildResult.resources', '资源') }}</span><code>Embedded {{ buildResult.resource_summary.embedded_resource_count ?? '—' }} · External {{ buildResult.resource_summary.external_resource_count ?? '—' }}</code></div>
                  <div v-if="buildResult.dependency_summary"><span>{{ t('framework.packageManager.buildResult.components', '组件') }}</span><code>{{ t('framework.packageManager.buildResult.builtin', '内置') }} {{ buildResult.dependency_summary.builtin_component_count ?? '—' }} · {{ t('framework.packageManager.buildResult.custom', '自定义') }} {{ buildResult.dependency_summary.custom_component_count ?? '—' }}</code></div>
                </div>
              </div>
            </template>

            <!-- Inspect & Load -->
            <template v-else-if="active === 'inspect'">
              <div class="pkp-row"><input v-model="packagePath" class="pkp-input" :placeholder="t('framework.packageManager.inspect.pathPlaceholder', '.wcrun 文件路径')" /><button class="pkp-pick" @click="pickFile('package')">…</button></div>
              <div class="pkp-actions">
                <button class="pkp-btn" @click="doInspect" :disabled="!!loading">{{ t('framework.packageManager.inspect.inspectButton', '🔍 检查') }}</button>
                <button class="pkp-btn pkp-btn-build" @click="doLoad" :disabled="!!loading">{{ t('framework.packageManager.inspect.loadButton', '📥 加载') }}</button>
                <button v-if="isWcrun" class="pkp-btn pkp-btn-unload" @click="doUnload" :disabled="!!loading">{{ t('framework.packageManager.inspect.unloadButton', '📤 卸载') }}</button>
              </div>
              <!-- Inspect result -->
              <div v-if="inspectResult" class="pkp-result">
                <div class="pkp-summary"><span class="pkp-ok">{{ t('framework.packageManager.inspectResult.done', '检查完成') }}</span></div>
                <div class="pkp-info-grid">
                  <div v-if="(inspectResult.package_summary as any)?.package_identity"><span>{{ t('framework.packageManager.inspectResult.packageName', '包名') }}</span><code>{{ (inspectResult.package_summary as any).package_identity.package_name || '—' }} v{{ (inspectResult.package_summary as any).package_identity.package_version || '—' }}</code></div>
                  <div v-if="(inspectResult.package_summary as any)?.entrypoint"><span>{{ t('framework.packageManager.inspectResult.entrypointGraph', '入口图') }}</span><code>{{ (inspectResult.package_summary as any).entrypoint.graph_id || '—' }}</code></div>
                  <div v-if="inspectResult.graph_detail_summary"><span>{{ t('framework.packageManager.inspectResult.graphDetail', '图详情') }}</span><code>{{ t('framework.packageManager.inspectResult.graphLabel', '图') }} {{ (inspectResult.graph_detail_summary as any).graph_count ?? '—' }} · {{ t('framework.packageManager.inspectResult.customGraph', '自定义图') }} {{ (inspectResult.graph_detail_summary as any).custom_component_graph_count ?? '—' }}</code></div>
                  <div v-if="inspectResult.resource_summary"><span>{{ t('framework.packageManager.inspectResult.resources', '资源') }}</span><code>Embedded {{ (inspectResult.resource_summary as any).embedded_resource_count ?? '—' }} · External {{ (inspectResult.resource_summary as any).external_resource_count ?? '—' }} · {{ t('framework.packageManager.inspectResult.customComponent', '自定义组件') }} {{ (inspectResult.resource_summary as any).custom_component_count ?? '—' }}</code></div>
                  <div v-if="inspectResult.dependency_summary"><span>{{ t('framework.packageManager.inspectResult.dependencies', '依赖') }}</span><code>{{ t('framework.packageManager.buildResult.builtin', '内置') }} {{ (inspectResult.dependency_summary as any).builtin_component_count ?? '—' }} · {{ t('framework.packageManager.buildResult.custom', '自定义') }} {{ (inspectResult.dependency_summary as any).custom_component_count ?? '—' }}</code></div>
                  <div v-if="(inspectResult.runtime_readiness_summary as any)"><span>{{ t('framework.packageManager.inspectResult.runtimeReady', '运行就绪') }}</span><code :class="(inspectResult.runtime_readiness_summary as any).ready ? 'pkp-ok' : 'pkp-block'">{{ (inspectResult.runtime_readiness_summary as any).ready ? t('framework.packageManager.common.yes', '✅ 是') : t('framework.packageManager.common.no', '⛔ 否') }}</code></div>
                </div>
              </div>
              <!-- Load result -->
              <div v-if="loadResult" class="pkp-result" style="margin-top:12px">
                <div class="pkp-summary"><span class="pkp-ok">{{ t('framework.packageManager.loadResult.loaded', '✅ 已加载') }}</span></div>
                <div class="pkp-info-grid">
                  <div><span>{{ t('framework.packageManager.loadResult.packagePath', '包路径') }}</span><code class="pkp-info-path">{{ loadResult.package_path || '—' }}</code></div>
                  <div><span>{{ t('framework.packageManager.loadResult.sessionDir', '会话目录') }}</span><code class="pkp-info-path">{{ loadResult.session_dir || '—' }}</code></div>
                  <div><span>{{ t('framework.packageManager.loadResult.sourceOfTruth', '数据来源') }}</span><code>{{ loadResult.source_of_truth || '—' }}</code></div>
                  <div><span>{{ t('framework.packageManager.loadResult.readonly', '只读') }}</span><code>{{ loadResult.readonly ? t('framework.packageManager.common.yesText', '是') : t('framework.packageManager.common.noText', '否') }}</code></div>
                  <div><span>{{ t('framework.packageManager.loadResult.runtimeReady', '运行就绪') }}</span><code :class="loadResult.runtime_ready ? 'pkp-ok' : 'pkp-block'">{{ loadResult.runtime_ready ? t('framework.packageManager.common.yes', '✅ 是') : t('framework.packageManager.common.no', '⛔ 否') }}</code></div>
                  <div v-if="loadResult.runtime_blocking_count"><span>{{ t('framework.packageManager.loadResult.runtimeBlocking', '运行阻断') }}</span><code class="pkp-block">{{ loadResult.runtime_blocking_count }} {{ t('framework.packageManager.loadResult.itemUnit', '项') }}</code></div>
                  <div><span>{{ t('framework.packageManager.loadResult.securityReady', '安全就绪') }}</span><code :class="loadResult.security_ready ? 'pkp-ok' : 'pkp-block'">{{ loadResult.security_ready ? t('framework.packageManager.common.yes', '✅ 是') : t('framework.packageManager.common.no', '⛔ 否') }}</code></div>
                  <div v-if="loadResult.security_blocked_count"><span>{{ t('framework.packageManager.loadResult.securityBlocking', '安全阻断') }}</span><code class="pkp-block">{{ loadResult.security_blocked_count }} {{ t('framework.packageManager.loadResult.itemUnit', '项') }}</code></div>
                </div>
              </div>
            </template>

            <!-- Bind -->
            <template v-else-if="active === 'bind'">
              <div class="psp-field"><label>resource_id</label><input v-model="bindResourceId" class="psp-input" placeholder="ext-xxx" /></div>
              <div class="psp-field"><label>{{ t('framework.packageManager.bind.valueLabel', '值') }}</label><input v-model="bindValue" class="psp-input" :placeholder="t('framework.packageManager.bind.valuePlaceholder', '路径或值')" /></div>
              <button class="pkp-btn" @click="doBind" :disabled="!!loading">{{ t('framework.packageManager.bind.bindButton', '绑定') }}</button>
            </template>
          </div>
        </div>
    </div>
  </div>

  <!-- Security requirement dialog -->
  <Teleport to="body">
    <div v-if="secDialog" class="pkp-sec-overlay" @click.self="dismissSecDialog">
      <div class="pkp-sec-box">
        <div class="pkp-sec-hd">{{ t('framework.packageManager.securityDialog.title', '运行该包前需要放行安全权限') }}</div>
        <div class="pkp-sec-body">
          <p class="pkp-sec-desc">{{ t('framework.packageManager.securityDialog.desc', '当前软件首选项缺少该包运行所需的权限。你可以先忽略，但运行时可能被安全策略拦截。') }}</p>
          <div class="pkp-sec-list">
            <div v-for="e in secDialog.blocked_entries" :key="e.field" class="pkp-sec-item">
              <span class="pkp-sec-name">{{ e.display_name }}</span>
              <span class="pkp-sec-val">{{ e.current_value ? t('framework.packageManager.securityDialog.enabled', '已开启') : t('framework.packageManager.securityDialog.disabled', '未开启') }} → {{ t('framework.packageManager.securityDialog.needEnable', '需要开启') }}</span>
            </div>
          </div>
        </div>
        <div class="pkp-sec-ft">
          <button class="pkp-sec-btn pkp-sec-ignore" @click="dismissSecDialog">{{ t('framework.packageManager.securityDialog.ignore', '忽略') }}</button>
          <button class="pkp-sec-btn pkp-sec-enable" :disabled="secEnabling" @click="enableSecurityAndClose">
            {{ secEnabling ? t('framework.packageManager.securityDialog.enabling', '放行中…') : t('framework.packageManager.securityDialog.enableAll', '一键修改并放行权限') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
<style scoped>
.pkp-root { height: 100%; overflow: hidden; }
.pkp-box { background: var(--bg-panel); height: 100%; display: flex; flex-direction: column; }
.pkp-hd { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); font-size: var(--text-body); font-weight: 600; color: var(--text-primary); flex-shrink: 0; }
.pkp-source { font-size: var(--text-caption); color: var(--text-disabled); }
.pkp-close { margin-left: auto; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 12px; }
.pkp-body { display: flex; flex: 1; overflow: hidden; }
.pkp-nav { width: 100px; flex-shrink: 0; border-right: 1px solid var(--border-subtle); padding: var(--space-xs) 0; overflow-y: auto; }
.pkp-nav-item { display: block; width: 100%; padding: 4px 8px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); text-align: left; }
.pkp-nav-item:hover { background: var(--bg-hover); }
.pkp-nav-item.active { background: var(--bg-selected); color: var(--accent); font-weight: 600; }
.pkp-content { flex: 1; padding: var(--space-md); overflow-y: auto; }
.pkp-row { display: flex; gap: 4px; margin-bottom: 8px; }
.pkp-input { flex: 1; padding: 3px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); }
.pkp-pick { padding: 3px 8px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); }
.pkp-btn { margin-top: 8px; padding: 4px 14px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; font-size: var(--text-small); width: 100%; }
.pkp-btn:hover:not(:disabled) { background: var(--bg-hover); }
.pkp-btn:disabled { opacity: 0.5; }
.pkp-btn-build { border-color: var(--accent); color: var(--accent); }
.pkp-btn-build:hover:not(:disabled) { background: var(--accent-light); }
.pkp-btn-unload { border-color: var(--state-error); color: var(--state-error); }
.pkp-actions { display: flex; gap: var(--space-sm); }
.pkp-actions .pkp-btn { width: auto; flex: 1; }
.pkp-result { margin-top: 8px; padding: var(--space-sm); background: var(--bg-input); border-radius: var(--radius-sm); }
.pkp-summary { display: flex; gap: var(--space-md); font-size: var(--text-small); margin-bottom: 4px; }
.pkp-block { color: var(--state-error); font-weight: 600; }
.pkp-ok { color: var(--state-success); font-weight: 600; }
.pkp-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 12px; font-size: var(--text-small); margin-top: 6px; }
.pkp-info-grid div { display: flex; justify-content: space-between; align-items: center; }
.pkp-info-grid span { color: var(--text-disabled); }
.pkp-info-grid code { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); background: var(--bg-panel); padding: 0 4px; border-radius: 2px; }
.pkp-info-path { word-break: break-all; white-space: normal; max-width: 200px; }
/* Busy indicator */
.pkp-busy { padding: var(--space-md); margin-bottom: 8px; background: var(--bg-input); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); }
.pkp-busy-bar { height: 3px; background: var(--border-default); border-radius: 2px; overflow: hidden; margin-bottom: 10px; }
.pkp-busy-track { height: 100%; width: 30%; background: var(--accent); border-radius: 2px; animation: pkp-busy-slide 1.2s ease-in-out infinite; }
@keyframes pkp-busy-slide {
  0% { transform: translateX(-30%); }
  100% { transform: translateX(400%); }
}
.pkp-busy-title { font-size: var(--text-body); font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.pkp-busy-desc { font-size: var(--text-small); color: var(--text-disabled); }


.pkp-entry { display: flex; gap: var(--space-sm); padding: 2px 0; font-size: var(--text-small); align-items: baseline; }
.pkp-entry-sev { font-weight: 600; min-width: 48px; }
.sev-error .pkp-entry-sev { color: var(--state-error); }
.sev-warning .pkp-entry-sev { color: var(--state-warning); }
.sev-info .pkp-entry-sev { color: var(--state-info); }
.pkp-entry-msg { flex: 1; }
.pkp-entry-ref { font-size: var(--text-caption); color: var(--text-disabled); font-family: var(--font-mono); }
.psp-field { display: flex; align-items: center; gap: var(--space-sm); padding: 3px 0; font-size: var(--text-small); margin-bottom: 8px; }
.psp-field label { width: 80px; flex-shrink: 0; color: var(--text-disabled); }
.psp-input { flex: 1; padding: 2px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); }
/* Security requirement dialog */
.pkp-sec-overlay { position: fixed; inset: 0; z-index: 4000; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; }
.pkp-sec-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-lg); min-width: 380px; max-width: 480px; box-shadow: var(--shadow-menu); }
.pkp-sec-hd { padding: 12px 14px; border-bottom: 1px solid var(--border-subtle); font-weight: 600; color: var(--state-error); font-size: var(--text-body); }
.pkp-sec-body { padding: 12px 14px; }
.pkp-sec-desc { font-size: var(--text-small); color: var(--text-secondary); margin-bottom: 10px; }
.pkp-sec-list { display: flex; flex-direction: column; gap: 6px; }
.pkp-sec-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: rgba(208,112,96,0.06); border: 1px solid rgba(208,112,96,0.15); border-radius: var(--radius-sm); }
.pkp-sec-name { font-size: var(--text-small); font-weight: 500; color: var(--state-error); }
.pkp-sec-val { font-size: var(--text-caption); color: var(--text-disabled); }
.pkp-sec-ft { padding: 10px 14px; border-top: 1px solid var(--border-subtle); display: flex; gap: 8px; justify-content: flex-end; }
.pkp-sec-btn { padding: 4px 16px; border-radius: var(--radius-sm); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.pkp-sec-ignore { border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); }
.pkp-sec-ignore:hover { background: var(--bg-hover); }
.pkp-sec-enable { border: 1px solid var(--state-error); background: var(--state-error); color: #fff; }
.pkp-sec-enable:hover:not(:disabled) { background: #b85d54; }
.pkp-sec-enable:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
