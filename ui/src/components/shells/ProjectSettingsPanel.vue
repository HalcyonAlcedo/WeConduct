<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { fetchProjectSettings, postProjectSettings, postRuntimeDefaults, postOpenPath } from '@/services/api'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useToastStore } from '@/stores/toastStore'
import type { ProjectSettings, ProjectSettingsSnapshot } from '@/types/domains/api'

const workspace = useWorkspaceStore()
const toast = useToastStore()

const active = ref('identity')
const loading = ref(false)
const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')

const settings = reactive<ProjectSettings>({
  project_settings_schema_version: 1,
  project_identity: { name: '' },
  runtime_defaults: { initial_variables: {}, browser_config: { headless: true, slow_mo_ms: 0 }, execution_defaults: { default_timeout_ms: 30000, default_retry_count: 0 } },
  packaging: { default_output_name: '' },
  external_resources: [],
  resource_policy: { embedded_resources: [], external_resource_bindings: [] },
  compile_profile: { source_of_truth: 'saved_project_only', inject_project_runtime_defaults_into_main_flow_start: true },
})

const tags = ref<string[]>([])
const tagInput = ref('')
function addTag() { const t = tagInput.value.trim(); if (t && !tags.value.includes(t)) { tags.value.push(t); tagInput.value = '' } }
function removeTag(idx: number) { tags.value.splice(idx, 1) }

const identityDesc = computed({ get: () => (settings.project_identity as any).description || '', set: (v: string) => { (settings.project_identity as any).description = v } })
const identityVersion = computed({ get: () => (settings.project_identity as any).version || '', set: (v: string) => { (settings.project_identity as any).version = v } })
const identityAuthor = computed({ get: () => (settings.project_identity as any).author || '', set: (v: string) => { (settings.project_identity as any).author = v } })

interface VarEntry { key: string; value: string }
const variables = reactive<VarEntry[]>([])
function syncVars() { const obj: Record<string, unknown> = {}; for (const v of variables) { if (v.key.trim()) { const n = Number(v.value); if (!isNaN(n) && v.value.trim()) obj[v.key.trim()] = n; else if (v.value === 'true') obj[v.key.trim()] = true; else if (v.value === 'false') obj[v.key.trim()] = false; else obj[v.key.trim()] = v.value } } settings.runtime_defaults.initial_variables = obj }
function loadVars() { variables.splice(0, variables.length); for (const [k, v] of Object.entries(settings.runtime_defaults.initial_variables || {})) { variables.push({ key: k, value: typeof v === 'object' ? JSON.stringify(v) : String(v) }) } }
function addVar() { variables.push({ key: '', value: '' }) }
function removeVar(idx: number) { variables.splice(idx, 1); syncVars() }

async function load() { loading.value = true; try { const r = await fetchProjectSettings(); Object.assign(settings, r.project_settings); loadVars(); tags.value = (settings.project_identity as any).tags || []; saveState.value = 'idle' } catch (e: any) { toast.error('加载失败', e?.message) } finally { loading.value = false } }

async function save() { if (isWcrun.value) return; saveState.value = 'saving'; syncVars(); (settings.project_identity as any).tags = [...tags.value]; try { const r = await postProjectSettings({ project_settings: { ...settings } as unknown as Record<string, unknown> }); Object.assign(settings, r.project_settings); loadVars(); tags.value = (settings.project_identity as any).tags || []; saveState.value = 'saved'; await workspace.refreshSnapshot(); setTimeout(() => { if (saveState.value === 'saved') saveState.value = 'idle' }, 2000) } catch (e: any) { saveState.value = 'error'; toast.error('保存失败', e?.message) } }

async function saveRuntimeDefaults() { saveState.value = 'saving'; syncVars(); try { await postRuntimeDefaults({ runtime_defaults: settings.runtime_defaults }); saveState.value = 'saved'; await workspace.refreshSnapshot(); setTimeout(() => { if (saveState.value === 'saved') saveState.value = 'idle' }, 2000) } catch (e: any) { saveState.value = 'error'; toast.error('保存失败', e?.message) } }

const st = computed(() => (workspace.snapshot?.project_settings || {}) as ProjectSettingsSnapshot)
const isWcrun = computed(() => (st.value as any)?.source_of_truth === 'wcrun_package')
const sectionReadonly = computed(() => isWcrun.value && active.value !== 'runtime')
const sourceLabel = computed(() => isWcrun.value ? '📦 .wcrun 包 (只读)' : '📁 项目目录')
const dirtyLabel = computed(() => st.value?.is_dirty ? '● 未保存' : '● 已保存')

