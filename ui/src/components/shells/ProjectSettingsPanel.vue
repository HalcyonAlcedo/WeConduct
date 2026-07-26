<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch, toRaw } from 'vue'
import { fetchConfigValues, patchConfigValues, fetchPythonRuntime, postOpenPath, postFileDialog,
  postPythonRuntimeHealthCheck, postPythonRuntimePrepare, postPythonRuntimeRebuild,
  postPythonRuntimeClear, postPythonRuntimeExportBundle, postSecurityEnableRequired,
  fetchEncryptedParameters, postEncryptedParameters, postRekeyEncryptedParameters,
  postDeleteEncryptedParameters,
} from '@/services/api'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useToastStore } from '@/stores/toastStore'
import { t } from '@/i18n'
import type {
  ConfigPatchOperation,
  GraphEntrypointRuntimeValues,
  ProjectConfigRegistryValues,
  ProjectSettingsSnapshot,
  PythonRuntimeGetResponse,
  PythonRuntimeProfile,
  PythonRuntimeStatus,
  SecurityRequirementSummary,
} from '@/types/domains/api'

const workspace = useWorkspaceStore()
const toast = useToastStore()

const active = ref<'identity' | 'runtime' | 'packaging' | 'compile' | 'pythonRuntime' | 'encryptedParameters' | 'status'>('identity')
const loading = ref(false)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')

const DEFAULT_PYTHON_PROFILE: PythonRuntimeProfile = {
  runtime_enabled: false, python_version_spec: '3.13', interpreter_strategy: 'bundled',
  custom_python_path: null, cache_location_mode: 'software_cache', project_cache_mode: 'wheelhouse_rebuild',
  requirements_source_mode: 'inline', requirements_inline: [], requirements_file_path: null,
  lock_file_path: null, index_strategy: 'default', custom_index_url: null,
  auto_prepare_on_run: true, package_embed_mode: 'wheelhouse_rebuild',
  materialized_runtime_hash: null, last_health_status: 'unknown', last_health_message: null,
}
const DEFAULT_RUNTIME_STATUS: PythonRuntimeStatus = {
  health_status: null, health_message: null, runtime_root: null, python_executable: null,
  manifest_hash: null, cache_location_mode: null, project_cache_mode: null,
}
interface ProjectSettingsEditorModel {
  project_settings_schema_version: number
  project_identity: { name: string; description?: string; version?: string; author?: string; tags?: string[] }
  entrypoint_runtime: {
    initial_variables: Record<string, unknown>
    browser_config: Record<string, unknown>
    execution_defaults: Record<string, unknown>
  }
  packaging: { default_output_name?: string; include_embedded_resources?: boolean }
  external_resources: Record<string, unknown>[]
  resource_policy: { embedded_resources: string[]; external_resource_bindings: Record<string, unknown>[] }
  compile_profile: { source_of_truth: string; inject_project_runtime_defaults_into_main_flow_start: boolean }
  debug_profile?: { history_retention_limit: number }
  python_runtime_profile: PythonRuntimeProfile
}

const DEFAULT_ENTRYPOINT_RUNTIME: ProjectSettingsEditorModel['entrypoint_runtime'] = {
  initial_variables: {},
  browser_config: { headless: true, slow_mo_ms: 0 },
  execution_defaults: { default_timeout_ms: 30000, default_retry_count: 0 },
}
const pythonProfile = reactive<PythonRuntimeProfile>({ ...DEFAULT_PYTHON_PROFILE })
const runtimeStatus = reactive<PythonRuntimeStatus>({ ...DEFAULT_RUNTIME_STATUS })
const actionLoading = ref<string | null>(null)

const secSummary = ref<SecurityRequirementSummary | null>(null)
const secEnabling = ref(false)

interface EncryptedParameterEditorRow { parameter_id: string; name: string; type: string; value: string }
const encryptedParameterSummary = ref({ configured: false, parameter_set_id: null as string | null, parameters: [] as { parameter_id: string; name: string; type: string }[] })
const encryptedParameterSetId = ref('parameters-1')
const encryptedParameterRows = reactive<EncryptedParameterEditorRow[]>([])
const encryptedParameterPassword = ref('')
const encryptedParameterCurrentPassword = ref('')
const encryptedParameterNewPassword = ref('')
const encryptedParameterOverwriteConfirmed = ref(false)
const encryptedParameterDeleteConfirmed = ref(false)

const settings = reactive<ProjectSettingsEditorModel>({
  project_settings_schema_version: 1,
  project_identity: { name: '' },
  entrypoint_runtime: structuredClone(DEFAULT_ENTRYPOINT_RUNTIME),
  packaging: { default_output_name: '' },
  external_resources: [],
  resource_policy: { embedded_resources: [], external_resource_bindings: [] },
  compile_profile: { source_of_truth: 'saved_project_only', inject_project_runtime_defaults_into_main_flow_start: true },
  debug_profile: { history_retention_limit: 10 },
  python_runtime_profile: { ...DEFAULT_PYTHON_PROFILE },
})

type ProjectConfigValues = ProjectConfigRegistryValues
type GraphConfigValues = GraphEntrypointRuntimeValues

const PYTHON_PROFILE_EDITABLE_KEYS: (keyof PythonRuntimeProfile)[] = [
  'runtime_enabled',
  'python_version_spec',
  'interpreter_strategy',
  'custom_python_path',
  'cache_location_mode',
  'project_cache_mode',
  'requirements_source_mode',
  'requirements_inline',
  'requirements_file_path',
  'lock_file_path',
  'index_strategy',
  'custom_index_url',
  'auto_prepare_on_run',
  'package_embed_mode',
]

const tags = ref<string[]>([])
const tagInput = ref('')
function addTag() { const t = tagInput.value.trim(); if (t && !tags.value.includes(t)) { tags.value.push(t); tagInput.value = '' } }
function removeTag(idx: number) { tags.value.splice(idx, 1) }

const identityDesc = computed({ get: () => (settings.project_identity as any).description || '', set: (v: string) => { (settings.project_identity as any).description = v } })
const identityVersion = computed({ get: () => (settings.project_identity as any).version || '', set: (v: string) => { (settings.project_identity as any).version = v } })
const identityAuthor = computed({ get: () => (settings.project_identity as any).author || '', set: (v: string) => { (settings.project_identity as any).author = v } })
const runtimeControlsDisabled = computed(() => saveState.value === 'saving')
const executionDefaultsReadonly = computed(() => true)
const runtimeInjectionReadonly = computed(() => true)

interface VarEntry { key: string; value: string }
const variables = reactive<VarEntry[]>([])
function syncVars() { const obj: Record<string, unknown> = {}; for (const v of variables) { if (v.key.trim()) { const n = Number(v.value); if (!isNaN(n) && v.value.trim()) obj[v.key.trim()] = n; else if (v.value === 'true') obj[v.key.trim()] = true; else if (v.value === 'false') obj[v.key.trim()] = false; else obj[v.key.trim()] = v.value } } settings.entrypoint_runtime.initial_variables = obj }
function loadVars() { variables.splice(0, variables.length); for (const [k, v] of Object.entries(settings.entrypoint_runtime.initial_variables || {})) { variables.push({ key: k, value: typeof v === 'object' ? JSON.stringify(v) : String(v) }) } }
function addVar() { variables.push({ key: '', value: '' }) }
function removeVar(idx: number) { variables.splice(idx, 1); syncVars() }

function replaceObject(target: Record<string, unknown>, source: Record<string, unknown>) {
  for (const key of Object.keys(target)) {
    delete target[key]
  }
  Object.assign(target, source)
}

