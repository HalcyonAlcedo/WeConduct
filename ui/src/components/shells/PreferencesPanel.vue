<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { postPreferences, postPreferencesReset, fetchPreferences, postPreferencesPreview, postFileDialog, fetchConfigValues, patchConfigValues, resetConfigValues, postOpenPath } from '@/services/api'
import type { PreferencesUpdateRequest } from '@/types/domains/api'
import { useToastStore } from '@/stores/toastStore'
import { useThemeStore } from '@/stores/themeStore'
import { useFontScaleStore } from '@/stores/fontScaleStore'
import { useLanguageStore } from '@/stores/languageStore'
import { SOURCE_LOCALE, t } from '@/i18n'

const workspace = useWorkspaceStore()
const toast = useToastStore()
const theme = useThemeStore()
const fontScale = useFontScaleStore()
const language = useLanguageStore()
const active = ref('general')

// Built-in source locale (needs no pack) + every discovered external pack.
// Chinese is the hardcoded source, so it is always selectable even with no packs on disk.
// Field-aware: 界面语言 and 资源语言 share the same discovered-pack list but each
// keeps its own persisted-but-missing locale visible.
function languageOptionsFor(fieldKey: string): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = [{ value: SOURCE_LOCALE, label: t('framework.preferences.builtinLocaleLabel', '简体中文（内置）') }]
  for (const pack of language.available) {
    if (pack.locale === SOURCE_LOCALE) continue
    options.push({ value: pack.locale, label: pack.display_name || pack.locale })
  }
  // If the persisted locale has no pack on disk, keep it visible (marked missing)
  // so the dropdown reflects the stored value instead of silently mismatching.
  const current = getField('program_settings', fieldKey)
  if (typeof current === 'string' && current && !options.some(o => o.value === current)) {
    options.push({ value: current, label: t('framework.preferences.localeNotInstalled', `${current}（未安装）`, { locale: current }) })
  }
  return options
}

/** Open the program's languages/ data directory in the OS file manager. */
async function openDataDir() {
  const dir = language.directory
  if (!dir) return
  try {
    await postOpenPath({ path: dir })
  } catch (e: any) {
    if (e?.status === 503) {
      toast.info('', workspace.isLimitedBrowser
        ? t('framework.preferences.openDataDirLimited', '受限浏览器模式：无法打开系统目录，请手动前往该路径')
        : t('framework.preferences.openDataDirUnsupported', '当前运行环境不支持打开系统目录，请手动前往该路径'))
    } else {
      toast.error(t('framework.preferences.openDataDirFailed', '打开失败'), e?.message)
    }
  }
}

interface FieldDef { key: string; label: string; type: 'text' | 'number' | 'bool' | 'select' | 'object' | 'json' | 'directory_list' | 'string_list' | 'font_scale' | 'language'; options?: string[]; hint?: string }

// Font scale presets: numeric multiplier (persisted) → percentage label (shown).
const FONT_SCALE_PRESETS: { value: number; label: string }[] = [
  { value: 0.85, label: '85%' },
  { value: 1.0, label: '100%' },
  { value: 1.15, label: '115%' },
  { value: 1.25, label: '125%' },
  { value: 1.5, label: '150%' },
]

