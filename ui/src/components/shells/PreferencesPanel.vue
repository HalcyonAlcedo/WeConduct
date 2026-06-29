<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { postPreferences, postPreferencesReset, fetchPreferences, postPreferencesPreview, postFileDialog } from '@/services/api'
import type { PreferencesUpdateRequest } from '@/types/domains/api'
import { useToastStore } from '@/stores/toastStore'

const workspace = useWorkspaceStore()
const toast = useToastStore()
const active = ref('general')

interface FieldDef { key: string; label: string; type: 'text' | 'number' | 'bool' | 'select' | 'object' | 'json' | 'directory_list'; options?: string[]; hint?: string }

const FIELD_DEFS: Record<string, FieldDef[]> = {
  general: [
    { key: 'language', label: '语言', type: 'select', options: ['zh-CN', 'en-US', 'ja-JP'] }, { key: 'resource_language', label: '资源语言', type: 'select', options: ['zh-CN', 'en-US'] },
    { key: 'theme', label: '主题', type: 'select', options: ['light', 'dark', 'system'] }, { key: 'default_window_size', label: '默认窗口尺寸', type: 'object', hint: '宽度 × 高度（像素）' },
    { key: 'startup_action', label: '启动行为', type: 'select', options: ['restore_last_workspace'] }, { key: 'default_project_directory', label: '默认项目目录', type: 'text' },
    { key: 'recent_project_limit', label: '最近项目上限', type: 'number' }, { key: 'preferences_auto_save', label: '自动保存', type: 'bool' }, { key: 'check_updates_on_startup', label: '启动时检查更新', type: 'bool' }, { key: 'font_scale', label: '字体缩放', type: 'number' },
  ],
  compile: [
    { key: 'default_source_kind', label: '默认源类型', type: 'select', options: ['graph_workspace'] }, { key: 'diagnostic_level', label: '诊断级别', type: 'select', options: ['error', 'warning', 'info', 'debug'] },
    { key: 'block_on_disabled_components', label: '禁用组件阻断编译', type: 'bool' }, { key: 'allow_degraded_compile', label: '允许降级编译', type: 'bool' },
    { key: 'stop_on_first_error', label: '首个错误即停止', type: 'bool' }, { key: 'emit_runtime_plan', label: '生成运行时计划', type: 'bool' }, { key: 'emit_debug_plan', label: '生成调试计划', type: 'bool' },
  ],
  security: [
    { key: 'confirm_high_risk_actions', label: '确认高风险操作', type: 'bool' }, { key: 'show_security_warnings_in_runtime', label: '运行时显示安全警告', type: 'bool' },
    { key: 'log_security_events', label: '记录安全事件', type: 'bool' },
    { key: 'allow_file_access', label: '允许文件访问', type: 'bool' }, { key: 'file_access_scope', label: '文件访问范围', type: 'select', options: ['restricted', 'custom_roots', 'allow_all'] },
    { key: 'file_access_require_absolute_path', label: '要求绝对路径', type: 'bool' },
    { key: 'file_access_allowed_roots', label: '允许访问目录', type: 'directory_list', hint: '仅在 custom_roots 模式下生效' },
    { key: 'file_access_blocked_roots', label: '禁止访问目录', type: 'directory_list' },
    { key: 'file_access_allowed_extensions', label: '允许文件扩展名', type: 'text', hint: '逗号分隔，如 .txt,.json' },
    { key: 'file_access_blocked_extensions', label: '禁止文件扩展名', type: 'text', hint: '逗号分隔，如 .exe,.bat' },
    { key: 'allow_browser_executor', label: '允许浏览器执行器', type: 'bool' },
    { key: 'allow_browser_screenshots', label: '允许截图', type: 'bool' },
    { key: 'allow_cookie_manipulation', label: '允许 Cookie 操作', type: 'bool' },
    { key: 'allow_browser_storage_manipulation', label: '允许 Storage 操作', type: 'bool' },
    { key: 'allow_browser_uploads', label: '允许上传文件', type: 'bool' },
    { key: 'allow_browser_downloads', label: '允许下载文件', type: 'bool' },
    { key: 'allow_new_browser_windows', label: '允许新窗口', type: 'bool' },
    { key: 'allow_external_programs', label: '允许外部程序', type: 'bool' },
    { key: 'allow_python_execution', label: '允许 Python 执行', type: 'bool' },
    { key: 'allow_local_network_access', label: '允许本地网络', type: 'bool' },
    { key: 'allow_remote_network_access', label: '允许远程网络', type: 'bool' },
    { key: 'allow_js_injection', label: '允许 JS 注入', type: 'bool' },
    { key: 'allow_js_evaluation', label: '允许 JS 执行', type: 'bool' },
  ],
  python: [
    { key: 'python_executable_path', label: 'Python 路径', type: 'text' }, { key: 'timeout_seconds', label: '超时（秒）', type: 'number' },
    { key: 'sandbox_mode', label: '沙盒模式', type: 'select', options: ['restricted'] }, { key: 'capture_stdout_stderr', label: '捕获标准输出/错误', type: 'bool' },
    { key: 'default_python_version_spec', label: '默认 Python 版本', type: 'text' },
    { key: 'default_cache_location_mode', label: '默认缓存位置模式', type: 'select', options: ['software_cache', 'project_cache'] },
    { key: 'default_project_cache_mode', label: '默认项目缓存模式', type: 'select', options: ['full_venv', 'wheelhouse_rebuild'] },
    { key: 'default_requirements_source_mode', label: '默认需求来源模式', type: 'select', options: ['inline', 'requirements_txt', 'lock_file'] },
    { key: 'default_package_embed_mode', label: '默认包嵌入模式', type: 'select', options: ['none', 'wheelhouse_rebuild', 'full_venv'] },
  ],
  nodegraph: [
    { key: 'auto_sync_mode', label: '自动同步模式', type: 'select', options: ['responsive'] }, { key: 'show_node_id_on_node', label: '显示节点 ID', type: 'bool' },
    { key: 'show_disabled_resource_badge', label: '显示禁用资源徽章', type: 'bool' }, { key: 'snap_to_grid', label: '吸附网格', type: 'bool' },
    { key: 'grid_enabled', label: '网格启用', type: 'bool' }, { key: 'auto_open_node_on_drop', label: '拖放后自动打开节点', type: 'bool' },
    { key: 'confirm_delete_node', label: '删除节点确认', type: 'bool' }, { key: 'show_inline_config_summary', label: '显示内联配置摘要', type: 'bool' },
    { key: 'save_conflict_policy', label: '保存冲突策略', type: 'select', options: ['prefer_current_graph', 'strict'] },
  ],
  other: [
    { key: 'workspace_draft_recovery_enabled', label: '工作区草稿恢复', type: 'bool' }, { key: 'workspace_draft_recovery_ttl_minutes', label: '草稿恢复 TTL（分钟）', type: 'number' },
  ],
}