async function openProjectDir() { const dir = (st.value as any).project_file_path || (st.value as any).session_dir; if (!dir) { toast.info('', '当前无项目目录路径'); return }; try { const path = dir.includes('.weconduct.json') ? dir.slice(0, Math.max(dir.lastIndexOf('\\'), dir.lastIndexOf('/'))) : dir; const r = await postOpenPath({ path }); if (r.status === 'opened') toast.success('已打开', r.path) } catch (e: any) { if (e?.status === 503) toast.info('', '当前运行环境不支持系统打开目录'); else toast.error('打开失败', e?.message) } }

const NAV = [{ key: 'identity', label: '项目信息' }, { key: 'runtime', label: '运行默认值' }, { key: 'packaging', label: '资源与打包' }, { key: 'compile', label: '编译规则' }, { key: 'status', label: '状态与诊断' }]

onMounted(load)
watch(() => workspace.projectId, (next, prev) => { if (next && next !== prev) load() })
</script>
<template>
  <div class="psp-root">
    <div class="psp-hd">
      <span>项目设置</span><span class="psp-source">{{ sourceLabel }}</span><span :class="st.is_dirty ? 'psp-dirty' : 'psp-clean'">{{ dirtyLabel }}</span>
      <span v-if="saveState === 'saving'" class="psp-st-saving">保存中…</span><span v-else-if="saveState === 'saved'" class="psp-st-saved">已保存</span><span v-else-if="saveState === 'error'" class="psp-st-err">错误</span>
      <button class="psp-open-dir" @click="openProjectDir" :disabled="!st.project_file_path && !st.session_dir" title="打开项目目录">📂 打开目录</button>
    </div>
    <div v-if="isWcrun" class="psp-readonly-banner">📦 .wcrun 包已加载 — 仅运行默认值可编辑，其余为只读</div>
    <div class="psp-body" v-if="!loading">
      <div class="psp-nav"><button v-for="n in NAV" :key="n.key" :class="['psp-nav-item', { active: active === n.key }]" @click="active = n.key">{{ n.label }}</button></div>
      <div class="psp-content">
        <template v-if="active === 'identity'">
          <div class="psp-field"><label>项目 ID</label><code class="psp-ro">{{ workspace.projectId || '—' }}</code></div>
          <div class="psp-field"><label>项目名称</label><input v-model="settings.project_identity.name" class="psp-input" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>描述</label><textarea v-model="identityDesc" class="psp-input psp-textarea" rows="2" placeholder="项目描述" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>版本</label><input v-model="identityVersion" class="psp-input" placeholder="0.1.0" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>作者</label><input v-model="identityAuthor" class="psp-input" placeholder="作者" :disabled="sectionReadonly" /></div>
          <div class="psp-field"><label>标签</label><div class="psp-tags"><span v-for="(t, i) in tags" :key="i" class="psp-tag">{{ t }}<button v-if="!sectionReadonly" class="psp-tag-rm" @click="removeTag(i)">×</button></span><input v-if="!sectionReadonly" v-model="tagInput" class="psp-tag-input" placeholder="新增标签" @keyup.enter="addTag" style="width:80px" /></div></div>
        </template>
        <template v-else-if="active === 'runtime'">
          <h5>初始变量</h5>
          <div v-for="(v, i) in variables" :key="i" class="psp-var-row"><input v-model="v.key" class="psp-input" placeholder="变量名" @change="syncVars()" style="width:120px" /><input v-model="v.value" class="psp-input" placeholder="值" @change="syncVars()" style="flex:1" /><button class="psp-rm" @click="removeVar(i)">✕</button></div>
          <button class="psp-add" @click="addVar">+ 新增变量</button>
          <h5 style="margin-top:14px">浏览器配置</h5>
          <div class="psp-field"><label>headless</label><input type="checkbox" v-model="settings.runtime_defaults.browser_config.headless" /></div>
          <div class="psp-field"><label>slow_mo_ms</label><input type="number" v-model.number="settings.runtime_defaults.browser_config.slow_mo_ms" class="psp-input" style="width:100px" /></div>
          <h5 style="margin-top:14px">执行默认值</h5>
          <div class="psp-field"><label>超时(ms)</label><input type="number" v-model.number="settings.runtime_defaults.execution_defaults.default_timeout_ms" class="psp-input" style="width:100px" /></div>
          <div class="psp-field"><label>重试次数</label><input type="number" v-model.number="settings.runtime_defaults.execution_defaults.default_retry_count" class="psp-input" style="width:80px" /></div>
          <button class="psp-btn-save" @click="saveRuntimeDefaults" :disabled="saveState === 'saving'" style="margin-top:14px">仅保存运行默认值</button>
        </template>
        <template v-else-if="active === 'packaging'">
          <h5>打包设置</h5>
          <div class="psp-field"><label>默认输出名</label><input v-model="settings.packaging.default_output_name" class="psp-input" placeholder="demo.wcrun" :disabled="sectionReadonly" /></div>
          <h5 style="margin-top:14px">External 资源</h5>
          <div v-if="!settings.external_resources.length && !sectionReadonly" class="psp-empty">暂无 external 资源声明</div>
          <div v-for="(er, i) in settings.external_resources" :key="i" class="psp-var-row"><input :value="(er as any).resource_id || (er as any).bind_key || ''" class="psp-input" placeholder="resource_id" style="width:100px" :disabled="sectionReadonly" @change="(er as any).resource_id = ($event.target as HTMLInputElement).value" /><input :value="(er as any).kind || ''" class="psp-input" placeholder="kind" style="width:70px" :disabled="sectionReadonly" @change="(er as any).kind = ($event.target as HTMLInputElement).value" /><input :value="(er as any).description || ''" class="psp-input" placeholder="描述" style="flex:1" :disabled="sectionReadonly" @change="(er as any).description = ($event.target as HTMLInputElement).value" /><button v-if="!sectionReadonly" class="psp-rm" @click="settings.external_resources.splice(i,1)">✕</button></div>
          <button v-if="!sectionReadonly" class="psp-add" @click="settings.external_resources.push({ resource_id: '', kind: 'file', description: '' })">+ 新增 external 资源</button>
          <h5 style="margin-top:14px">Embedded 资源</h5>
          <div v-if="!settings.resource_policy.embedded_resources?.length && !sectionReadonly" class="psp-empty">暂无 embedded 资源</div>
          <div v-for="(p, i) in settings.resource_policy.embedded_resources" :key="i" class="psp-var-row"><input :value="p" class="psp-input" style="flex:1" :disabled="sectionReadonly" @change="settings.resource_policy.embedded_resources[i] = ($event.target as HTMLInputElement).value" /><button v-if="!sectionReadonly" class="psp-rm" @click="settings.resource_policy.embedded_resources.splice(i,1)">✕</button></div>
          <button v-if="!sectionReadonly" class="psp-add" @click="settings.resource_policy.embedded_resources.push('')">+ 新增 embedded 资源</button>
        </template>
        <template v-else-if="active === 'compile'">
          <div class="psp-field"><label>真值来源</label><select v-model="settings.compile_profile.source_of_truth" class="psp-input" :disabled="sectionReadonly"><option value="saved_project_only">saved_project_only</option></select></div>
          <div class="psp-field"><label>注入运行默认值</label><input type="checkbox" v-model="settings.compile_profile.inject_project_runtime_defaults_into_main_flow_start" :disabled="sectionReadonly" /></div>
        </template>
        <template v-else-if="active === 'status'">
          <div class="psp-state-grid">
            <div><span>真值来源</span><code>{{ st.source_of_truth || '—' }}</code></div><div><span>状态来源</span><code>{{ st.state_source || '—' }}</code></div><div><span>Schema 版本</span><code>{{ st.project_settings_schema_version || '—' }}</code></div><div><span>是否 dirty</span><code>{{ st.is_dirty ? '是' : '否' }}</code></div>
            <div v-if="st.project_file_path"><span>项目文件</span><code class="psp-path">{{ st.project_file_path }}</code></div><div v-if="st.project_settings_path"><span>设置文件</span><code class="psp-path">{{ st.project_settings_path }}</code></div><div v-if="st.session_dir"><span>会话目录</span><code class="psp-path">{{ st.session_dir }}</code></div>
            <div><span>External 资源</span><code>{{ st.has_external_resources ? '是' : '否' }}</code></div><div><span>Embedded 资源数</span><code>{{ st.embedded_resource_count ?? '—' }}</code></div><div><span>External 资源数</span><code>{{ st.external_resource_count ?? '—' }}</code></div><div><span>默认输出名</span><code>{{ st.package_default_output_name || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>图数据版本</span><code>{{ st.main_graph_compatibility.graph_data_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>创建时版本</span><code>{{ st.main_graph_compatibility.built_with_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>最低加载版本</span><code>{{ st.main_graph_compatibility.minimum_loader_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>最近升级版本</span><code>{{ st.main_graph_compatibility.last_upgraded_by_app_version || '—' }}</code></div>
            <div v-if="st.main_graph_compatibility"><span>历史无版本图</span><code>{{ st.main_graph_compatibility.is_legacy_unversioned ? '是' : '否' }}</code></div>
          </div>
        </template>
      </div>
    </div>
    <div class="psp-ft"><button class="psp-btn-save" @click="save" :disabled="saveState === 'saving' || isWcrun">{{ isWcrun ? '.wcrun 只读' : '保存全部设置' }}</button></div>
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
</style>