function replaceArray<T>(target: T[], source: T[]) {
  target.splice(0, target.length, ...source)
}

function cloneValue<T>(value: T): T {
  return structuredClone(toRaw(value))
}

function editablePythonProfileValue() {
  const next = {} as Partial<PythonRuntimeProfile>
  for (const key of PYTHON_PROFILE_EDITABLE_KEYS) {
    next[key] = cloneValue(pythonProfile[key]) as never
  }
  return next
}

function applyProjectConfig(values: ProjectConfigValues) {
  settings.project_settings_schema_version = 1
  replaceObject(settings.project_identity as Record<string, unknown>, {
    name: values.identity?.name || '',
  })
  replaceObject(settings.packaging as Record<string, unknown>, {
    default_output_name: values.packaging?.default_output_name || '',
    include_embedded_resources: values.packaging?.include_embedded_resources ?? true,
  })
  replaceArray(settings.external_resources, cloneValue(values.resources?.external_resources || []))
  replaceArray(settings.resource_policy.embedded_resources, cloneValue(values.resources?.embedded_resources || []))
  replaceArray(settings.resource_policy.external_resource_bindings, [])
  replaceObject(settings.compile_profile as Record<string, unknown>, {
    source_of_truth: 'saved_project_only',
    inject_project_runtime_defaults_into_main_flow_start: true,
  })
  replaceObject(settings.debug_profile as Record<string, unknown>, {
    history_retention_limit: values.debug?.history_retention_limit ?? 10,
  })
  Object.assign(pythonProfile, DEFAULT_PYTHON_PROFILE, values.python_profile || {})
  settings.python_runtime_profile = { ...editablePythonProfileValue(), ...pythonProfile }
  tags.value = Array.isArray((settings.project_identity as any).tags) ? [...((settings.project_identity as any).tags)] : []
  secSummary.value = (workspace.snapshot as any)?.security_requirement_summary || null
}

function applyGraphConfig(values: GraphConfigValues) {
  const entrypointRuntime = values.entrypoint_runtime || {}
  settings.entrypoint_runtime.initial_variables = cloneValue(entrypointRuntime.initial_variables || {})
  settings.entrypoint_runtime.browser_config = {
    ...cloneValue(DEFAULT_ENTRYPOINT_RUNTIME.browser_config),
    ...cloneValue(entrypointRuntime.browser_config || {}),
  }
  settings.entrypoint_runtime.execution_defaults = cloneValue(DEFAULT_ENTRYPOINT_RUNTIME.execution_defaults)
  loadVars()
}

function applyPythonRuntimeCapabilities(response: PythonRuntimeGetResponse) {
  Object.assign(runtimeStatus, DEFAULT_RUNTIME_STATUS, response.runtime_status || {})
  if (response.python_runtime_profile) {
    pythonProfile.materialized_runtime_hash = response.python_runtime_profile.materialized_runtime_hash
    pythonProfile.last_health_status = response.python_runtime_profile.last_health_status
    pythonProfile.last_health_message = response.python_runtime_profile.last_health_message
  }
}

function applyEncryptedParameterSummary(summary: { configured: boolean; parameter_set_id: string | null; parameters: { parameter_id: string; name: string; type: string }[] }) {
  encryptedParameterSummary.value = summary
  encryptedParameterSetId.value = summary.parameter_set_id || 'parameters-1'
  encryptedParameterRows.splice(0, encryptedParameterRows.length, ...summary.parameters.map(parameter => ({ ...parameter, value: '' })))
  encryptedParameterPassword.value = ''
  encryptedParameterCurrentPassword.value = ''
  encryptedParameterNewPassword.value = ''
  encryptedParameterOverwriteConfirmed.value = false
  encryptedParameterDeleteConfirmed.value = false
}

function addEncryptedParameter() {
  encryptedParameterRows.push({ parameter_id: '', name: '', type: 'string', value: '' })
}

function removeEncryptedParameter(index: number) {
  encryptedParameterRows.splice(index, 1)
}

async function saveEncryptedParameters() {
  if (isWcrun.value) return
  try {
    const parameters = encryptedParameterRows.map(({ parameter_id, name, type }) => ({ parameter_id, name, type }))
    const values = Object.fromEntries(encryptedParameterRows.map(row => [row.parameter_id, row.value]))
    const summary = await postEncryptedParameters({
      parameter_set_id: encryptedParameterSetId.value,
      parameters,
      values,
      password: encryptedParameterPassword.value,
      confirm_overwrite: encryptedParameterSummary.value.configured && encryptedParameterOverwriteConfirmed.value,
    })
    applyEncryptedParameterSummary(summary)
    await workspace.refreshSnapshot()
    toast.success(t('framework.projectSettings.encryptedParameters.saved', '加密参数已保存'))
  } catch (e: any) {
    toast.error(t('framework.projectSettings.encryptedParameters.saveFailed', '保存加密参数失败'), e?.message)
  }
}

async function rekeyEncryptedParameters() {
  if (isWcrun.value) return
  try {
    const summary = await postRekeyEncryptedParameters({
      current_password: encryptedParameterCurrentPassword.value,
      new_password: encryptedParameterNewPassword.value,
    })
    applyEncryptedParameterSummary(summary)
    toast.success(t('framework.projectSettings.encryptedParameters.rekeyed', '加密参数密码已更新'))
  } catch (e: any) {
    toast.error(t('framework.projectSettings.encryptedParameters.rekeyFailed', '更新加密参数密码失败'), e?.message)
  }
}

async function deleteEncryptedParameters() {
  if (isWcrun.value || !encryptedParameterDeleteConfirmed.value) return
  try {
    const summary = await postDeleteEncryptedParameters({ confirm_delete: true })
    applyEncryptedParameterSummary(summary)
    await workspace.refreshSnapshot()
    toast.success(t('framework.projectSettings.encryptedParameters.deleted', '加密参数已删除'))
  } catch (e: any) {
    toast.error(t('framework.projectSettings.encryptedParameters.deleteFailed', '删除加密参数失败'), e?.message)
  }
}

function projectOperations(): ConfigPatchOperation[] {
  syncVars()
  const pythonRuntimeProfile = editablePythonProfileValue()
  settings.python_runtime_profile = { ...pythonRuntimeProfile, ...settings.python_runtime_profile }
  const operations: ConfigPatchOperation[] = [
    { op: 'replace', path: '/identity/name', value: settings.project_identity.name },
    { op: 'replace', path: '/debug/history_retention_limit', value: settings.debug_profile?.history_retention_limit ?? 10 },
    { op: 'replace', path: '/resources/external_resources', value: cloneValue(settings.external_resources) },
    { op: 'replace', path: '/resources/embedded_resources', value: cloneValue(settings.resource_policy.embedded_resources) },
    { op: 'replace', path: '/packaging/default_output_name', value: settings.packaging.default_output_name || '' },
    { op: 'replace', path: '/packaging/include_embedded_resources', value: (settings.packaging as any).include_embedded_resources ?? true },
  ]
  for (const key of PYTHON_PROFILE_EDITABLE_KEYS) {
    operations.push({
      op: 'replace',
      path: `/python_profile/${key}`,
      value: cloneValue(pythonRuntimeProfile[key]),
    })
  }
  return operations
}

function graphRuntimeOperations(): ConfigPatchOperation[] {
  syncVars()
  return [
    {
      op: 'replace',
      path: '/entrypoint_runtime/initial_variables',
      value: cloneValue(settings.entrypoint_runtime.initial_variables),
    },
    {
      op: 'replace',
      path: '/entrypoint_runtime/browser_config',
      value: cloneValue(settings.entrypoint_runtime.browser_config),
    },
  ]
}