const FIELD_DEFS: Record<string, FieldDef[]> = {
  general: [
    { key: 'language', label: t('framework.preferences.general.language', '界面语言'), type: 'language', hint: t('framework.preferences.general.languageHint', '主界面语言。内置简体中文；其他语言需在程序目录 languages/ 放置语言包') },
    { key: 'resource_language', label: t('framework.preferences.general.resourceLanguage', '资源语言'), type: 'language', hint: t('framework.preferences.general.resourceLanguageHint', '各模块/节点内容的语言，与界面语言独立配置') },
    { key: 'theme', label: t('framework.preferences.general.theme', '主题'), type: 'select', options: ['light', 'dark', 'system'] }, { key: 'default_window_size', label: t('framework.preferences.general.defaultWindowSize', '默认窗口尺寸'), type: 'object', hint: t('framework.preferences.general.defaultWindowSizeHint', '宽度 × 高度（像素）') },
    { key: 'default_project_directory', label: t('framework.preferences.general.defaultProjectDirectory', '默认项目目录'), type: 'text' },
    { key: 'recent_project_limit', label: t('framework.preferences.general.recentProjectLimit', '最近项目上限'), type: 'number' }, { key: 'preferences_auto_save', label: t('framework.preferences.general.autoSave', '自动保存'), type: 'bool' }, { key: 'check_updates_on_startup', label: t('framework.preferences.general.checkUpdatesOnStartup', '启动时检查更新'), type: 'bool' }, { key: 'font_scale', label: t('framework.preferences.general.fontScale', '字体缩放'), type: 'font_scale' },
  ],
  security: [
    { key: 'confirm_high_risk_actions', label: t('framework.preferences.security.confirmHighRiskActions', '确认高风险操作'), type: 'bool' }, { key: 'show_security_warnings_in_runtime', label: t('framework.preferences.security.showSecurityWarningsInRuntime', '运行时显示安全警告'), type: 'bool' },
    { key: 'log_security_events', label: t('framework.preferences.security.logSecurityEvents', '记录安全事件'), type: 'bool' },
    { key: 'allow_file_access', label: t('framework.preferences.security.allowFileAccess', '允许文件访问'), type: 'bool' }, { key: 'file_access_scope', label: t('framework.preferences.security.fileAccessScope', '文件访问范围'), type: 'select', options: ['restricted', 'custom_roots', 'allow_all'] },
    { key: 'file_access_require_absolute_path', label: t('framework.preferences.security.fileAccessRequireAbsolutePath', '要求绝对路径'), type: 'bool' },
    { key: 'file_access_allowed_roots', label: t('framework.preferences.security.fileAccessAllowedRoots', '允许访问目录'), type: 'directory_list', hint: t('framework.preferences.security.fileAccessAllowedRootsHint', '仅在 custom_roots 模式下生效') },
    { key: 'file_access_blocked_roots', label: t('framework.preferences.security.fileAccessBlockedRoots', '禁止访问目录'), type: 'directory_list' },
    { key: 'file_access_allowed_extensions', label: t('framework.preferences.security.fileAccessAllowedExtensions', '允许文件扩展名'), type: 'text', hint: t('framework.preferences.security.fileAccessAllowedExtensionsHint', '逗号分隔，如 .txt,.json') },
    { key: 'file_access_blocked_extensions', label: t('framework.preferences.security.fileAccessBlockedExtensions', '禁止文件扩展名'), type: 'text', hint: t('framework.preferences.security.fileAccessBlockedExtensionsHint', '逗号分隔，如 .exe,.bat') },
    { key: 'allow_browser_executor', label: t('framework.preferences.security.allowBrowserExecutor', '允许浏览器执行器'), type: 'bool' },
    { key: 'allow_browser_screenshots', label: t('framework.preferences.security.allowBrowserScreenshots', '允许截图'), type: 'bool' },
    { key: 'allow_cookie_manipulation', label: t('framework.preferences.security.allowCookieManipulation', '允许 Cookie 操作'), type: 'bool' },
    { key: 'allow_browser_storage_manipulation', label: t('framework.preferences.security.allowBrowserStorageManipulation', '允许 Storage 操作'), type: 'bool' },
    { key: 'allow_browser_uploads', label: t('framework.preferences.security.allowBrowserUploads', '允许上传文件'), type: 'bool' },
    { key: 'allow_browser_downloads', label: t('framework.preferences.security.allowBrowserDownloads', '允许下载文件'), type: 'bool' },
    { key: 'allow_new_browser_windows', label: t('framework.preferences.security.allowNewBrowserWindows', '允许新窗口'), type: 'bool' },
    { key: 'allow_external_programs', label: t('framework.preferences.security.allowExternalPrograms', '允许外部程序'), type: 'bool' },
    { key: 'allow_python_execution', label: t('framework.preferences.security.allowPythonExecution', '允许 Python 执行'), type: 'bool' },
    { key: 'allow_local_network_access', label: t('framework.preferences.security.allowLocalNetworkAccess', '允许本地网络'), type: 'bool' },
    { key: 'allow_remote_network_access', label: t('framework.preferences.security.allowRemoteNetworkAccess', '允许远程网络'), type: 'bool' },
    { key: 'allow_js_injection', label: t('framework.preferences.security.allowJsInjection', '允许 JS 注入'), type: 'bool' },
    { key: 'allow_js_evaluation', label: t('framework.preferences.security.allowJsEvaluation', '允许 JS 执行'), type: 'bool' },
  ],
  python: [
    { key: 'python_executable_path', label: t('framework.preferences.python.pythonExecutablePath', 'Python 路径'), type: 'text' }, { key: 'timeout_seconds', label: t('framework.preferences.python.timeoutSeconds', '超时（秒）'), type: 'number' },
    { key: 'sandbox_mode', label: t('framework.preferences.python.sandboxMode', '沙盒模式'), type: 'select', options: ['restricted'] }, { key: 'capture_stdout_stderr', label: t('framework.preferences.python.captureStdoutStderr', '捕获标准输出/错误'), type: 'bool' },
    { key: 'variable_apply_mode', label: t('framework.preferences.python.variableApplyMode', '调试变量应用策略'), type: 'select', options: ['staged', 'immediate'], hint: t('framework.preferences.python.variableApplyModeHint', 'staged 为暂存后再继续调试，immediate 为立即生效') },
    { key: 'default_python_version_spec', label: t('framework.preferences.python.defaultPythonVersionSpec', '默认 Python 版本'), type: 'text' },
    { key: 'default_cache_location_mode', label: t('framework.preferences.python.defaultCacheLocationMode', '默认缓存位置模式'), type: 'select', options: ['software_cache', 'project_cache'] },
    { key: 'default_project_cache_mode', label: t('framework.preferences.python.defaultProjectCacheMode', '默认项目缓存模式'), type: 'select', options: ['full_venv', 'wheelhouse_rebuild'] },
    { key: 'default_requirements_source_mode', label: t('framework.preferences.python.defaultRequirementsSourceMode', '默认需求来源模式'), type: 'select', options: ['inline', 'requirements_txt', 'lock_file'] },
    { key: 'default_package_embed_mode', label: t('framework.preferences.python.defaultPackageEmbedMode', '默认包嵌入模式'), type: 'select', options: ['none', 'wheelhouse_rebuild', 'full_venv'] },
    { key: 'blocked_import_modules', label: t('framework.preferences.python.blockedImportModules', '阻断导入模块'), type: 'string_list', hint: t('framework.preferences.python.blockedImportModulesHint', '这些模块会在 python.run 中被禁止导入。删除某项后，项目脚本即可导入该模块。') },
  ],
  nodegraph: [
    { key: 'show_node_id_on_node', label: t('framework.preferences.nodegraph.showNodeIdOnNode', '显示节点 ID'), type: 'bool' },
    { key: 'show_disabled_resource_badge', label: t('framework.preferences.nodegraph.showDisabledResourceBadge', '显示禁用资源徽章'), type: 'bool' }, { key: 'snap_to_grid', label: t('framework.preferences.nodegraph.snapToGrid', '吸附网格'), type: 'bool' },
    { key: 'grid_enabled', label: t('framework.preferences.nodegraph.gridEnabled', '网格启用'), type: 'bool' }, { key: 'auto_open_node_on_drop', label: t('framework.preferences.nodegraph.autoOpenNodeOnDrop', '拖放后自动打开节点'), type: 'bool' },
    { key: 'confirm_delete_node', label: t('framework.preferences.nodegraph.confirmDeleteNode', '删除节点确认'), type: 'bool' }, { key: 'show_inline_config_summary', label: t('framework.preferences.nodegraph.showInlineConfigSummary', '显示内联配置摘要'), type: 'bool' },
    { key: 'edge_line_style', label: t('framework.preferences.nodegraph.edgeLineStyle', '连线样式'), type: 'select', options: ['smoothstep', 'straight', 'bezier'], hint: t('framework.preferences.nodegraph.edgeLineStyleHint', 'smoothstep 平滑折线 / straight 直线 / bezier 曲线') },
    { key: 'save_conflict_policy', label: t('framework.preferences.nodegraph.saveConflictPolicy', '保存冲突策略'), type: 'select', options: ['prefer_current_graph', 'strict'] },
  ],
}