const SECTION_MAP: Record<string, string> = { general: 'program_settings', compile: 'compile_settings', security: 'security_settings', python: 'python_runtime_settings', nodegraph: 'graph_settings', other: 'other_settings' }
const CATS = [{ key: 'general', label: '程序设置' }, { key: 'compile', label: '编译设置' }, { key: 'security', label: '安全设置' }, { key: 'python', label: 'Python 运行时设置' }, { key: 'nodegraph', label: '节点图设置' }, { key: 'other', label: '其他设置' }]

const form = reactive<Record<string, Record<string, any>>>({ program_settings: {}, compile_settings: {}, security_settings: {}, python_runtime_settings: {}, graph_settings: {}, other_settings: {} })
const saveState = reactive<Record<string, 'idle' | 'saving' | 'saved' | 'error'>>({}); const saveError = reactive<Record<string, string>>({})

function normalizeRoots(value: unknown): string[] { if (!Array.isArray(value)) return []; const result: string[] = []; for (const item of value) { if (typeof item !== 'string') continue; const n = item.trim(); if (!n || result.includes(n)) continue; result.push(n) } return result }

function initForm() {
  const prefs = workspace.snapshot?.preferences || {}
  for (const section of Object.values(SECTION_MAP)) {
    const source = (prefs as Record<string, any>)[section] || {}
    const next = { ...source }
    if (section === 'security_settings') { next.file_access_allowed_roots = normalizeRoots(next.file_access_allowed_roots); next.file_access_blocked_roots = normalizeRoots(next.file_access_blocked_roots) }
    form[section] = next; saveState[section] = 'idle'; saveError[section] = ''
  }
}
onMounted(() => initForm()); watch(() => workspace.snapshot?.preferences, () => initForm(), { deep: true })