async function load() {
  loading.value = true
  try {
    const [projectResult, graphResult, pythonRuntimeResult, encryptedParameterResult] = await Promise.all([
      fetchConfigValues<ProjectConfigValues>('project'),
      fetchConfigValues<GraphConfigValues>('graph'),
      fetchPythonRuntime(),
      fetchEncryptedParameters(),
    ])
    applyProjectConfig(projectResult.values || {})
    applyGraphConfig(graphResult.values || {})
    applyPythonRuntimeCapabilities(pythonRuntimeResult)
    applyEncryptedParameterSummary(encryptedParameterResult)
    secSummary.value = (workspace.snapshot as any)?.security_requirement_summary || null
    saveState.value = 'idle'
  } catch (e: any) {
    toast.error(t('framework.projectSettings.toast.loadFailed', '加载失败'), e?.message)
  } finally {
    loading.value = false
  }
}

function markSaved() {
  saveState.value = 'saved'
  setTimeout(() => { if (saveState.value === 'saved') saveState.value = 'idle' }, 2000)
}

async function save() {
  if (isWcrun.value) return
  saveState.value = 'saving'
  try {
    const projectResult = await patchConfigValues<ProjectConfigValues>({
      scope: 'project',
      operations: projectOperations(),
      confirm_high_risk: false,
    })
    applyProjectConfig(projectResult.values || {})
    const graphResult = await patchConfigValues<GraphConfigValues>({
      scope: 'graph',
      operations: graphRuntimeOperations(),
      confirm_high_risk: false,
    })
    applyGraphConfig(graphResult.values || {})
    await workspace.refreshSnapshot()
    secSummary.value = (workspace.snapshot as any)?.security_requirement_summary || null
    markSaved()
  } catch (e: any) {
    saveState.value = 'error'
    toast.error(t('framework.projectSettings.toast.saveFailed', '保存失败'), e?.message)
  }
}

async function saveRuntimeDefaults() {
  saveState.value = 'saving'
  try {
    const graphResult = await patchConfigValues<GraphConfigValues>({
      scope: 'graph',
      operations: graphRuntimeOperations(),
      confirm_high_risk: false,
    })
    applyGraphConfig(graphResult.values || {})
    await workspace.refreshSnapshot()
    secSummary.value = (workspace.snapshot as any)?.security_requirement_summary || null
    markSaved()
  } catch (e: any) {
    saveState.value = 'error'
    toast.error(t('framework.projectSettings.toast.saveFailed', '保存失败'), e?.message)
  }
}

const st = computed(() => (workspace.snapshot?.project_settings || {}) as ProjectSettingsSnapshot)
const isWcrun = computed(() => (st.value as any)?.source_of_truth === 'wcrun_package')
const sectionReadonly = computed(() => isWcrun.value && active.value !== 'runtime')
const sourceLabel = computed(() => isWcrun.value ? t('framework.projectSettings.header.sourceWcrun', '📦 .wcrun 包 (只读)') : t('framework.projectSettings.header.sourceProject', '📁 项目目录'))
const dirtyLabel = computed(() => st.value?.is_dirty ? t('framework.projectSettings.header.dirty', '● 未保存') : t('framework.projectSettings.header.clean', '● 已保存'))

async function openProjectDir() { const dir = (st.value as any).project_file_path || (st.value as any).session_dir; if (!dir) { toast.info('', t('framework.projectSettings.toast.noProjectDir', '当前无项目目录路径')); return }; try { const path = dir.includes('.weconduct.json') ? dir.slice(0, Math.max(dir.lastIndexOf('\\'), dir.lastIndexOf('/'))) : dir; const r = await postOpenPath({ path }); if (r.status === 'opened') toast.success(t('framework.projectSettings.toast.opened', '已打开'), r.path) } catch (e: any) { if (e?.status === 503) toast.info('', t('framework.projectSettings.toast.openDirUnsupported', '当前运行环境不支持系统打开目录')); else toast.error(t('framework.projectSettings.toast.openFailed', '打开失败'), e?.message) } }

// Python runtime helpers
const pythonReadonly = computed(() => isWcrun.value)
const actionDisabled = computed(() => isWcrun.value || !pythonProfile.runtime_enabled || !!actionLoading.value)
const exportDisabled = computed(() => actionDisabled.value || pythonProfile.package_embed_mode === 'none')
const healthStatusLabel = computed(() => {
  const labels: Record<string, string> = { disabled: t('framework.projectSettings.healthStatus.disabled', '已禁用'), unknown: t('framework.projectSettings.healthStatus.unknown', '未知'), ready: t('framework.projectSettings.healthStatus.ready', '就绪'), missing: t('framework.projectSettings.healthStatus.missing', '缺失'), broken: t('framework.projectSettings.healthStatus.broken', '异常'), stale: t('framework.projectSettings.healthStatus.stale', '过期') }
  return labels[runtimeStatus.health_status ?? ''] ?? (runtimeStatus.health_status ?? '—')
})

async function pickPythonPath(field: 'custom_python_path' | 'requirements_file_path' | 'lock_file_path') {
  try {
    const labels: Record<string, string> = { custom_python_path: t('framework.projectSettings.fileDialog.pickPython', '选择 Python 可执行文件'), requirements_file_path: t('framework.projectSettings.fileDialog.pickRequirements', '选择 requirements.txt'), lock_file_path: t('framework.projectSettings.fileDialog.pickLockFile', '选择锁定文件') }
    const r = await postFileDialog({ mode: 'open_file', title: labels[field] || t('framework.projectSettings.fileDialog.pickFile', '选择文件') })
    if (r.status === 'selected' && r.paths.length) (pythonProfile as any)[field] = r.paths[0]
  } catch (e: any) { if (e?.status === 503) toast.info('', workspace.isLimitedBrowser ? t('framework.projectSettings.toast.limitedBrowserFileDialog', '受限浏览器模式：系统文件选择器不可用') : t('framework.projectSettings.toast.fileDialogUnsupported', '当前运行环境不支持系统文件选择器')) }
}

