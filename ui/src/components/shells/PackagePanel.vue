<script setup lang="ts">
import { ref, computed } from 'vue'
import { postPackagePreflight, postPackageBuild, fetchPackageInspect, postPackageLoad, postPackageUnload, postPackageBindExternal, postFileDialog, postSecurityEnableRequired } from '@/services/api'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useRuntimeStore } from '@/stores/runtimeStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import type { PackagePreflightResponse, SecurityRequirementSummary } from '@/types/domains/api'

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
const inspectResult = ref<Record<string, unknown> | null>(null)
const bindResourceId = ref('')
const bindValue = ref('')

const secDialog = ref<SecurityRequirementSummary | null>(null)
const secEnabling = ref(false)

function dismissSecDialog() { secDialog.value = null }
async function enableSecurityAndClose() {
  secEnabling.value = true
  try {
    await postSecurityEnableRequired({ confirm_high_risk: true })
    toast.success('已放行该包所需权限')
    await workspace.refreshSnapshot()
    secDialog.value = null
  } catch (e: any) {
    toast.error('放行失败', e?.message)
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
      title: target === 'package' ? '选择 .wcrun 文件' : '选择 .wcrun 输出路径',
      default_path: target === 'output' ? resolveDefaultOutputPath() : outputPath.value || '',
      file_types: target === 'output' ? ['WeConduct Runtime Package (*.wcrun)'] : ['WeConduct Runtime Package (*.wcrun)'],
    })
    if (r.status === 'selected' && r.paths.length) {
      if (target === 'package') packagePath.value = r.paths[0]
      else outputPath.value = r.paths[0]
    }
  } catch { toast.info('', '文件选择器不可用') }
}

async function doPreflight() {
  loading.value = 'preflight'
  try {
    preflightResult.value = await postPackagePreflight({
      mode: 'wcrun',
      source_of_truth: 'saved_project_only',
    })
    toast.success('校验完成', preflightResult.value.summary.blocking ? '存在阻断项' : '通过')
  }
  catch (e: any) { toast.error('校验失败', e?.message) }
  finally { loading.value = '' }
}

async function doBuild() {
  if (!outputPath.value) { toast.info('', '请选择输出路径'); return }
  loading.value = 'build'
  try {
    const r = await postPackageBuild({ output_path: outputPath.value, mode: 'wcrun', source_of_truth: 'saved_project_only' })
    toast.success('打包完成', r.output_path || '')
  } catch (e: any) { toast.error('打包失败', e?.message) }
  finally { loading.value = '' }
}

async function doInspect() {
  if (!packagePath.value) { toast.info('', '请选择 .wcrun 文件'); return }
  loading.value = 'inspect'
  try { inspectResult.value = await fetchPackageInspect(packagePath.value) as unknown as Record<string, unknown>; toast.success('检查完成') }
  catch (e: any) { toast.error('检查失败', e?.message) }
  finally { loading.value = '' }
}

async function doLoad() {
  if (!packagePath.value) { toast.info('', '请选择 .wcrun 文件'); return }
  loading.value = 'load'
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
    toast.success('已加载', '工作区已切换为 wcrun_package')
  } catch (e: any) { toast.error('加载失败', e?.message) }
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
    toast.success('已卸载')
  } catch (e: any) { toast.error('卸载失败', e?.message) }
  finally { loading.value = '' }
}

async function doBind() {
  if (!bindResourceId.value || !bindValue.value) { toast.info('', '请填写 resource_id 和值'); return }
  loading.value = 'bind'
  try {
    await postPackageBindExternal({ resource_id: bindResourceId.value, value: bindValue.value })
    toast.success('已绑定')
    await workspace.refreshSnapshot()
    bindResourceId.value = ''; bindValue.value = ''
  } catch (e: any) { toast.error('绑定失败', e?.message) }
  finally { loading.value = '' }
}

const sourceLabel = computed(() => (workspace.snapshot as any)?.project_settings?.source_of_truth === 'wcrun_package' ? '📦 .wcrun 包' : '📁 项目')
const isWcrun = computed(() => (workspace.snapshot as any)?.project_settings?.source_of_truth === 'wcrun_package')