const SECTION_MAP: Record<string, string> = { general: 'program_settings', security: 'security_settings', python: 'python_runtime_settings', nodegraph: 'graph_settings' }
const CATS = [{ key: 'general', label: t('framework.preferences.cats.general', '程序设置') }, { key: 'security', label: t('framework.preferences.cats.security', '安全设置') }, { key: 'python', label: t('framework.preferences.cats.python', 'Python 运行时设置') }, { key: 'nodegraph', label: t('framework.preferences.cats.nodegraph', '节点图设置') }]

const form = reactive<Record<string, Record<string, any>>>({ program_settings: {}, security_settings: {}, python_runtime_settings: {}, graph_settings: {} })
const saveState = reactive<Record<string, 'idle' | 'saving' | 'saved' | 'error'>>({}); const saveError = reactive<Record<string, string>>({})

function normalizeRoots(value: unknown): string[] { if (!Array.isArray(value)) return []; const result: string[] = []; for (const item of value) { if (typeof item !== 'string') continue; const n = item.trim(); if (!n || result.includes(n)) continue; result.push(n) } return result }
function normalizePreferenceValue(value: unknown): unknown {
  return value
}

function initForm() {
  const prefs = workspace.snapshot?.preferences || {}
  for (const section of Object.values(SECTION_MAP)) {
    const source = (prefs as Record<string, any>)[section] || {}
    const next = Object.fromEntries(
      Object.entries(source).map(([key, value]) => [key, normalizePreferenceValue(value)]),
    )
    if (section === 'security_settings') { next.file_access_allowed_roots = normalizeRoots(next.file_access_allowed_roots); next.file_access_blocked_roots = normalizeRoots(next.file_access_blocked_roots) }
    form[section] = next; saveState[section] = 'idle'; saveError[section] = ''
  }
  form.graph_settings = {
    ...form.graph_settings,
    ...normalizeGraphPreferences((workspace.snapshot as any)?.graph_workspace?.graph_preferences),
  }
}
async function loadGraphPreferences() {
  try {
    const result = await fetchConfigValues<{ editor_preferences?: Record<string, unknown> }>('graph')
    const editorPreferences = normalizeGraphPreferences(result.values?.editor_preferences)
    if (Object.keys(editorPreferences).length) {
      form.graph_settings = {
        ...form.graph_settings,
        ...editorPreferences,
      }
    }
  } catch {}
}
onMounted(async () => { initForm(); await loadGraphPreferences(); language.refreshAvailable().catch(() => {}) })
watch(() => workspace.snapshot?.preferences, () => initForm(), { deep: true })
watch(() => (workspace.snapshot as any)?.graph_workspace?.graph_preferences, () => {
  form.graph_settings = {
    ...form.graph_settings,
    ...normalizeGraphPreferences((workspace.snapshot as any)?.graph_workspace?.graph_preferences),
  }
}, { deep: true })