async function doHealthCheck() {
  actionLoading.value = 'health-check'; try {
    await save(); if (saveState.value === 'error') { toast.error(t('framework.projectSettings.toast.saveAbortedRuntime', '保存项目设置失败，已中止 Python runtime 操作')); return }
    const r = await postPythonRuntimeHealthCheck(); Object.assign(runtimeStatus, r.runtime_status); toast.success(t('framework.projectSettings.toast.healthCheckDone', '健康检查完成'), t('framework.projectSettings.toast.statusValue', `状态: ${r.runtime_status.health_status}`, { status: r.runtime_status.health_status }))
  } catch (e: any) { toast.error(t('framework.projectSettings.toast.healthCheckFailed', '健康检查失败'), e?.message) } finally { actionLoading.value = null }
}
async function doPrepare() {
  actionLoading.value = 'prepare'; try {
    await save(); if (saveState.value === 'error') { toast.error(t('framework.projectSettings.toast.saveAbortedRuntime', '保存项目设置失败，已中止 Python runtime 操作')); return }
    const r = await postPythonRuntimePrepare(); Object.assign(pythonProfile, r.python_runtime_profile); Object.assign(runtimeStatus, r.runtime_status); toast.success(t('framework.projectSettings.toast.runtimePrepared', '运行时已准备'), t('framework.projectSettings.toast.statusValue', `状态: ${r.runtime_status.health_status}`, { status: r.runtime_status.health_status }))
  } catch (e: any) { toast.error(t('framework.projectSettings.toast.prepareFailed', '准备失败'), e?.message) } finally { actionLoading.value = null }
}
async function doRebuild() {
  actionLoading.value = 'rebuild'; try {
    await save(); if (saveState.value === 'error') { toast.error(t('framework.projectSettings.toast.saveAbortedRuntime', '保存项目设置失败，已中止 Python runtime 操作')); return }
    const r = await postPythonRuntimeRebuild(); Object.assign(pythonProfile, r.python_runtime_profile); Object.assign(runtimeStatus, r.runtime_status); toast.success(t('framework.projectSettings.toast.runtimeRebuilt', '运行时已重建'), t('framework.projectSettings.toast.statusValue', `状态: ${r.runtime_status.health_status}`, { status: r.runtime_status.health_status }))
  } catch (e: any) { toast.error(t('framework.projectSettings.toast.rebuildFailed', '重建失败'), e?.message) } finally { actionLoading.value = null }
}
async function doClear() {
  actionLoading.value = 'clear'; try {
    await save(); if (saveState.value === 'error') { toast.error(t('framework.projectSettings.toast.saveAbortedRuntime', '保存项目设置失败，已中止 Python runtime 操作')); return }
    const r = await postPythonRuntimeClear(); Object.assign(runtimeStatus, r.runtime_status); toast.success(t('framework.projectSettings.toast.runtimeCleared', '运行时已清理'), t('framework.projectSettings.toast.statusValue', `状态: ${r.runtime_status.health_status}`, { status: r.runtime_status.health_status }))
  } catch (e: any) { toast.error(t('framework.projectSettings.toast.clearFailed', '清理失败'), e?.message) } finally { actionLoading.value = null }
}
async function doExportBundle() {
  actionLoading.value = 'export'; try {
    await save(); if (saveState.value === 'error') { toast.error(t('framework.projectSettings.toast.saveAbortedRuntime', '保存项目设置失败，已中止 Python runtime 操作')); return }
    const r = await postFileDialog({ mode: 'save_file', title: t('framework.projectSettings.fileDialog.pickExportPath', '选择 Python 运行时导出路径'), default_path: 'python-runtime-export.zip', file_types: [t('framework.projectSettings.fileDialog.zipArchive', 'Zip 存档 (*.zip)')] }); if (r.status !== 'selected' || !r.paths.length) { actionLoading.value = null; return }; const exportResult = await postPythonRuntimeExportBundle({ output_path: r.paths[0] }); toast.success(t('framework.projectSettings.toast.exportDone', '导出成功'), t('framework.projectSettings.toast.exportedTo', `已导出至 ${exportResult.export_bundle.output_path}`, { path: exportResult.export_bundle.output_path }))
  } catch (e: any) { toast.error(t('framework.projectSettings.toast.exportFailed', '导出失败'), e?.message) } finally { actionLoading.value = null }
}

async function enableSecurityRequirements() {
  secEnabling.value = true
  try {
    const r = await postSecurityEnableRequired({ confirm_high_risk: true })
    if (r.status === 'updated') {
      toast.success(t('framework.projectSettings.toast.securityUpdated', '安全设置已更新'), t('framework.projectSettings.toast.securityAllEnabled', '所有必需的安全选项已开启'))
      secSummary.value = r.security_requirement_summary
      await workspace.refreshSnapshot()
    }
  } catch (e: any) {
    if (e?.body?.error === 'high_risk_confirmation_required') {
      toast.info(t('framework.projectSettings.toast.confirmRequired', '需要确认'), t('framework.projectSettings.toast.confirmHighRiskHint', '请在首选项安全设置中手动确认高风险变更'))
    } else {
      toast.error(t('framework.projectSettings.toast.enableFailed', '开启失败'), e?.message)
    }
  } finally { secEnabling.value = false }
}

// computed (not const) so nav labels re-localize live on UI language change.
const NAV = computed<{ key: typeof active.value; label: string }[]>(() => [{ key: 'identity', label: t('framework.projectSettings.nav.identity', '项目信息') }, { key: 'runtime', label: t('framework.projectSettings.nav.runtime', '运行默认值') }, { key: 'packaging', label: t('framework.projectSettings.nav.packaging', '资源与打包') }, { key: 'compile', label: t('framework.projectSettings.nav.compile', '编译规则') }, { key: 'pythonRuntime', label: t('framework.projectSettings.nav.pythonRuntime', 'Python 运行时') }, { key: 'encryptedParameters', label: t('framework.projectSettings.nav.encryptedParameters', '加密参数') }, { key: 'status', label: t('framework.projectSettings.nav.status', '状态与诊断') }])