</script>
<template>
  <div class="pkp-root">
    <div class="pkp-box">
        <div class="pkp-hd">
          <span>.wcrun 打包</span>
          <span class="pkp-source">{{ sourceLabel }}</span>
        </div>
        <div class="pkp-body">
          <div class="pkp-nav">
            <button :class="['pkp-nav-item', { active: active === 'preflight' }]" @click="active = 'preflight'">校验 & 构建</button>
            <button :class="['pkp-nav-item', { active: active === 'inspect' }]" @click="active = 'inspect'">检查 & 加载</button>
            <button :class="['pkp-nav-item', { active: active === 'bind' }]" @click="active = 'bind'">外部绑定</button>
          </div>
          <div class="pkp-content">
            <!-- Preflight & Build -->
            <template v-if="active === 'preflight'">
              <button class="pkp-btn" @click="doPreflight" :disabled="!!loading">🔍 打包前校验</button>
              <div v-if="preflightResult" class="pkp-result">
                <div class="pkp-summary">
                  <span :class="preflightResult.summary.blocking ? 'pkp-block' : 'pkp-ok'">{{ preflightResult.summary.blocking ? '⛔ 有阻断' : '✅ 通过' }}</span>
                  <span>错误 {{ preflightResult.summary.error_count }} · 警告 {{ preflightResult.summary.warning_count }}</span>
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
              <div class="pkp-row"><input v-model="outputPath" class="pkp-input" placeholder="输出路径，如 I:\output\demo.wcrun" /><button class="pkp-pick" @click="pickFile('output')">…</button></div>
              <button class="pkp-btn pkp-btn-build" @click="doBuild" :disabled="!!loading">📦 构建 .wcrun</button>
            </template>

            <!-- Inspect & Load -->
            <template v-else-if="active === 'inspect'">
              <div class="pkp-row"><input v-model="packagePath" class="pkp-input" placeholder=".wcrun 文件路径" /><button class="pkp-pick" @click="pickFile('package')">…</button></div>
              <div class="pkp-actions">
                <button class="pkp-btn" @click="doInspect" :disabled="!!loading">🔍 检查</button>
                <button class="pkp-btn pkp-btn-build" @click="doLoad" :disabled="!!loading">📥 加载</button>
                <button v-if="isWcrun" class="pkp-btn pkp-btn-unload" @click="doUnload" :disabled="!!loading">📤 卸载</button>
              </div>
              <div v-if="inspectResult" class="pkp-result">
                <div class="pkp-summary">状态: {{ inspectResult.status }}</div>
                <div v-if="inspectResult.runtime_readiness_summary" class="pkp-summary">
                  <span :class="(inspectResult.runtime_readiness_summary as any).ready ? 'pkp-ok' : 'pkp-block'">
                    {{ (inspectResult.runtime_readiness_summary as any).ready ? '✅ 可运行' : '⛔ 不可运行' }}
                  </span>
                </div>
              </div>
            </template>

            <!-- Bind -->
            <template v-else-if="active === 'bind'">
              <div class="psp-field"><label>resource_id</label><input v-model="bindResourceId" class="psp-input" placeholder="ext-xxx" /></div>
              <div class="psp-field"><label>值</label><input v-model="bindValue" class="psp-input" placeholder="路径或值" /></div>
              <button class="pkp-btn" @click="doBind" :disabled="!!loading">绑定</button>
            </template>
          </div>
        </div>
    </div>
  </div>

  <!-- Security requirement dialog -->
  <Teleport to="body">
    <div v-if="secDialog" class="pkp-sec-overlay" @click.self="dismissSecDialog">
      <div class="pkp-sec-box">
        <div class="pkp-sec-hd">运行该包前需要放行安全权限</div>
        <div class="pkp-sec-body">
          <p class="pkp-sec-desc">当前软件首选项缺少该包运行所需的权限。你可以先忽略，但运行时可能被安全策略拦截。</p>
          <div class="pkp-sec-list">
            <div v-for="e in secDialog.blocked_entries" :key="e.field" class="pkp-sec-item">
              <span class="pkp-sec-name">{{ e.display_name }}</span>
              <span class="pkp-sec-val">{{ e.current_value ? '已开启' : '未开启' }} → 需要开启</span>
            </div>
          </div>
        </div>
        <div class="pkp-sec-ft">
          <button class="pkp-sec-btn pkp-sec-ignore" @click="dismissSecDialog">忽略</button>
          <button class="pkp-sec-btn pkp-sec-enable" :disabled="secEnabling" @click="enableSecurityAndClose">
            {{ secEnabling ? '放行中…' : '一键修改并放行权限' }}
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