const prefsState = computed(() => (workspace.snapshot as any)?.graph_workspace?.preferences_state || {})
function fieldState(s: string, k: string): string | undefined { const n = (prefsState.value as any)[s]; if (!n || typeof n !== 'object') return; const v = n[k]; return typeof v === 'string' ? v : undefined }
function stateLabel(s: string | undefined): string { if (s === 'active') return t('framework.preferences.fieldState.active', '已接入'); if (s === 'stored_only') return t('framework.preferences.fieldState.storedOnly', '待接入'); return '—' }

const autoSaveTimers: Record<string, ReturnType<typeof setTimeout>> = {}
const autoSaveEnabled = computed(() => !!form.program_settings?.preferences_auto_save)
const confirmDialog = ref<{ section: string; changes: { field: string; from: unknown; to: unknown; reason: string }[] } | null>(null)

function onFieldChange(section: string) { if (!autoSaveEnabled.value) return; clearTimeout(autoSaveTimers[section]); saveState[section] = 'saving'; autoSaveTimers[section] = setTimeout(() => doSave(section), 400) }

async function doSave(section: string) {
  saveState[section] = 'saving'; saveError[section] = ''
  try {
    if (section === 'graph_settings') {
      const result = await patchConfigValues<{ editor_preferences?: Record<string, unknown> }>({
        scope: 'graph',
        operations: graphPreferenceOperations(form[section]),
        confirm_high_risk: false,
      })
      form.graph_settings = {
        ...form.graph_settings,
        ...normalizeGraphPreferences(result.values?.editor_preferences),
      }
      saveState[section] = 'saved'; setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000)
      await workspace.refreshSnapshot()
      return
    }
    const values = flattenForSave(section, form[section])
    if (section === 'security_settings') {
      try { const preview = await postPreferencesPreview({ section, values }); if (preview.confirmation_required && preview.high_risk_changes.length) { confirmDialog.value = { section, changes: preview.high_risk_changes }; saveState[section] = 'idle'; return } } catch {}
    }
    await postPreferences({ section, values } as PreferencesUpdateRequest)
    saveState[section] = 'saved'; setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000)
    try {
      const r = await fetchPreferences()
      if (section === 'security_settings') {
        form[section] = { ...form[section], ...(r.preferences[section] as any || {}), file_access_allowed_roots: normalizeRoots((r.preferences[section] as any)?.file_access_allowed_roots), file_access_blocked_roots: normalizeRoots((r.preferences[section] as any)?.file_access_blocked_roots) }
      } else {
        const savedValues = (r.preferences[section] as Record<string, any>) || {}
        form[section] = { ...form[section], ...Object.fromEntries(Object.entries(savedValues).map(([key, value]) => [key, normalizePreferenceValue(value)])) }
      }
    } catch {}
    await workspace.refreshSnapshot()
  } catch (e: any) {
    if (e?.body?.error === 'high_risk_confirmation_required') { confirmDialog.value = { section, changes: e.body.high_risk_changes || [] }; saveState[section] = 'idle'; return }
    saveState[section] = 'error'; saveError[section] = e?.message || t('framework.preferences.saveFailed', '保存失败')
  }
}

async function confirmHighRiskSave() {
  if (!confirmDialog.value) return
  const { section } = confirmDialog.value
  confirmDialog.value = null
  saveState[section] = 'saving'
  try {
    await postPreferences({ section, values: flattenForSave(section, form[section]), confirm_high_risk: true } as PreferencesUpdateRequest)
    saveState[section] = 'saved'
    setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000)
    try {
      const r = await fetchPreferences()
      const savedValues = (r.preferences[section] as Record<string, any>) || {}
      if (section === 'security_settings') {
        form[section] = { ...form[section], ...savedValues, file_access_allowed_roots: normalizeRoots(savedValues.file_access_allowed_roots), file_access_blocked_roots: normalizeRoots(savedValues.file_access_blocked_roots) }
      } else {
        form[section] = { ...form[section], ...Object.fromEntries(Object.entries(savedValues).map(([key, value]) => [key, normalizePreferenceValue(value)])) }
      }
    } catch {}
    await workspace.refreshSnapshot()
  } catch (e: any) {
    saveState[section] = 'error'
    saveError[section] = e?.message || t('framework.preferences.saveFailed', '保存失败')
  }
}

function flattenForSave(section: string, vals: Record<string, any>): Record<string, unknown> {
  const r: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(vals)) {
    if (k === 'default_window_size') { r[k] = { width: (v as any)?.width ?? 800, height: (v as any)?.height ?? 600 }; continue }
    if (section === 'security_settings' && k === 'file_access_allowed_roots') { r[k] = normalizeRoots(v); continue }
    if (section === 'security_settings' && k === 'file_access_blocked_roots') { r[k] = normalizeRoots(v); continue }
    if (section === 'security_settings' && (k === 'file_access_allowed_extensions' || k === 'file_access_blocked_extensions')) { r[k] = typeof v === 'string' ? v.split(',').map(s => s.trim()).filter(Boolean) : Array.isArray(v) ? v : []; continue }
    r[k] = v
  }
  return r
}
function normalizeGraphPreferences(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.fromEntries(Object.entries(value as Record<string, unknown>))
}
function graphPreferenceOperations(values: Record<string, unknown>) {
  return Object.entries(values).map(([key, value]) => ({
    op: 'replace' as const,
    path: `/editor_preferences/${key}`,
    value,
  }))
}