onMounted(load)
watch(() => workspace.projectId, (next, prev) => { if (next && next !== prev) load() })
</script>
<template>
  <div class="psp-root">
    <div class="psp-hd">
      <span>{{ t('framework.projectSettings.header.title', '项目设置') }}</span><span class="psp-source">{{ sourceLabel }}</span><span :class="st.is_dirty ? 'psp-dirty' : 'psp-clean'">{{ dirtyLabel }}</span>
      <span v-if="saveState === 'saving'" class="psp-st-saving">{{ t('framework.projectSettings.header.saving', '保存中…') }}</span><span v-else-if="saveState === 'saved'" class="psp-st-saved">{{ t('framework.projectSettings.header.saved', '已保存') }}</span><span v-else-if="saveState === 'error'" class="psp-st-err">{{ t('framework.projectSettings.header.error', '错误') }}</span>
      <button class="psp-open-dir" @click="openProjectDir" :disabled="!st.project_file_path && !st.session_dir" :title="t('framework.projectSettings.header.openDirTitle', '打开项目目录')">{{ t('framework.projectSettings.header.openDir', '📂 打开目录') }}</button>
    </div>
    <div v-if="isWcrun" class="psp-readonly-banner">{{ t('framework.projectSettings.banner.wcrunReadonly', '📦 .wcrun 包已加载 — 仅运行默认值可编辑，其余为只读') }}</div>
    <div v-if="secSummary && !secSummary.ready" class="psp-sec-banner">
      <div class="psp-sec-title">{{ t('framework.projectSettings.security.insufficientTitle', '⚠ 安全设置不足 — 当前软件安全设置不足以运行该项目') }}</div>
      <div class="psp-sec-entries">
        <div v-for="e in secSummary.blocked_entries" :key="e.field" class="psp-sec-entry">
          <span>{{ e.display_name }}</span>
          <span class="psp-sec-req">{{ t('framework.projectSettings.security.needEnable', '需要开启') }}</span>
        </div>
      </div>
      <button class="psp-sec-enable-btn" :disabled="secEnabling" @click="enableSecurityRequirements">
        {{ secEnabling ? t('framework.projectSettings.security.enabling', '开启中…') : t('framework.projectSettings.security.enableAll', '🔓 一键开启所需安全选项') }}
      </button>
    </div>
    <div class="psp-body" v-if="!loading">
      <div class="psp-nav"><button v-for="n in NAV" :key="n.key" :class="['psp-nav-item', { active: active === n.key }]" @click="active = n.key">{{ n.label }}</button></div>
      <div class="psp-content">
        <template v-if="active === 'identity'">
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.projectId', '项目 ID') }}</label><code class="psp-ro">{{ workspace.projectId || '—' }}</code></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.name', '项目名称') }}</label><input v-model="settings.project_identity.name" class="psp-input" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.description', '描述') }}</label><textarea v-model="identityDesc" class="psp-input psp-textarea" rows="2" :placeholder="t('framework.projectSettings.identity.descriptionPlaceholder', '项目描述')" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.version', '版本') }}</label><input v-model="identityVersion" class="psp-input" placeholder="0.1.0" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.author', '作者') }}</label><input v-model="identityAuthor" class="psp-input" :placeholder="t('framework.projectSettings.identity.authorPlaceholder', '作者')" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.identity.tags', '标签') }}</label><div class="psp-tags"><span v-for="(tag, i) in tags" :key="i" class="psp-tag">{{ tag }}<button v-if="!sectionReadonly" class="psp-tag-rm" @click="removeTag(i)">×</button></span><input v-if="!sectionReadonly" v-model="tagInput" class="psp-tag-input" :placeholder="t('framework.projectSettings.identity.addTag', '新增标签')" @keyup.enter="addTag" style="width:80px" /></div></div>
        </template>
        <template v-else-if="active === 'runtime'">
          <h5>{{ t('framework.projectSettings.runtime.initialVariables', '初始变量') }}</h5>
          <div v-for="(v, i) in variables" :key="i" class="psp-var-row"><input v-model="v.key" class="psp-input" :placeholder="t('framework.projectSettings.runtime.varName', '变量名')" @change="syncVars()" style="width:120px" :disabled="runtimeControlsDisabled" /><input v-model="v.value" class="psp-input" :placeholder="t('framework.projectSettings.runtime.varValue', '值')" @change="syncVars()" style="flex:1" :disabled="runtimeControlsDisabled" /><button class="psp-rm" @click="removeVar(i)" :disabled="runtimeControlsDisabled">✕</button></div>
          <button class="psp-add" @click="addVar" :disabled="runtimeControlsDisabled">{{ t('framework.projectSettings.runtime.addVar', '+ 新增变量') }}</button>
          <h5 style="margin-top:14px">{{ t('framework.projectSettings.runtime.browserConfig', '浏览器配置') }}</h5>
          <div class="psp-field"><label>headless</label><input type="checkbox" v-model="settings.entrypoint_runtime.browser_config.headless" :disabled="runtimeControlsDisabled" /></div>
          <div class="psp-field"><label>slow_mo_ms</label><input type="number" v-model.number="settings.entrypoint_runtime.browser_config.slow_mo_ms" class="psp-input" style="width:100px" :disabled="runtimeControlsDisabled" /></div>
          <h5 style="margin-top:14px">{{ t('framework.projectSettings.runtime.executionDefaults', '执行默认值') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.runtime.timeoutMs', '超时(ms)') }}</label><input type="number" v-model.number="settings.entrypoint_runtime.execution_defaults.default_timeout_ms" class="psp-input" style="width:100px" :disabled="executionDefaultsReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.runtime.retryCount', '重试次数') }}</label><input type="number" v-model.number="settings.entrypoint_runtime.execution_defaults.default_retry_count" class="psp-input" style="width:80px" :disabled="executionDefaultsReadonly" /></div>
          <button class="psp-btn-save" @click="saveRuntimeDefaults" :disabled="saveState === 'saving'" style="margin-top:14px">{{ t('framework.projectSettings.runtime.saveRuntimeOnly', '仅保存运行默认值') }}</button>
        </template>
        <template v-else-if="active === 'packaging'">
          <h5>{{ t('framework.projectSettings.packaging.title', '打包设置') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.packaging.defaultOutputName', '默认输出名') }}</label><input v-model="settings.packaging.default_output_name" class="psp-input" placeholder="demo.wcrun" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.packaging.includeEmbeddedResources', '包含嵌入资源') }}</label><input type="checkbox" v-model="settings.packaging.include_embedded_resources" :disabled="sectionReadonly" /></div>
          <h5 style="margin-top:14px">{{ t('framework.projectSettings.packaging.externalResources', 'External 资源') }}</h5>
          <div v-if="!settings.external_resources.length && !sectionReadonly" class="psp-empty">{{ t('framework.projectSettings.packaging.noExternal', '暂无 external 资源声明') }}</div>
          <div v-for="(er, i) in settings.external_resources" :key="i" class="psp-var-row"><input :value="(er as any).resource_id || (er as any).bind_key || ''" class="psp-input" placeholder="resource_id" style="width:100px" :disabled="sectionReadonly" @change="(er as any).resource_id = ($event.target as HTMLInputElement).value" /><input :value="(er as any).kind || ''" class="psp-input" placeholder="kind" style="width:70px" :disabled="sectionReadonly" @change="(er as any).kind = ($event.target as HTMLInputElement).value" /><input :value="(er as any).description || ''" class="psp-input" :placeholder="t('framework.projectSettings.packaging.descriptionPlaceholder', '描述')" style="flex:1" :disabled="sectionReadonly" @change="(er as any).description = ($event.target as HTMLInputElement).value" /><button v-if="!sectionReadonly" class="psp-rm" @click="settings.external_resources.splice(i,1)">✕</button></div>
          <button v-if="!sectionReadonly" class="psp-add" @click="settings.external_resources.push({ resource_id: '', kind: 'file', description: '' })">{{ t('framework.projectSettings.packaging.addExternal', '+ 新增 external 资源') }}</button>
          <h5 style="margin-top:14px">{{ t('framework.projectSettings.packaging.embeddedResources', 'Embedded 资源') }}</h5>
          <div v-if="!settings.resource_policy.embedded_resources?.length && !sectionReadonly" class="psp-empty">{{ t('framework.projectSettings.packaging.noEmbedded', '暂无 embedded 资源') }}</div>
          <div v-for="(p, i) in settings.resource_policy.embedded_resources" :key="i" class="psp-var-row"><input :value="p" class="psp-input" style="flex:1" :disabled="sectionReadonly" @change="settings.resource_policy.embedded_resources[i] = ($event.target as HTMLInputElement).value" /><button v-if="!sectionReadonly" class="psp-rm" @click="settings.resource_policy.embedded_resources.splice(i,1)">✕</button></div>
          <button v-if="!sectionReadonly" class="psp-add" @click="settings.resource_policy.embedded_resources.push('')">{{ t('framework.projectSettings.packaging.addEmbedded', '+ 新增 embedded 资源') }}</button>
        </template>
        <template v-else-if="active === 'compile'">
          <div class="psp-field"><label>{{ t('framework.projectSettings.compile.sourceOfTruth', '真值来源') }}</label><select v-model="settings.compile_profile.source_of_truth" class="psp-input" :disabled="sectionReadonly"><option value="saved_project_only">saved_project_only</option></select></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.compile.injectRuntimeDefaults', '注入运行默认值') }}</label><input type="checkbox" v-model="settings.compile_profile.inject_project_runtime_defaults_into_main_flow_start" :disabled="runtimeInjectionReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.compile.historyRetentionLimit', '调试历史保留上限') }}</label><input type="number" v-model.number="settings.debug_profile!.history_retention_limit" class="psp-input" style="width:100px" min="1" :disabled="sectionReadonly" /></div>
        </template>
        <template v-else-if="active === 'pythonRuntime'">
          <!-- Status banner -->
          <div class="psp-runtime-banner" :class="`psp-runtime-banner--${runtimeStatus.health_status || 'unknown'}`">
            <span>{{ t('framework.projectSettings.pythonRuntime.runtimeStatusLabel', '运行时状态') }}: <strong>{{ healthStatusLabel }}</strong></span>
            <span v-if="runtimeStatus.health_message" class="psp-runtime-msg">{{ runtimeStatus.health_message }}</span>
          </div>

          <h5>{{ t('framework.projectSettings.pythonRuntime.runtimeStatus', '运行时状态') }}</h5>
          <div class="psp-state-grid">
            <div><span>{{ t('framework.projectSettings.pythonRuntime.healthStatus', '健康状态') }}</span><code>{{ healthStatusLabel }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.runtimeRoot', '运行时根目录') }}</span><code class="psp-path">{{ runtimeStatus.runtime_root || '—' }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.pythonExecutable', 'Python 可执行文件') }}</span><code class="psp-path">{{ runtimeStatus.python_executable || '—' }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.manifestHash', 'Manifest 哈希') }}</span><code>{{ runtimeStatus.manifest_hash || '—' }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.cacheLocationMode', '缓存位置模式') }}</span><code>{{ runtimeStatus.cache_location_mode || '—' }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.projectCacheMode', '项目缓存模式') }}</span><code>{{ runtimeStatus.project_cache_mode || '—' }}</code></div>
            <div><span>{{ t('framework.projectSettings.pythonRuntime.packageEmbedMode', '包嵌入模式') }}</span><code>{{ pythonProfile.package_embed_mode || '—' }}</code></div>
            <div><span>Materialized Hash</span><code class="psp-path">{{ pythonProfile.materialized_runtime_hash || '—' }}</code></div>
          </div>

          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.basicSettings', '基本设置') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.enableRuntime', '启用运行时') }}</label><input type="checkbox" v-model="pythonProfile.runtime_enabled" :disabled="isWcrun" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.pythonVersion', 'Python 版本') }}</label>
            <select v-model="pythonProfile.python_version_spec" class="psp-input" :disabled="pythonReadonly" style="max-width:120px">
              <option value="3.10">3.10</option><option value="3.11">3.11</option><option value="3.12">3.12</option><option value="3.13">3.13</option>
            </select>
          </div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.interpreterStrategy', '解释器策略') }}</label>
            <select v-model="pythonProfile.interpreter_strategy" class="psp-input" :disabled="pythonReadonly" style="max-width:160px">
              <option value="bundled">bundled</option><option value="system">system</option><option value="custom_path">custom_path</option>
            </select>
          </div>
          <div class="psp-field" v-if="pythonProfile.interpreter_strategy === 'custom_path'">
            <label>{{ t('framework.projectSettings.pythonRuntime.customPath', '自定义路径') }}</label>
            <div class="psp-path-row">
              <input v-model="pythonProfile.custom_python_path" class="psp-input" :placeholder="t('framework.projectSettings.pythonRuntime.customPathPlaceholder', 'Python 可执行文件路径')" :disabled="pythonReadonly" />
              <button class="psp-pick-btn" @click="pickPythonPath('custom_python_path')" :disabled="pythonReadonly">…</button>
            </div>
          </div>

          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.cacheSettings', '缓存设置') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.cacheLocationMode', '缓存位置模式') }}</label>
            <select v-model="pythonProfile.cache_location_mode" class="psp-input" :disabled="pythonReadonly" style="max-width:180px">
              <option value="software_cache">software_cache</option><option value="project_cache">project_cache</option>
            </select>
          </div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.projectCacheMode', '项目缓存模式') }}</label>
            <select v-model="pythonProfile.project_cache_mode" class="psp-input" :disabled="pythonReadonly" style="max-width:200px">
              <option value="full_venv">full_venv</option><option value="wheelhouse_rebuild">wheelhouse_rebuild</option>
            </select>
          </div>

          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.dependencyConfig', '依赖配置') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.requirementsSourceMode', '需求来源模式') }}</label>
            <select v-model="pythonProfile.requirements_source_mode" class="psp-input" :disabled="pythonReadonly" style="max-width:200px">
              <option value="inline">inline</option><option value="requirements_txt">requirements_txt</option><option value="lock_file">lock_file</option>
            </select>
          </div>
          <template v-if="pythonProfile.requirements_source_mode === 'inline'">
            <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.inlineDependencies', '内联依赖') }}</label>
              <div class="psp-vars-list">
                <div v-for="(_r, i) in pythonProfile.requirements_inline" :key="i" class="psp-var-row">
                  <input v-model="pythonProfile.requirements_inline[i]" class="psp-input" placeholder="package==version" :disabled="pythonReadonly" />
                  <button v-if="!pythonReadonly" class="psp-rm" @click="pythonProfile.requirements_inline.splice(i, 1)">✕</button>
                </div>
                <button v-if="!pythonReadonly" class="psp-add" @click="pythonProfile.requirements_inline.push('')">{{ t('framework.projectSettings.pythonRuntime.addDependency', '+ 新增依赖') }}</button>
              </div>
            </div>
          </template>
          <div class="psp-field" v-if="pythonProfile.requirements_source_mode === 'requirements_txt'">
            <label>requirements.txt</label>
            <div class="psp-path-row">
              <input v-model="pythonProfile.requirements_file_path" class="psp-input" :placeholder="t('framework.projectSettings.pythonRuntime.requirementsPathPlaceholder', 'requirements.txt 路径')" :disabled="pythonReadonly" />
              <button class="psp-pick-btn" @click="pickPythonPath('requirements_file_path')" :disabled="pythonReadonly">…</button>
            </div>
          </div>
          <div class="psp-field" v-if="pythonProfile.requirements_source_mode === 'lock_file'">
            <label>{{ t('framework.projectSettings.pythonRuntime.lockFile', '锁定文件') }}</label>
            <div class="psp-path-row">
              <input v-model="pythonProfile.lock_file_path" class="psp-input" :placeholder="t('framework.projectSettings.pythonRuntime.lockFilePathPlaceholder', 'Pipfile.lock / poetry.lock 路径')" :disabled="pythonReadonly" />
              <button class="psp-pick-btn" @click="pickPythonPath('lock_file_path')" :disabled="pythonReadonly">…</button>
            </div>
          </div>

          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.indexConfig', '索引配置') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.indexStrategy', '索引策略') }}</label>
            <select v-model="pythonProfile.index_strategy" class="psp-input" :disabled="pythonReadonly" style="max-width:120px">
              <option value="default">default</option><option value="custom">custom</option>
            </select>
          </div>
          <div class="psp-field" v-if="pythonProfile.index_strategy === 'custom'">
            <label>{{ t('framework.projectSettings.pythonRuntime.customIndexUrl', '自定义索引 URL') }}</label>
            <input v-model="pythonProfile.custom_index_url" class="psp-input" placeholder="https://pypi.example.com/simple" :disabled="pythonReadonly" />
          </div>

          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.runtimeBehavior', '运行时行为') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.autoPrepareOnRun', '运行前自动准备') }}</label><input type="checkbox" v-model="pythonProfile.auto_prepare_on_run" :disabled="pythonReadonly" /></div>
          <div class="psp-field"><label>{{ t('framework.projectSettings.pythonRuntime.packageEmbedMode', '包嵌入模式') }}</label>
            <select v-model="pythonProfile.package_embed_mode" class="psp-input" :disabled="pythonReadonly" style="max-width:200px">
              <option value="none">none</option><option value="wheelhouse_rebuild">wheelhouse_rebuild</option><option value="full_venv">full_venv</option>
            </select>
          </div>

          <!-- Action buttons -->
          <h5 style="margin-top:14px">{{ t('framework.projectSettings.pythonRuntime.actions', '操作') }}</h5>
          <div class="psp-runtime-actions">
            <button class="psp-runtime-btn" :disabled="actionDisabled || actionLoading === 'health-check'" @click="doHealthCheck">
              {{ actionLoading === 'health-check' ? t('framework.projectSettings.pythonRuntime.checking', '检查中…') : t('framework.projectSettings.pythonRuntime.healthCheck', '健康检查') }}
            </button>
            <button class="psp-runtime-btn" :disabled="actionDisabled || actionLoading === 'prepare'" @click="doPrepare">
              {{ actionLoading === 'prepare' ? t('framework.projectSettings.pythonRuntime.preparing', '准备中…') : t('framework.projectSettings.pythonRuntime.prepare', '准备') }}
            </button>
            <button class="psp-runtime-btn" :disabled="actionDisabled || actionLoading === 'rebuild'" @click="doRebuild">
              {{ actionLoading === 'rebuild' ? t('framework.projectSettings.pythonRuntime.rebuilding', '重建中…') : t('framework.projectSettings.pythonRuntime.rebuild', '重建') }}
            </button>
            <button class="psp-runtime-btn" :disabled="actionDisabled || actionLoading === 'clear'" @click="doClear">
              {{ actionLoading === 'clear' ? t('framework.projectSettings.pythonRuntime.clearing', '清理中…') : t('framework.projectSettings.pythonRuntime.clear', '清理') }}
            </button>
            <button class="psp-runtime-btn" :disabled="exportDisabled || actionLoading === 'export'" @click="doExportBundle">
              {{ actionLoading === 'export' ? t('framework.projectSettings.pythonRuntime.exporting', '导出中…') : t('framework.projectSettings.pythonRuntime.export', '导出') }}
            </button>
          </div>
          <div v-if="isWcrun" class="psp-field-hint">{{ t('framework.projectSettings.pythonRuntime.hintWcrun', '📦 .wcrun 包已加载 — Python 运行时设置与操作均不可用') }}</div>
          <div v-else-if="!pythonProfile.runtime_enabled" class="psp-field-hint">{{ t('framework.projectSettings.pythonRuntime.hintEnableFirst', '启用运行时后，操作按钮可用') }}</div>
          <div v-else-if="pythonProfile.package_embed_mode === 'none'" class="psp-field-hint">{{ t('framework.projectSettings.pythonRuntime.hintExportUnavailable', '包嵌入模式为 "none" 时，导出不可用') }}</div>
        </template>
        <template v-else-if="active === 'encryptedParameters'">
          <h5>{{ t('framework.projectSettings.encryptedParameters.title', '加密参数') }}</h5>
          <div class="psp-field"><label>{{ t('framework.projectSettings.encryptedParameters.setId', '集合 ID') }}</label><input v-model="encryptedParameterSetId" class="psp-input" :disabled="sectionReadonly" /></div>
          <div v-for="(parameter, index) in encryptedParameterRows" :key="index" class="psp-var-row">
            <input v-model="parameter.parameter_id" class="psp-input" :placeholder="t('framework.projectSettings.encryptedParameters.parameterId', '参数 ID')" :disabled="sectionReadonly" />
            <input v-model="parameter.name" class="psp-input" :placeholder="t('framework.projectSettings.encryptedParameters.name', '名称')" :disabled="sectionReadonly" />
            <input v-model="parameter.type" class="psp-input" :placeholder="t('framework.projectSettings.encryptedParameters.type', '类型')" :disabled="sectionReadonly" />
            <input v-model="parameter.value" type="password" class="psp-input" autocomplete="new-password" :placeholder="t('framework.projectSettings.encryptedParameters.value', '值')" :disabled="sectionReadonly" />
            <button class="psp-rm" type="button" :disabled="sectionReadonly" @click="removeEncryptedParameter(index)">✕</button>
          </div>
          <button class="psp-add" type="button" :disabled="sectionReadonly" @click="addEncryptedParameter">{{ t('framework.projectSettings.encryptedParameters.add', '+ 新增参数') }}</button>
          <div class="psp-field"><label>{{ t('framework.projectSettings.encryptedParameters.password', '加密密码') }}</label><input v-model="encryptedParameterPassword" type="password" class="psp-input" autocomplete="new-password" :disabled="sectionReadonly" /></div>
          <div v-if="encryptedParameterSummary.configured" class="psp-field"><label>{{ t('framework.projectSettings.encryptedParameters.confirmOverwrite', '确认覆盖') }}</label><input v-model="encryptedParameterOverwriteConfirmed" type="checkbox" :disabled="sectionReadonly" /></div>
          <button class="psp-runtime-btn" :disabled="sectionReadonly" @click="saveEncryptedParameters">{{ t('framework.projectSettings.encryptedParameters.save', '保存加密参数') }}</button>
          <template v-if="encryptedParameterSummary.configured">
            <h5 style="margin-top:14px">{{ t('framework.projectSettings.encryptedParameters.rekeyTitle', '修改密码') }}</h5>
            <div class="psp-field"><label>{{ t('framework.projectSettings.encryptedParameters.currentPassword', '当前密码') }}</label><input v-model="encryptedParameterCurrentPassword" type="password" class="psp-input" autocomplete="current-password" :disabled="sectionReadonly" /></div>
            <div class="psp-field"><label>{{ t('framework.projectSettings.encryptedParameters.newPassword', '新密码') }}</label><input v-model="encryptedParameterNewPassword" type="password" class="psp-input" autocomplete="new-password" :disabled="sectionReadonly" /></div>
            <button class="psp-runtime-btn" :disabled="sectionReadonly" @click="rekeyEncryptedParameters">{{ t('framework.projectSettings.encryptedParameters.rekey', '更新密码') }}</button>
            <div class="psp-field" style="margin-top:14px"><label>{{ t('framework.projectSettings.encryptedParameters.confirmDelete', '确认删除') }}</label><input v-model="encryptedParameterDeleteConfirmed" type="checkbox" :disabled="sectionReadonly" /></div>
            <button class="psp-sec-enable-btn" :disabled="sectionReadonly || !encryptedParameterDeleteConfirmed" @click="deleteEncryptedParameters">{{ t('framework.projectSettings.encryptedParameters.delete', '删除加密参数') }}</button>
          </template>
        </template>
        <template v-else-if="active === 'status'">
          <div class="psp-state-grid">
            <div><span>{{ t('framework.projectSettings.status.sourceOfTruth', '真值来源') }}</span><code>{{ st.source_of_truth || '—' }}</code></div><div><span>{{ t('framework.projectSettings.status.stateSource', '状态来源') }}</span><code>{{ st.state_source || '—' }}</code></div><div><span>{{ t('framework.projectSettings.status.schemaVersion', 'Schema 版本') }}</span><code>{{ st.project_settings_schema_version || '—' }}</code></div><div><span>{{ t('framework.projectSettings.status.isDirty', '是否 dirty') }}</span><code>{{ st.is_dirty ? t('framework.projectSettings.common.yes', '是') : t('framework.projectSettings.common.no', '否') }}</code></div>
            <div v-if="st.project_file_path"><span>{{ t('framework.projectSettings.status.projectFile', '项目文件') }}</span><code class="psp-path">{{ st.project_file_path }}</code></div><div v-if="st.project_settings_path"><span>{{ t('framework.projectSettings.status.settingsFile', '设置文件') }}</span><code class="psp-path">{{ st.project_settings_path }}</code></div><div v-if="st.session_dir"><span>{{ t('framework.projectSettings.status.sessionDir', '会话目录') }}</span><code class="psp-path">{{ st.session_dir }}</code></div>
            <div><span>{{ t('framework.projectSettings.status.externalResources', 'External 资源') }}</span><code>{{ st.has_external_resources ? t('framework.projectSettings.common.yes', '是') : t('framework.projectSettings.common.no', '否') }}</code></div><div><span>{{ t('framework.projectSettings.status.embeddedResourceCount', 'Embedded 资源数') }}</span><code>{{ st.embedded_resource_count ?? '—' }}</code></div><div><span>{{ t('framework.projectSettings.status.externalResourceCount', 'External 资源数') }}</span><code>{{ st.external_resource_count ?? '—' }}</code></div><div><span>{{ t('framework.projectSettings.status.defaultOutputName', '默认输出名') }}</span><code>{{ st.package_default_output_name || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>{{ t('framework.projectSettings.status.graphDataVersion', '图数据版本') }}</span><code>{{ st.main_graph_compatibility.graph_data_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>{{ t('framework.projectSettings.status.builtWithVersion', '创建时版本') }}</span><code>{{ st.main_graph_compatibility.built_with_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>{{ t('framework.projectSettings.status.minimumLoaderVersion', '最低加载版本') }}</span><code>{{ st.main_graph_compatibility.minimum_loader_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>{{ t('framework.projectSettings.status.lastUpgradedVersion', '最近升级版本') }}</span><code>{{ st.main_graph_compatibility.last_upgraded_by_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>{{ t('framework.projectSettings.status.legacyUnversioned', '历史无版本图') }}</span><code>{{ st.main_graph_compatibility.is_legacy_unversioned ? t('framework.projectSettings.common.yes', '是') : t('framework.projectSettings.common.no', '否') }}</code></div>
          </div>
        </template>
      </div>
    </div>
    <div class="psp-ft"><button class="psp-btn-save" @click="save" :disabled="saveState === 'saving' || isWcrun">{{ isWcrun ? t('framework.projectSettings.footer.wcrunReadonly', '.wcrun 只读') : t('framework.projectSettings.footer.saveAll', '保存全部设置') }}</button></div>
  </div>
</template>
<style scoped>
.psp-root { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.psp-hd { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); font-size: var(--text-body); font-weight: 600; color: var(--text-primary); flex-shrink: 0; }
.psp-source { font-size: var(--text-caption); color: var(--text-disabled); }
.psp-dirty { font-size: var(--text-caption); color: var(--state-warning); }
.psp-clean { font-size: var(--text-caption); color: var(--state-success); }
.psp-st-saving { font-size: var(--text-caption); color: var(--state-warning); }
.psp-st-saved { font-size: var(--text-caption); color: var(--state-success); }
.psp-st-err { font-size: var(--text-caption); color: var(--state-error); }
.psp-open-dir { margin-left: auto; padding: 2px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.psp-open-dir:hover:not(:disabled) { background: var(--bg-hover); }
.psp-open-dir:disabled { opacity: 0.4; cursor: not-allowed; }
.psp-readonly-banner { padding: 4px var(--space-md); background: rgba(232,152,104,0.12); color: var(--state-warning); font-size: var(--text-small); border-bottom: 1px solid var(--border-subtle); flex-shrink: 0; }
.psp-body { display: flex; flex: 1; overflow: hidden; }
.psp-nav { width: 110px; flex-shrink: 0; border-right: 1px solid var(--border-subtle); padding: var(--space-xs) 0; overflow-y: auto; }
.psp-nav-item { display: block; width: 100%; padding: 5px 12px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; font-size: var(--text-small); text-align: left; }
.psp-nav-item:hover { background: var(--bg-hover); }
.psp-nav-item.active { background: var(--bg-selected); color: var(--accent); font-weight: 600; }
.psp-content { flex: 1; padding: var(--space-md); overflow-y: auto; }
.psp-content h5 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }
.psp-field { display: flex; align-items: center; gap: var(--space-sm); padding: 3px 0; font-size: var(--text-small); }
.psp-field label { width: 70px; flex-shrink: 0; color: var(--text-disabled); }
.psp-input { flex: 1; padding: 2px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); }
.psp-input:disabled { opacity: 0.5; cursor: not-allowed; }
.psp-ro { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); background: var(--bg-input); padding: 2px 6px; border-radius: var(--radius-sm); }
.psp-textarea { resize: vertical; }
.psp-tags { display: flex; flex-wrap: wrap; gap: 3px; align-items: center; flex: 1; }
.psp-tag { display: inline-flex; align-items: center; gap: 2px; padding: 0 5px; background: var(--accent-light); color: var(--accent); border-radius: 2px; font-size: var(--text-caption); }
.psp-tag-rm { border: none; background: transparent; color: var(--accent); cursor: pointer; font-size: 10px; padding: 0; }
.psp-tag-input { padding: 2px 4px; border: 1px dashed var(--border-default); border-radius: 2px; background: transparent; color: var(--text-secondary); font-size: var(--text-caption); }
.psp-var-row { display: flex; gap: 4px; padding: 2px 0; align-items: center; }
.psp-rm { width: 18px; height: 18px; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; }
.psp-rm:hover { color: var(--state-error); }
.psp-add { margin-top: 2px; padding: 1px 8px; border: 1px dashed var(--border-default); background: transparent; color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); border-radius: var(--radius-sm); }
.psp-add:hover { border-color: var(--accent); color: var(--accent); }
.psp-empty { font-size: var(--text-small); color: var(--text-disabled); padding: 4px 0; }
.psp-state-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: var(--text-small); }
.psp-state-grid div { display: flex; justify-content: space-between; align-items: center; }
.psp-state-grid span { color: var(--text-disabled); }
.psp-state-grid code { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); background: var(--bg-input); padding: 0 4px; border-radius: 2px; }
.psp-path { word-break: break-all; }
.psp-ft { padding: var(--space-sm) var(--space-md); border-top: 1px solid var(--border-subtle); flex-shrink: 0; }
.psp-btn-save { padding: 4px 14px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--accent); color: #fff; cursor: pointer; font-size: var(--text-small); }
.psp-btn-save:hover:not(:disabled) { background: var(--accent-hover); }
.psp-btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.psp-runtime-banner { padding: 6px 10px; border-radius: var(--radius-sm); margin-bottom: 10px; font-size: var(--text-small); display: flex; flex-direction: column; gap: 2px; }
.psp-runtime-banner--ready { background: rgba(107,154,102,0.12); color: var(--state-success); }
.psp-runtime-banner--missing, .psp-runtime-banner--stale { background: rgba(232,152,104,0.12); color: var(--state-warning); }
.psp-runtime-banner--broken { background: rgba(208,112,96,0.08); color: var(--state-error); }
.psp-runtime-banner--disabled, .psp-runtime-banner--unknown { background: rgba(0,0,0,0.04); color: var(--text-disabled); }
.psp-runtime-msg { font-size: var(--text-caption); color: var(--text-secondary); }
.psp-runtime-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.psp-runtime-btn { padding: 4px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.psp-runtime-btn:hover:not(:disabled) { background: var(--bg-hover); }
.psp-runtime-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.psp-path-row { display: flex; gap: 2px; flex: 1; }
.psp-path-row .psp-input { flex: 1; }
.psp-pick-btn { padding: 2px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.psp-pick-btn:hover:not(:disabled) { background: var(--bg-hover); }
.psp-pick-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.psp-vars-list { flex: 1; }
.psp-field-hint { font-size: var(--text-caption); color: var(--text-disabled); margin-top: 4px; padding: 2px 0; }
.psp-sec-banner { padding: 8px var(--space-md); background: rgba(208,112,96,0.08); border-bottom: 1px solid rgba(208,112,96,0.2); flex-shrink: 0; }
.psp-sec-title { font-size: var(--text-small); font-weight: 600; color: var(--state-error); margin-bottom: 4px; }
.psp-sec-entries { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.psp-sec-entry { display: flex; align-items: center; gap: 4px; padding: 1px 8px; background: rgba(208,112,96,0.06); border: 1px solid rgba(208,112,96,0.15); border-radius: var(--radius-sm); font-size: var(--text-caption); color: var(--state-error); }
.psp-sec-req { color: var(--text-disabled); }
.psp-sec-enable-btn { padding: 4px 14px; border: 1px solid var(--state-error); border-radius: var(--radius-sm); background: transparent; color: var(--state-error); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.psp-sec-enable-btn:hover:not(:disabled) { background: rgba(208,112,96,0.1); }
.psp-sec-enable-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