const prefsState = computed(() => (workspace.snapshot as any)?.graph_workspace?.preferences_state || {})
function fieldState(s: string, k: string): string | undefined { const n = (prefsState.value as any)[s]; if (!n || typeof n !== 'object') return; const v = n[k]; return typeof v === 'string' ? v : undefined }
function stateLabel(s: string | undefined): string { if (s === 'active') return '已接入'; if (s === 'stored_only') return '待接入'; return '—' }

const autoSaveTimers: Record<string, ReturnType<typeof setTimeout>> = {}
const autoSaveEnabled = computed(() => !!form.program_settings?.preferences_auto_save)
const confirmDialog = ref<{ section: string; changes: { field: string; from: unknown; to: unknown; reason: string }[] } | null>(null)

function onFieldChange(section: string) { if (!autoSaveEnabled.value) return; clearTimeout(autoSaveTimers[section]); saveState[section] = 'saving'; autoSaveTimers[section] = setTimeout(() => doSave(section), 400) }

async function doSave(section: string) {
  saveState[section] = 'saving'; saveError[section] = ''
  try {
    const values = flattenForSave(section, form[section])
    if (section === 'security_settings') {
      try { const preview = await postPreferencesPreview({ section, values }); if (preview.confirmation_required && preview.high_risk_changes.length) { confirmDialog.value = { section, changes: preview.high_risk_changes }; saveState[section] = 'idle'; return } } catch {}
    }
    await postPreferences({ section, values } as PreferencesUpdateRequest)
    saveState[section] = 'saved'; setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000)
    try { const r = await fetchPreferences(); if (section === 'security_settings') { form[section] = { ...(r.preferences[section] as any || {}), file_access_allowed_roots: normalizeRoots((r.preferences[section] as any)?.file_access_allowed_roots), file_access_blocked_roots: normalizeRoots((r.preferences[section] as any)?.file_access_blocked_roots) } } else { form[section] = { ...(r.preferences[section] as Record<string, any> || {}) } } } catch {}
    await workspace.refreshSnapshot()
  } catch (e: any) {
    if (e?.body?.error === 'high_risk_confirmation_required') { confirmDialog.value = { section, changes: e.body.high_risk_changes || [] }; saveState[section] = 'idle'; return }
    saveState[section] = 'error'; saveError[section] = e?.message || '保存失败'
  }
}