function isRootsFieldVisible(): boolean { return getField('security_settings', 'allow_file_access') && getField('security_settings', 'file_access_scope') === 'custom_roots' }

// Directory list editor (parameterized by field key)
function getDirectoryList(fieldKey: string): string[] { return normalizeRoots(getField('security_settings', fieldKey)) }
function setDirectoryList(fieldKey: string, next: string[]) { setField('security_settings', fieldKey, normalizeRoots(next)) }
function addDirectoryItem(fieldKey: string, path: string) { const n = path.trim(); if (!n) return; const cur = getDirectoryList(fieldKey); if (cur.includes(n)) return; setDirectoryList(fieldKey, [...cur, n]) }
function removeDirectoryItem(fieldKey: string, path: string) { setDirectoryList(fieldKey, getDirectoryList(fieldKey).filter(item => item !== path)) }
async function pickDirectoryItem(fieldKey: string) { try { const r = await postFileDialog({ mode: 'open_folder', title: t('framework.preferences.dialog.pickDirectory', '选择目录') }); if (r.status === 'selected' && r.paths.length) addDirectoryItem(fieldKey, r.paths[0]) } catch (e: any) { if (e?.status === 503) toast.info('', workspace.isLimitedBrowser ? t('framework.preferences.dirPickerLimited', '受限浏览器模式：系统目录选择器不可用') : t('framework.preferences.dirPickerUnsupported', '当前运行环境不支持系统目录选择器')) } }
async function pickPythonPath() { try { const r = await postFileDialog({ mode: 'open_file', title: t('framework.preferences.dialog.pickPythonExecutable', '选择 Python 可执行文件') }); if (r.status === 'selected' && r.paths.length) setField('python_runtime_settings', 'python_executable_path', r.paths[0]) } catch (e: any) { if (e?.status === 503) toast.info('', workspace.isLimitedBrowser ? t('framework.preferences.filePickerLimited', '受限浏览器模式：系统文件选择器不可用') : t('framework.preferences.filePickerUnsupported', '当前运行环境不支持系统文件选择器')) } }
function getStringList(fieldKey: string): string[] { const v = getField(currentSection.value, fieldKey); return Array.isArray(v) ? v.filter((x: any) => typeof x === 'string') : [] }
function addStringListItem(fieldKey: string) { setField(currentSection.value, fieldKey, [...getStringList(fieldKey), '']) }
function removeStringListItem(fieldKey: string, idx: number) { const n = [...getStringList(fieldKey)]; n.splice(idx, 1); setField(currentSection.value, fieldKey, n) }
function updateStringListItem(fieldKey: string, idx: number, val: string) { const n = [...getStringList(fieldKey)]; n[idx] = val; setField(currentSection.value, fieldKey, n) }

// Extension display helper: convert string[] to comma-separated display
function extDisplay(fieldKey: string): string { const v = getField('security_settings', fieldKey); if (Array.isArray(v)) return v.join(', '); return typeof v === 'string' ? v : '' }

async function doReset(section: string) {
  saveState[section] = 'saving'
  saveError[section] = ''
  try {
    if (section === 'graph_settings') {
      const result = await resetConfigValues<{ editor_preferences?: Record<string, unknown> }>('graph')
      form.graph_settings = normalizeGraphPreferences(result.values?.editor_preferences)
      saveState[section] = 'saved'
      setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000)
      await workspace.refreshSnapshot()
      return
    }
    await postPreferencesReset()
    const result = await fetchPreferences()
    for (const current of Object.values(SECTION_MAP)) {
      if (current === 'graph_settings') continue
      const values = { ...((result.preferences as Record<string, any>)[current] || {}) }
      if (current === 'security_settings') {
        values.file_access_allowed_roots = normalizeRoots(values.file_access_allowed_roots)
      }
      form[current] = values
      saveState[current] = 'saved'
      setTimeout(() => { if (saveState[current] === 'saved') saveState[current] = 'idle' }, 2000)
    }
    await workspace.refreshSnapshot()
  } catch (error: any) {
    saveState[section] = 'error'
    saveError[section] = error?.message || t('framework.preferences.resetFailed', '重置失败')
  }
}