async function confirmHighRiskSave() {
  if (!confirmDialog.value) return; const { section } = confirmDialog.value; confirmDialog.value = null; saveState[section] = 'saving'
  try { await postPreferences({ section, values: flattenForSave(section, form[section]), confirm_high_risk: true } as PreferencesUpdateRequest); saveState[section] = 'saved'; setTimeout(() => { if (saveState[section] === 'saved') saveState[section] = 'idle' }, 2000); try { const r = await fetchPreferences(); if (section === 'security_settings') { form[section] = { ...(r.preferences[section] as any || {}), file_access_allowed_roots: normalizeRoots((r.preferences[section] as any)?.file_access_allowed_roots), file_access_blocked_roots: normalizeRoots((r.preferences[section] as any)?.file_access_blocked_roots) } } else { form[section] = { ...(r.preferences[section] as Record<string, any> || {}) } } } catch {}; await workspace.refreshSnapshot() } catch (e: any) { saveState[section] = 'error'; saveError[section] = e?.message || '保存失败' }
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

function isRootsFieldVisible(): boolean { return getField('security_settings', 'allow_file_access') && getField('security_settings', 'file_access_scope') === 'custom_roots' }

// Directory list editor (parameterized by field key)
function getDirectoryList(fieldKey: string): string[] { return normalizeRoots(getField('security_settings', fieldKey)) }
function setDirectoryList(fieldKey: string, next: string[]) { setField('security_settings', fieldKey, normalizeRoots(next)) }
function addDirectoryItem(fieldKey: string, path: string) { const n = path.trim(); if (!n) return; const cur = getDirectoryList(fieldKey); if (cur.includes(n)) return; setDirectoryList(fieldKey, [...cur, n]) }
function removeDirectoryItem(fieldKey: string, path: string) { setDirectoryList(fieldKey, getDirectoryList(fieldKey).filter(item => item !== path)) }
async function pickDirectoryItem(fieldKey: string) { try { const r = await postFileDialog({ mode: 'open_folder', title: '选择目录' }); if (r.status === 'selected' && r.paths.length) addDirectoryItem(fieldKey, r.paths[0]) } catch (e: any) { if (e?.status === 503) toast.info('', '当前运行环境不支持系统目录选择器') } }
async function pickPythonPath() { try { const r = await postFileDialog({ mode: 'open_file', title: '选择 Python 可执行文件' }); if (r.status === 'selected' && r.paths.length) setField('python_runtime_settings', 'python_executable_path', r.paths[0]) } catch (e: any) { if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器') } }

// Extension display helper: convert string[] to comma-separated display
function extDisplay(fieldKey: string): string { const v = getField('security_settings', fieldKey); if (Array.isArray(v)) return v.join(', '); return typeof v === 'string' ? v : '' }

async function doReset(section: string) { saveState[section] = 'saving'; saveError[section] = ''; try { await postPreferencesReset(); const r = await fetchPreferences(); for (const sec of Object.values(SECTION_MAP)) { const vals = { ...((r.preferences as Record<string, any>)[sec] || {}) }; if (sec === 'security_settings') vals.file_access_allowed_roots = normalizeRoots(vals.file_access_allowed_roots); form[sec] = vals; saveState[sec] = 'saved'; setTimeout(() => { if (saveState[sec] === 'saved') saveState[sec] = 'idle' }, 2000) }; await workspace.refreshSnapshot() } catch (e: any) { saveState[section] = 'error'; saveError[section] = e?.message || '重置失败' } }

function saveStatusLabel(section: string): string { const s = saveState[section]; if (s === 'saving') return '保存中…'; if (s === 'saved') return '已保存'; if (s === 'error') return '保存失败'; return '' }
function getField(section: string, key: string): any { return form[section]?.[key] }
function setField(section: string, key: string, value: any) { if (form[section]) { form[section][key] = value; onFieldChange(section) } }
function toggleBool(section: string, key: string) { setField(section, key, !getField(section, key)) }
const currentSection = computed(() => SECTION_MAP[active.value] || 'program_settings')
const currentFields = computed(() => FIELD_DEFS[active.value] || [])
</script>
<template>
  <div class="pref">
    <div class="pref-nav"><button v-for="c in CATS" :key="c.key" :class="['pref-nav-item', { active: active === c.key }]" @click="active = c.key">{{ c.label }}<span v-if="saveState[SECTION_MAP[c.key]] === 'saving'" class="pref-st-saving">保存中</span><span v-else-if="saveState[SECTION_MAP[c.key]] === 'saved'" class="pref-st-saved">已保存</span><span v-else-if="saveState[SECTION_MAP[c.key]] === 'error'" class="pref-st-err">错误</span></button></div>
    <div class="pref-content">
      <div class="pref-content-hd"><h4>{{ CATS.find(c => c.key === active)?.label }}</h4><div class="pref-content-actions"><span class="pref-status" :class="{'pref-status-saving':saveState[currentSection]==='saving','pref-status-saved':saveState[currentSection]==='saved','pref-status-err':saveState[currentSection]==='error'}">{{ saveStatusLabel(currentSection) }}</span></div></div>
      <div v-if="saveState[currentSection] === 'error'" class="pref-err-msg">{{ saveError[currentSection] }}</div>
      <div class="pref-auto-bar"><label class="pref-auto-label"><input type="checkbox" :checked="autoSaveEnabled" @change="toggleBool('program_settings', 'preferences_auto_save')" />自动保存（修改字段后自动提交）</label></div>
      <div v-for="f in currentFields" :key="f.key" class="pref-field" v-show="f.key !== 'file_access_allowed_roots' || isRootsFieldVisible()">
        <label class="pref-field-label">{{ f.label }}</label><div class="pref-field-ctl">
          <template v-if="f.type === 'bool'"><label class="pref-check-label"><input type="checkbox" :checked="!!getField(currentSection, f.key)" @change="toggleBool(currentSection, f.key)" />{{ getField(currentSection, f.key) ? '是' : '否' }}</label></template>
          <input v-else-if="f.type === 'number'" type="number" class="pref-input pref-input-num" :value="getField(currentSection, f.key) ?? ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).valueAsNumber)" />
          <select v-else-if="f.type === 'select'" class="pref-input" :value="getField(currentSection, f.key) || f.options?.[0] || ''" @change="setField(currentSection, f.key, ($event.target as HTMLSelectElement).value)"><option v-for="o in f.options" :key="o" :value="o">{{ o }}</option></select>
          <template v-else-if="f.type === 'object' && f.key === 'default_window_size'"><input type="number" class="pref-input pref-input-num" placeholder="宽度" :value="(getField(currentSection, 'default_window_size') || {}).width ?? ''" @input="(e: Event) => { const ws = { ...(form[currentSection]?.default_window_size || {}), width: (e.target as HTMLInputElement).valueAsNumber }; setField(currentSection, 'default_window_size', ws) }" /><span class="pref-obj-sep">×</span><input type="number" class="pref-input pref-input-num" placeholder="高度" :value="(getField(currentSection, 'default_window_size') || {}).height ?? ''" @input="(e: Event) => { const ws = { ...(form[currentSection]?.default_window_size || {}), height: (e.target as HTMLInputElement).valueAsNumber }; setField(currentSection, 'default_window_size', ws) }" /></template>
          <!-- Directory list editor -->
          <div v-else-if="f.type === 'directory_list'" class="pref-roots-editor">
            <div class="pref-roots-list" v-if="getDirectoryList(f.key).length"><div v-for="root in getDirectoryList(f.key)" :key="root" class="pref-roots-item"><span class="pref-roots-path">{{ root }}</span><button class="pref-btn pref-btn-rm" type="button" @click="removeDirectoryItem(f.key, root)">✕</button></div></div>
            <div v-else class="pref-roots-empty">未配置目录</div>
            <div class="pref-roots-actions"><button class="pref-btn pref-btn-sm" type="button" @click="pickDirectoryItem(f.key)">📁 选择目录</button></div>
            <div v-if="f.hint" class="pref-field-hint">{{ f.hint }}</div>
          </div>
          <!-- Path picker for python_executable_path -->
          <div v-else-if="f.key === 'python_executable_path'" class="pref-path-row">
            <input type="text" class="pref-input" :value="getField(currentSection, f.key) ?? ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
            <button class="pref-btn pref-btn-pick" type="button" @click="pickPythonPath">…</button>
          </div>
          <!-- Extension fields (display string[] as comma-separated) -->
          <input v-else-if="f.key.includes('extensions')" type="text" class="pref-input" :value="extDisplay(f.key)" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
          <!-- Text -->
          <input v-else type="text" class="pref-input" :value="typeof getField(currentSection, f.key) === 'string' ? getField(currentSection, f.key) : typeof getField(currentSection, f.key) === 'number' ? String(getField(currentSection, f.key)) : ''" @input="setField(currentSection, f.key, ($event.target as HTMLInputElement).value)" />
        </div>
        <span class="pref-fs" :class="fieldState(currentSection, f.key) === 'active' ? 'pref-fs-active' : 'pref-fs-pending'">{{ stateLabel(fieldState(currentSection, f.key)) }}</span>
      </div>
      <div v-if="!autoSaveEnabled" class="pref-section-acts"><button class="pref-btn pref-btn-save" :disabled="saveState[currentSection] === 'saving'" @click="doSave(currentSection)">{{ saveState[currentSection] === 'saving' ? '保存中…' : '保存本分类' }}</button><button class="pref-btn pref-btn-reset-all" :disabled="saveState[currentSection] === 'saving'" @click="doReset(currentSection)">重置全部首选项</button></div>
    </div>
  </div>
  <Teleport to="body"><div v-if="confirmDialog" class="pref-confirm-overlay" @click.self="confirmDialog = null"><div class="pref-confirm-box"><div class="pref-confirm-hd">⚠ 高风险安全设置变更</div><div class="pref-confirm-body"><div v-for="c in confirmDialog.changes" :key="c.field" class="pref-confirm-item"><strong>{{ c.field }}</strong>: {{ c.from }} → {{ c.to }}<br><small>{{ c.reason }}</small></div></div><div class="pref-confirm-ft"><button class="pref-btn pref-btn-save" @click="confirmHighRiskSave()">确认变更</button><button class="pref-btn" @click="confirmDialog = null">取消</button></div></div></div></Teleport>
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
</style>