function saveStatusLabel(section: string): string { const s = saveState[section]; if (s === 'saving') return t('framework.preferences.status.savingEllipsis', '保存中…'); if (s === 'saved') return t('framework.preferences.status.saved', '已保存'); if (s === 'error') return t('framework.preferences.saveFailed', '保存失败'); return '' }
function getField(section: string, key: string): any { return form[section]?.[key] }
function setField(section: string, key: string, value: any) {
  if (form[section]) {
    form[section][key] = value
    // Theme, font scale & language are applied live as explicit user overrides.
    if (section === 'program_settings' && key === 'theme') {
      theme.setPreference(value)
    }
    if (section === 'program_settings' && key === 'font_scale') {
      fontScale.setScale(Number(value))
    }
    if (section === 'program_settings' && key === 'language') {
      language.setLocale(String(value)).catch(() => {})
    }
    if (section === 'program_settings' && key === 'resource_language') {
      language.setResourceLocale(String(value)).catch(() => {})
    }
    onFieldChange(section)
  }
}
function toggleBool(section: string, key: string) { setField(section, key, !getField(section, key)) }
const currentSection = computed(() => SECTION_MAP[active.value] || 'program_settings')
const currentFields = computed(() => {
  const fields = FIELD_DEFS[active.value] || []
  const sectionState = (prefsState.value as any)?.[currentSection.value]
  if (!sectionState || typeof sectionState !== 'object') return fields
  return fields.filter(field => sectionState[field.key] === 'active')
})
</script>
<template>
  <div class="pref">
    <div class="pref-nav"><button v-for="c in CATS" :key="c.key" :class="['pref-nav-item', { active: active === c.key }]" @click="active = c.key">{{ c.label }}<span v-if="saveState[SECTION_MAP[c.key]] === 'saving'" class="pref-st-saving">{{ t('framework.preferences.navState.saving', '保存中') }}</span><span v-else-if="saveState[SECTION_MAP[c.key]] === 'saved'" class="pref-st-saved">{{ t('framework.preferences.navState.saved', '已保存') }}</span><span v-else-if="saveState[SECTION_MAP[c.key]] === 'error'" class="pref-st-err">{{ t('framework.preferences.navState.error', '错误') }}</span></button></div>
    <div class="pref-content">
      <div class="pref-content-hd"><h4>{{ CATS.find(c => c.key === active)?.label }}</h4><div class="pref-content-actions"><span class="pref-status" :class="{'pref-status-saving':saveState[currentSection]==='saving','pref-status-saved':saveState[currentSection]==='saved','pref-status-err':saveState[currentSection]==='error'}">{{ saveStatusLabel(currentSection) }}</span></div></div>
      <div v-if="saveState[currentSection] === 'error'" class="pref-err-msg">{{ saveError[currentSection] }}</div>
      <div class="pref-auto-bar"><label class="pref-auto-label"><input type="checkbox" :checked="autoSaveEnabled" @change="toggleBool('program_settings', 'preferences_auto_save')" />{{ t('framework.preferences.autoSaveLabel', '自动保存（修改字段后自动提交）') }}</label></div>
      <div v-for="f in currentFields" :key="f.key" class="pref-field" v-show="f.key !== 'file_access_allowed_roots' || isRootsFieldVisible()">
        <label class="pref-field-label">{{ f.label }}</label><div class="pref-field-ctl">
          <template v-if="f.type === 'bool'"><label class="pref-check-label"><input type="checkbox" :checked="!!getField(currentSection, f.key)" @change="toggleBool(currentSection, f.key)" />{{ getField(currentSection, f.key) ? t('framework.preferences.common.yes', '是') : t('framework.preferences.common.no', '否') }}</label></template>
          <input v-else-if="f.type === 'number'" type="number" class="pref-input pref-input-num" :value="getField(currentSection, f.key) ?? ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).valueAsNumber)" />
          <select v-else-if="f.type === 'select'" class="pref-input" :value="getField(currentSection, f.key) || f.options?.[0] || ''" @change="setField(currentSection, f.key, ($event.target as HTMLSelectElement).value)"><option v-for="o in f.options" :key="o" :value="o">{{ o }}</option></select>
          <select v-else-if="f.type === 'language'" class="pref-input" :value="getField(currentSection, f.key) || 'zh-CN'" @change="setField(currentSection, f.key, ($event.target as HTMLSelectElement).value)"><option v-for="o in languageOptionsFor(f.key)" :key="o.value" :value="o.value">{{ o.label }}</option></select>
          <select v-else-if="f.type === 'font_scale'" class="pref-input" :value="String(Number(getField(currentSection, f.key) ?? 1))" @change="setField(currentSection, f.key, Number(($event.target as HTMLSelectElement).value))"><option v-for="o in FONT_SCALE_PRESETS" :key="o.value" :value="String(o.value)">{{ o.label }}</option></select>
          <template v-else-if="f.type === 'object' && f.key === 'default_window_size'"><input type="number" class="pref-input pref-input-num" :placeholder="t('framework.preferences.windowSize.width', '宽度')" :value="(getField(currentSection, 'default_window_size') || {}).width ?? ''" @input="(e: Event) => { const ws = { ...(form[currentSection]?.default_window_size || {}), width: (e.target as HTMLInputElement).valueAsNumber }; setField(currentSection, 'default_window_size', ws) }" /><span class="pref-obj-sep">×</span><input type="number" class="pref-input pref-input-num" :placeholder="t('framework.preferences.windowSize.height', '高度')" :value="(getField(currentSection, 'default_window_size') || {}).height ?? ''" @input="(e: Event) => { const ws = { ...(form[currentSection]?.default_window_size || {}), height: (e.target as HTMLInputElement).valueAsNumber }; setField(currentSection, 'default_window_size', ws) }" /></template>
          <!-- Directory list editor -->
          <div v-else-if="f.type === 'directory_list'" class="pref-roots-editor">
            <div class="pref-roots-list" v-if="getDirectoryList(f.key).length"><div v-for="root in getDirectoryList(f.key)" :key="root" class="pref-roots-item"><span class="pref-roots-path">{{ root }}</span><button class="pref-btn pref-btn-rm" type="button" @click="removeDirectoryItem(f.key, root)">✕</button></div></div>
            <div v-else class="pref-roots-empty">{{ t('framework.preferences.directoryList.empty', '未配置目录') }}</div>
            <div class="pref-roots-actions"><button class="pref-btn pref-btn-sm" type="button" @click="pickDirectoryItem(f.key)">{{ t('framework.preferences.directoryList.pickDir', '📁 选择目录') }}</button></div>
            <div v-if="f.hint" class="pref-field-hint">{{ f.hint }}</div>
          </div>
          <!-- Path picker for python_executable_path -->
          <div v-else-if="f.key === 'python_executable_path'" class="pref-path-row">
            <input type="text" class="pref-input" :value="getField(currentSection, f.key) ?? ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
            <button class="pref-btn pref-btn-pick" type="button" @click="pickPythonPath">…</button>
          </div>
          <!-- String list editor -->
          <div v-else-if="f.type === 'string_list'" class="pref-string-list">
            <div v-for="(item, i) in getStringList(f.key)" :key="i" class="pref-string-item">
              <input class="pref-input" :value="item" @input="updateStringListItem(f.key, i, ($event.target as HTMLInputElement).value)" :placeholder="t('framework.preferences.stringList.modulePlaceholder', '模块名')" />
              <button class="pref-btn pref-btn-rm" type="button" @click="removeStringListItem(f.key, i)">✕</button>
            </div>
            <button class="pref-btn pref-btn-sm" type="button" @click="addStringListItem(f.key)">{{ t('framework.preferences.stringList.add', '+ 新增') }}</button>
            <div v-if="f.hint" class="pref-field-hint">{{ f.hint }}</div>
          </div>
          <!-- Extension fields (display string[] as comma-separated) -->
          <input v-else-if="f.key.includes('extensions')" type="text" class="pref-input" :value="extDisplay(f.key)" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
          <!-- Text -->
          <input v-else type="text" class="pref-input" :value="typeof getField(currentSection, f.key) === 'string' ? getField(currentSection, f.key) : typeof getField(currentSection, f.key) === 'number' ? String(getField(currentSection, f.key)) : ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
        </div>
        <span class="pref-fs" :class="fieldState(currentSection, f.key) === 'active' ? 'pref-fs-active' : 'pref-fs-pending'">{{ stateLabel(fieldState(currentSection, f.key)) }}</span>
      </div>
      <div v-if="active === 'general'" class="pref-field">
        <label class="pref-field-label">{{ t('framework.preferences.dataDir', '数据目录') }}</label>
        <div class="pref-field-ctl">
          <button class="pref-btn pref-btn-sm" type="button" :disabled="!language.directory" @click="openDataDir()">📁 {{ t('framework.preferences.openDataDir', '打开数据目录') }}</button>
          <div class="pref-field-hint">{{ t('framework.preferences.dataDirHint', '语言包放在此目录的 languages/ 子目录下') }}</div>
        </div>
      </div>
      <div v-if="!autoSaveEnabled" class="pref-section-acts"><button class="pref-btn pref-btn-save" :disabled="saveState[currentSection] === 'saving'" @click="doSave(currentSection)">{{ saveState[currentSection] === 'saving' ? t('framework.preferences.actions.saving', '保存中…') : t('framework.preferences.actions.saveSection', '保存本分类') }}</button><button class="pref-btn pref-btn-reset-all" :disabled="saveState[currentSection] === 'saving'" @click="doReset(currentSection)">{{ t('framework.preferences.actions.resetAll', '重置全部首选项') }}</button></div>
    </div>
  </div>
  <Teleport to="body"><div v-if="confirmDialog" class="pref-confirm-overlay" @click.self="confirmDialog = null"><div class="pref-confirm-box"><div class="pref-confirm-hd">{{ t('framework.preferences.confirmDialog.title', '⚠ 高风险安全设置变更') }}</div><div class="pref-confirm-body"><div v-for="c in confirmDialog.changes" :key="c.field" class="pref-confirm-item"><strong>{{ c.field }}</strong>: {{ c.from }} → {{ c.to }}<br><small>{{ c.reason }}</small></div></div><div class="pref-confirm-ft"><button class="pref-btn pref-btn-save" @click="confirmHighRiskSave()">{{ t('framework.preferences.confirmDialog.confirm', '确认变更') }}</button><button class="pref-btn" @click="confirmDialog = null">{{ t('framework.preferences.confirmDialog.cancel', '取消') }}</button></div></div></div></Teleport>
</template>
<style scoped>
.pref { display: flex; height: 100%; }
.pref-nav { width: 150px; flex-shrink: 0; border-right: 1px solid var(--border-subtle); padding: var(--space-xs) 0; overflow-y: auto; }
.pref-nav-item { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 10px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; font-family: var(--font-ui); font-size: var(--text-small); text-align: left; }
.pref-nav-item:hover { background: var(--bg-hover); }
.pref-nav-item.active { background: var(--bg-selected); color: var(--accent); font-weight: 600; }
.pref-st-saving { font-size: 7px; color: var(--state-warning); }
.pref-st-saved { font-size: 7px; color: var(--state-success); }
.pref-st-err { font-size: 7px; color: var(--state-error); }
.pref-content { flex: 1; padding: var(--space-md); overflow-y: auto; }
.pref-content-hd { display: flex; align-items: center; gap: var(--space-md); margin-bottom: var(--space-md); }
.pref-content-hd h4 { font-size: var(--text-body); font-weight: 600; color: var(--text-primary); }
.pref-content-actions { display: flex; align-items: center; gap: var(--space-sm); }
.pref-status { font-size: var(--text-caption); }
.pref-status-saving { color: var(--state-warning); } .pref-status-saved { color: var(--state-success); } .pref-status-err { color: var(--state-error); }
.pref-err-msg { padding: var(--space-xs) var(--space-sm); background: rgba(208,112,96,0.08); color: var(--state-error); border-radius: var(--radius-sm); margin-bottom: var(--space-sm); font-size: var(--text-small); }
.pref-auto-bar { margin-bottom: var(--space-md); padding: var(--space-xs) var(--space-sm); background: var(--bg-input); border-radius: var(--radius-sm); }
.pref-auto-label { display: flex; align-items: center; gap: var(--space-sm); font-size: var(--text-small); color: var(--text-secondary); cursor: pointer; }
.pref-auto-label input { margin: 0; }
.pref-field { display: flex; align-items: center; gap: var(--space-sm); padding: 2px 0; font-size: var(--text-small); }
.pref-field-label { width: 130px; flex-shrink: 0; color: var(--text-secondary); }
.pref-field-ctl { flex: 1; display: flex; align-items: center; gap: var(--space-xs); }
.pref-input { padding: 2px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); width: 100%; max-width: 240px; }
.pref-input:focus { border-color: var(--accent); outline: none; }
.pref-input-num { max-width: 90px; }
select.pref-input { cursor: pointer; }
.pref-obj-sep { color: var(--text-disabled); font-weight: 600; }
.pref-check-label { display: flex; align-items: center; gap: 4px; cursor: pointer; color: var(--text-primary); }
.pref-check-label input { margin: 0; }
.pref-fs { font-size: 8px; padding: 0 3px; border-radius: 2px; flex-shrink: 0; }
.pref-fs-active { color: var(--state-success); background: rgba(107,154,102,0.12); }
.pref-fs-pending { color: var(--text-disabled); background: rgba(0,0,0,0.04); }
.pref-section-acts { display: flex; gap: var(--space-sm); margin-top: var(--space-lg); padding-top: var(--space-md); border-top: 1px solid var(--border-subtle); }
.pref-btn { padding: 3px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.pref-btn:hover:not(:disabled) { background: var(--bg-hover); }
.pref-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pref-btn-save { border-color: var(--accent); color: var(--accent); }
.pref-btn-save:hover:not(:disabled) { background: var(--accent-light); }
.pref-btn-reset-all { color: var(--state-error); border-color: var(--state-error); margin-left: auto; }
.pref-btn-sm { padding: 2px 8px; font-size: var(--text-caption); }
.pref-btn-rm { padding: 1px 6px; border: 1px solid var(--border-default); background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; border-radius: 2px; }
.pref-btn-rm:hover { color: var(--state-error); background: rgba(208,112,96,0.08); }
.pref-confirm-overlay { position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; }
.pref-confirm-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-lg); min-width: 360px; max-width: 480px; box-shadow: var(--shadow-menu); }
.pref-confirm-hd { padding: 10px 14px; border-bottom: 1px solid var(--border-subtle); font-weight: 600; font-size: var(--text-body); color: var(--state-warning); }
.pref-confirm-body { padding: 12px 14px; font-size: var(--text-small); }
.pref-confirm-item { padding: 4px 0; border-bottom: 1px solid var(--border-subtle); }
.pref-confirm-item small { color: var(--text-disabled); }
.pref-confirm-ft { padding: 10px 14px; border-top: 1px solid var(--border-subtle); display: flex; gap: 8px; justify-content: flex-end; }
.pref-roots-editor { width: 100%; }
.pref-roots-list { margin-bottom: 4px; }
.pref-roots-item { display: flex; align-items: center; gap: 4px; padding: 2px 0; }
.pref-roots-path { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.pref-roots-empty { font-size: var(--text-caption); color: var(--text-disabled); padding: 4px 0; }
.pref-roots-actions { display: flex; gap: 4px; }
.pref-field-hint { font-size: var(--text-caption); color: var(--text-disabled); margin-top: 2px; }
.pref-path-row { display: flex; gap: 2px; width: 100%; }
.pref-path-row .pref-input { flex: 1; }
.pref-btn-pick { padding: 2px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.pref-btn-pick:hover { background: var(--bg-hover); }
.pref-string-list { width: 100%; }
.pref-string-item { display: flex; gap: 4px; align-items: center; padding: 2px 0; }
.pref-string-item .pref-input { flex: 1; }
</style>
