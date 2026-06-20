<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGraphStore } from '@/stores/graphStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useCompilationStore } from '@/stores/compilationStore'
import { useResourceStore } from '@/stores/resourceStore'
import PlaceholderBanner from '@/components/common/PlaceholderBanner.vue'
import MonacoEditor from '@/components/input/MonacoEditor.vue'
import { postFileDialog, postGraphNormalize } from '@/services/api'
import { useToastStore } from '@/stores/toastStore'

const graphStore = useGraphStore()
const workspace = useGraphWorkspaceStore()
const compilation = useCompilationStore()
const resourceStore = useResourceStore()
const toast = useToastStore()

const nodeSearch = ref('')
const showNodeSearch = ref(false)

const matchingNodes = computed(() => {
  const q = nodeSearch.value.trim().toLowerCase()
  if (!q) return []
  const gm = workspace.graphModel
  if (!gm) return []
  return gm.nodes.filter(n =>
    n.node_id.toLowerCase().includes(q) ||
    (n.display_name || '').toLowerCase().includes(q) ||
    (n.node_kind || '').toLowerCase().includes(q)
  ).slice(0, 10)
})

function selectSearchedNode(nodeId: string) {
  graphStore.selectNode(nodeId)
  nodeSearch.value = ''
  showNodeSearch.value = false
}

const targetSubgraph = computed(() => {
  if (selectedNode.value?.node_kind !== 'graph.call_subgraph') return null
  const subId = selectedNode.value?.node_config?.subgraph_id
  if (!subId) return null
  return resourceStore.resources.find(r => r.resource_id === subId || r.resource_key === subId)
})

function schemaFields(schema: Record<string, any> | undefined): { key: string; type: string; required: boolean }[] {
  if (!schema) return []
  return Object.entries(schema).map(([k, v]) => ({
    key: k, type: (v as any)?.type || 'string', required: !!(v as any)?.required,
  }))
}

const selected = computed(() => graphStore.selectGraphModel({
  workspaceModel: workspace.graphModel,
  compilationModel: compilation.outcome?.graph_model,
}))
const selectedNodeId = computed(() => graphStore.selectedNode)
const selectedNode = computed(() => selected.value.model?.nodes.find(n => n.node_id === selectedNodeId.value))

function kindLabel(k: string) {
  switch (k) { case 'execution': return '执行'; case 'control': return '控制'; case 'observe': return '观察'; case 'bridge': return '桥接'; default: return k }
}

// ---- Field templates ----
interface ParamField { key: string; type: 'string' | 'number' | 'boolean' | 'json' | 'object-map' | 'typed-value' | 'branch-list' | 'code'; options?: string[] }
const PARAM_TEMPLATES: Record<string, ParamField[]> = {
  'data.get_text':          [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }, { key: 'target_type', type: 'string', options: ['string', 'int', 'float', 'bool', 'json'] }],
  'data.get_attribute':     [{ key: 'selector', type: 'string' }, { key: 'attribute', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.get_value':         [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.get_element_count': [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'data.set_variables_batch': [{ key: 'variables', type: 'object-map' }],
  'data.set_variable':       [{ key: 'name', type: 'string' }, { key: 'value', type: 'typed-value' }],
  'data.convert_value':      [{ key: 'source_value', type: 'typed-value' }, { key: 'target_type', type: 'string', options: ['string', 'int', 'float', 'bool', 'json'] }, { key: 'variable_name', type: 'string' }, { key: 'in_place', type: 'boolean' }, { key: 'source_variable_name', type: 'string' }],
  'data.increment_variable': [{ key: 'variable_name', type: 'string' }, { key: 'step', type: 'number' }],
  'data.decrement_variable': [{ key: 'variable_name', type: 'string' }, { key: 'step', type: 'number' }],
  'data.list_index':         [{ key: 'variable_name', type: 'string' }, { key: 'value', type: 'typed-value' }, { key: 'output_variable_name', type: 'string' }],
  'browser.inject_js':       [{ key: 'script', type: 'code' }],
  'browser.run_js':          [{ key: 'script', type: 'code' }, { key: 'variable_name', type: 'string' }],
  'browser.extract_web_table': [{ key: 'selector', type: 'string' }, { key: 'variable_name', type: 'string' }],
  'browser.extract_web_table_to_excel': [{ key: 'selector', type: 'string' }, { key: 'path', type: 'string' }, { key: 'sheet_name', type: 'string' }],
  'session.apply_auth_session': [{ key: 'cookies', type: 'json' }, { key: 'local_storage', type: 'object-map' }],
  'dialog.switch_dialog_mode': [{ key: 'mode', type: 'string' }],
  'dialog.watch_dialogs':      [{ key: 'timeout', type: 'number' }, { key: 'variable_name', type: 'string' }],
  'dialog.handle_dialogs':     [{ key: 'clear_after', type: 'boolean' }],
  'dialog.set_agent_config':   [{ key: 'default_action', type: 'string' }, { key: 'prompt_text', type: 'string' }],
  'graph.call_subgraph':       [{ key: 'subgraph_id', type: 'string' }, { key: 'inputs', type: 'object-map' }, { key: 'outputs', type: 'object-map' }],
  'flow.start':                [{ key: 'initial_variables', type: 'object-map' }],
  'control.parallel_fork':     [{ key: 'branches', type: 'branch-list' }],
  'control.join':              [{ key: 'branches', type: 'branch-list' }],
}

const OBJECT_MAP_KEYS = new Set(['initial_variables', 'variables', 'inputs', 'outputs', 'local_storage'])

// ---- Typed-value helpers ----
type ValueType = 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null'
const VALUE_TYPES: ValueType[] = ['string', 'number', 'boolean', 'object', 'array', 'null']

function detectValueType(v: unknown): ValueType {
  if (v === null || v === undefined) return 'null'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'object') return 'object'
  if (typeof v === 'boolean') return 'boolean'
  if (typeof v === 'number') return 'number'
  return 'string'
}

function convertValue(v: unknown, fromType: ValueType, toType: ValueType): unknown {
  if (fromType === toType) return v
  switch (toType) {
    case 'string': return v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v)
    case 'number': { const n = Number(v); return isNaN(n) ? 0 : n }
    case 'boolean': return typeof v === 'string' ? v === 'true' : !!v
    case 'object': return (v !== null && typeof v === 'object' && !Array.isArray(v)) ? v : {}
    case 'array': return Array.isArray(v) ? v : []
    case 'null': return null
  }
}

function setTypedVal(key: string, val: unknown) {
  // write through setCfgVal — preserves type
  setCfgVal(key, val)
}

function setTypedJsonVal(key: string, raw: string) {
  try {
    const val = JSON.parse(raw)
    setCfgVal(key, val)
  } catch { /* invalid JSON */ }
}

// Track selected type per field (keyed by field path, initialized from actual value)
const typedValSelections = ref<Record<string, ValueType>>({})
watch(() => selectedNode.value, () => { typedValSelections.value = {} })
function getSelectedType(fieldKey: string): ValueType {
  if (!(fieldKey in typedValSelections.value)) {
    typedValSelections.value[fieldKey] = detectValueType(getCfgVal(fieldKey))
  }
  return typedValSelections.value[fieldKey]
}
function changeValueType(fieldKey: string, newType: ValueType) {
  const oldType = getSelectedType(fieldKey)
  const oldVal = getCfgVal(fieldKey)
  const newVal = convertValue(oldVal, oldType, newType)
  typedValSelections.value[fieldKey] = newType
  setCfgVal(fieldKey, newVal)
}

// ---- Computed fields ----
const paramFields = computed(() => {
  const nk = selectedNode.value?.node_kind
  return nk ? (PARAM_TEMPLATES[nk] || []) : []
})

const objectMapFields = computed(() => {
  const result: { key: string; section?: string }[] = []
  const cfg = selectedNode.value?.node_config || {}
  for (const f of paramFields.value) {
    if (f.type === 'object-map') result.push({ key: f.key })
  }
  const templateKeys = new Set(paramFields.value.map(f => f.key))
  for (const [k, v] of Object.entries(cfg)) {
    if (templateKeys.has(k)) continue
    if (OBJECT_MAP_KEYS.has(k) && v !== null && typeof v === 'object' && !Array.isArray(v)) {
      result.push({ key: k })
    }
  }
  return result
})

const objectMapTemplateKeys = computed(() => new Set(objectMapFields.value.map(f => f.key)))

const extraConfigSections = computed(() => {
  const cfg = selectedNode.value?.node_config || {}
  const templateKeys = new Set(paramFields.value.map(f => f.key))
  const sections: { section?: string; rows: { key: string; path: string; type: string; value: unknown }[] }[] = []
  for (const [k, v] of Object.entries(cfg)) {
    if (templateKeys.has(k)) continue
    if (objectMapTemplateKeys.value.has(k)) continue
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      const rows: { key: string; path: string; type: string; value: unknown }[] = []
      for (const [sk, sv] of Object.entries(v as Record<string, unknown>)) {
        rows.push({ key: sk, path: `${k}.${sk}`, type: guessType(sv), value: sv })
      }
      sections.push({ section: k, rows })
    } else {
      sections.push({ rows: [{ key: k, path: k, type: guessType(v), value: v }] })
    }
  }
  return sections
})
function guessType(v: unknown): string {
  if (typeof v === 'string') return 'string'; if (typeof v === 'number') return 'number'; if (typeof v === 'boolean') return 'boolean'; return 'json'
}

function isFieldBound(key: string): { nodeName: string; portId: string } | null {
  const gm = workspace.graphModel; if (!gm || !selectedNode.value) return null
  const targetNode = gm.nodes.find(n => n.node_id === selectedNode.value!.node_id)
  const edge = gm.edges.find(e => {
    if (e.to_node_id !== selectedNode.value!.node_id || e.relation_layer !== 'data') return false
    if (e.to_port_id === key || e.to_port_id?.endsWith('.' + key)) return true
    const port = targetNode?.ports?.find(p => p.port_id === e.to_port_id)
    if (port && (port.semantic_slot === key || port.semantic_slot?.endsWith('.' + key) || key.endsWith('.' + (port.semantic_slot || '')))) return true
    return false
  })
  if (!edge) return null
  const srcNode = gm.nodes.find(n => n.node_id === edge.from_node_id)
  return { nodeName: srcNode?.display_name || edge.from_node_id, portId: edge.from_port_id || edge.to_port_id || 'out' }
}

function getCfgVal(key: string): unknown {
  const cfg = selectedNode.value?.node_config || {}
  if (key.includes('.')) { const [p, s] = key.split('.'); return (cfg[p] as any)?.[s] ?? '' }
  return key in cfg ? cfg[key] : ''
}

function setCfgVal(key: string, val: unknown) {
  if (!selectedNode.value) return
  const cfg = JSON.parse(JSON.stringify(selectedNode.value.node_config || {}))
  if (key.includes('.')) { const [p, s] = key.split('.'); if (!cfg[p] || typeof cfg[p] !== 'object') cfg[p] = {}; cfg[p][s] = val }
  else cfg[key] = val
  workspace.updateNode(selectedNode.value.node_id, { node_config: cfg })
}

function setJsonVal(key: string, raw: string) {
  if (!selectedNode.value) return
  try {
    const val = JSON.parse(raw)
    const cfg = JSON.parse(JSON.stringify(selectedNode.value.node_config || {}))
    if (key.includes('.')) {
      const [p, s] = key.split('.')
      if (!cfg[p] || typeof cfg[p] !== 'object') cfg[p] = {}
      ;(cfg[p] as Record<string, unknown>)[s] = val
    } else {
      cfg[key] = val
    }
    workspace.updateNode(selectedNode.value.node_id, { node_config: cfg })
  } catch { /* invalid JSON */ }
}

// ---- Object-map field operations ----
function getObjectMap(fieldKey: string): Record<string, unknown> {
  const v = getCfgVal(fieldKey)
  if (v !== null && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
  return {}
}

function objectMapEntries(fieldKey: string): { key: string; value: unknown; type: string }[] {
  return Object.entries(getObjectMap(fieldKey)).map(([k, v]) => ({ key: k, value: v, type: guessType(v) }))
}

function addObjectMapKey(fieldKey: string) {
  const map = JSON.parse(JSON.stringify(getObjectMap(fieldKey)))
  let newKey = 'new_key'
  let i = 1
  while (newKey in map) newKey = `new_key_${i++}`
  map[newKey] = ''
  setCfgVal(fieldKey, map)
}

function deleteObjectMapKey(fieldKey: string, subKey: string) {
  const map = JSON.parse(JSON.stringify(getObjectMap(fieldKey)))
  delete map[subKey]
  setCfgVal(fieldKey, map)
}

function renameObjectMapKey(fieldKey: string, oldKey: string, newKeyRaw: string) {
  const newKey = newKeyRaw.trim()
  if (!newKey || newKey === oldKey) return
  const map = JSON.parse(JSON.stringify(getObjectMap(fieldKey)))
  if (newKey in map && newKey !== oldKey) return
  map[newKey] = map[oldKey]
  delete map[oldKey]
  setCfgVal(fieldKey, map)
}

function setObjectMapValue(fieldKey: string, subKey: string, val: unknown) {
  setCfgVal(`${fieldKey}.${subKey}`, val)
}

const renamingEntry = ref<{ fieldKey: string; subKey: string; tempName: string } | null>(null)
function startRename(fieldKey: string, subKey: string) {
  renamingEntry.value = { fieldKey, subKey, tempName: subKey }
}
function finishRename() {
  if (renamingEntry.value) {
    renameObjectMapKey(renamingEntry.value.fieldKey, renamingEntry.value.subKey, renamingEntry.value.tempName)
    renamingEntry.value = null
  }
}
function cancelRename() { renamingEntry.value = null }

function locateSelectedNode() {
  if (selectedNodeId.value) {
    try { (window as any).__panToNode?.(selectedNodeId.value) } catch {}
  }
}

// ---- Branch-list editor ----
interface BranchItem { key: string; label: string }
function getBranches(fieldKey: string): BranchItem[] {
  const v = getCfgVal(fieldKey)
  if (Array.isArray(v)) return v.filter((b: any) => b && typeof b === 'object').map((b: any) => ({ key: String(b.key || ''), label: String(b.label || '') }))
  return []
}

function setBranches(fieldKey: string, branches: BranchItem[]) {
  setCfgVal(fieldKey, branches)
}

function addBranch(fieldKey: string) {
  const branches = JSON.parse(JSON.stringify(getBranches(fieldKey)))
  let n = branches.length + 1
  while (branches.some((b: BranchItem) => b.key === `branch_${n}`)) n++
  branches.push({ key: `branch_${n}`, label: `分支 ${n}` })
  setBranches(fieldKey, branches)
}

function deleteBranch(fieldKey: string, idx: number) {
  const branches = JSON.parse(JSON.stringify(getBranches(fieldKey)))
  if (branches.length <= 2) { toast.info('', '至少保留 2 个分支'); return }
  branches.splice(idx, 1)
  setBranches(fieldKey, branches)
}

function updateBranchKey(fieldKey: string, idx: number, newKey: string) {
  const trimmed = newKey.trim()
  if (!trimmed) return
  const branches = JSON.parse(JSON.stringify(getBranches(fieldKey)))
  if (branches.some((b: BranchItem, i: number) => i !== idx && b.key === trimmed)) return // duplicate
  branches[idx].key = trimmed
  setBranches(fieldKey, branches)
}

function updateBranchLabel(fieldKey: string, idx: number, newLabel: string) {
  const branches = JSON.parse(JSON.stringify(getBranches(fieldKey)))
  branches[idx].label = newLabel
  setBranches(fieldKey, branches)
}

const normalizing = ref(false)
async function normalizeGraph() {
  if (!workspace.graphModel) return
  normalizing.value = true
  try {
    const r = await postGraphNormalize(workspace.graphModel as unknown as Record<string, unknown>)
    if (r.graph_model) {
      workspace.graphModel = r.graph_model as any
      workspace.changeRevision++
      toast.info('', '端口已同步更新')
    }
  } catch (e: any) { toast.error('规范化失败', e?.message) }
  finally { normalizing.value = false }
}

// ---- Path parameter editor ----
function getParamSchema(fieldKey: string) {
  const nk = selectedNode.value?.node_kind
  if (!nk) return undefined
  return workspace.parameterSchemas[nk]?.[fieldKey]
}

async function pickPathForField(fieldKey: string) {
  const schema = getParamSchema(fieldKey)
  if (!schema) return
  const mode = schema.path_kind === 'save_file' ? 'save_file'
    : schema.path_kind === 'open_directory' ? 'open_folder'
    : 'open_file'
  try {
    const r = await postFileDialog({ mode, title: schema.label || `选择 ${fieldKey}` })
    if (r.status === 'selected' && r.paths.length) {
      setCfgVal(fieldKey, r.paths[0])
    }
  } catch (e: any) {
    if (e?.status === 503) toast.info('', '当前运行环境不支持系统文件选择器')
  }
}
</script>
<template>
  <div class="mep">
    <div class="mep-search-row">
      <input v-model="nodeSearch" class="mep-search" placeholder="搜索节点…" @focus="showNodeSearch = true" @blur="showNodeSearch = false" />
      <div v-if="showNodeSearch && matchingNodes.length" class="mep-search-drop">
        <div v-for="n in matchingNodes" :key="n.node_id" class="mep-search-item" @mousedown.prevent="selectSearchedNode(n.node_id)">
          <span class="mep-search-name">{{ n.display_name || n.node_id }}</span>
          <span class="mep-search-kid">{{ n.node_id }}</span>
        </div>
      </div>
    </div>

    <template v-if="!selectedNode">
      <PlaceholderBanner type="empty" title="未选中节点" description="在节点图或节点列表中点击节点以查看属性" />
    </template>
    <template v-else>
      <div style="display:flex;align-items:center;gap:var(--space-sm);margin-bottom:var(--space-md)">
        <h4 class="mep-title" style="margin-bottom:0">{{ selectedNode.node_id }}</h4>
        <button class="mep-locate-btn" @click="locateSelectedNode" title="在节点图中定位此节点">📍 定位</button>
      </div>
      <div class="mep-grid">
        <div class="mep-row"><label>节点 ID</label><code>{{ selectedNode.node_id }}</code><span class="mep-hint">只读</span></div>
        <div class="mep-row"><label>类型</label><span>{{ kindLabel(selectedNode.lowered_kind) }}</span></div>
        <div class="mep-row"><label>显示名</label>
          <input class="mep-input" :value="selectedNode.display_name ?? ''" @change="workspace.updateNode(selectedNode.node_id, { display_name: ($event.target as HTMLInputElement).value })" placeholder="输入显示名" />
        </div>
        <div class="mep-row"><label>来源锚点</label><code>{{ selectedNode.source_anchor_ref }}</code></div>
        <div class="mep-row"><label>扩展角色</label><span>{{ selectedNode.expansion_role }}</span></div>
      </div>

      <div v-if="selectedNode.node_kind === 'graph.call_subgraph'" class="mep-section">
        <h5>目标子图 Schema</h5>
        <div v-if="!targetSubgraph" class="mep-empty-cfg">未找到目标子图资源 — 检查 subgraph_id</div>
        <template v-else>
          <div class="mep-schema-block">
            <h6>输入 Schema {{ targetSubgraph.input_schema && !Object.keys(targetSubgraph.input_schema).length ? '(未声明)' : '' }}</h6>
            <div v-if="targetSubgraph.input_schema && Object.keys(targetSubgraph.input_schema).length">
              <div v-for="f in schemaFields(targetSubgraph.input_schema)" :key="f.key" class="mep-schema-row">
                <span class="mep-schema-key">{{ f.key }}</span>
                <span class="mep-schema-type">{{ f.type }}</span>
                <span v-if="f.required" class="mep-schema-req">必填</span>
              </div>
            </div>
            <div v-else class="mep-empty-cfg">未声明 schema</div>
          </div>
          <div class="mep-schema-block">
            <h6>输出 Schema {{ targetSubgraph.output_schema && !Object.keys(targetSubgraph.output_schema).length ? '(未声明)' : '' }}</h6>
            <div v-if="targetSubgraph.output_schema && Object.keys(targetSubgraph.output_schema).length">
              <div v-for="f in schemaFields(targetSubgraph.output_schema)" :key="f.key" class="mep-schema-row">
                <span class="mep-schema-key">{{ f.key }}</span>
                <span class="mep-schema-type">{{ f.type }}</span>
              </div>
            </div>
            <div v-else class="mep-empty-cfg">未声明 schema</div>
          </div>
        </template>
      </div>

      <div class="mep-section">
        <h5>节点配置 (node_config)</h5>
        <div class="mep-config">
          <!-- Template fields (non-object-map, non-typed-value) -->
          <div v-for="f in paramFields.filter(p => p.type !== 'object-map' && p.type !== 'typed-value' && p.type !== 'branch-list' && p.type !== 'code')" :key="f.key" class="mep-cfg-row">
            <label :title="f.key">{{ f.key }}</label>
            <span v-if="isFieldBound(f.key)" class="mep-bound">{{ getCfgVal(f.key) }} <em>⇠ {{ isFieldBound(f.key)!.nodeName }}:{{ isFieldBound(f.key)!.portId }}</em></span>
            <template v-else>
              <select v-if="f.options" class="mep-cfg-input" :value="String(getCfgVal(f.key) ?? f.options[0])" @change="setCfgVal(f.key, ($event.target as HTMLSelectElement).value)">
                <option v-for="o in f.options" :key="o" :value="o">{{ o }}</option>
              </select>
              <span v-else-if="f.type === 'string'" style="display:flex;gap:2px;flex:1">
                <input class="mep-cfg-input" :value="String(getCfgVal(f.key) ?? '')" @change="setCfgVal(f.key, ($event.target as HTMLInputElement).value)" />
                <button v-if="getParamSchema(f.key)?.editor_kind === 'path'" class="mep-path-btn" @click="pickPathForField(f.key)" title="选择路径">…</button>
              </span>
              <input v-else-if="f.type === 'number'" class="mep-cfg-input" type="number" :value="Number(getCfgVal(f.key)) || 0" @change="setCfgVal(f.key, Number(($event.target as HTMLInputElement).value) || 0)" />
              <input v-else-if="f.type === 'boolean'" type="checkbox" :checked="!!getCfgVal(f.key)" @change="setCfgVal(f.key, ($event.target as HTMLInputElement).checked)" />
              <textarea v-else class="mep-cfg-textarea" :value="typeof getCfgVal(f.key) === 'object' ? JSON.stringify(getCfgVal(f.key), null, 2) : String(getCfgVal(f.key) ?? '')" @change="setJsonVal(f.key, ($event.target as HTMLTextAreaElement).value)" rows="3" />
            </template>
          </div>

          <!-- Typed-value fields -->
          <div v-for="f in paramFields.filter(p => p.type === 'typed-value')" :key="f.key" class="mep-cfg-row">
            <label :title="f.key">{{ f.key }}</label>
            <template v-if="isFieldBound(f.key)">
              <span class="mep-bound">{{ typeof getCfgVal(f.key) === 'object' ? JSON.stringify(getCfgVal(f.key)) : getCfgVal(f.key) }} <em>⇠ {{ isFieldBound(f.key)!.nodeName }}:{{ isFieldBound(f.key)!.portId }}</em></span>
            </template>
            <template v-else>
              <select class="mep-type-sel" :value="getSelectedType(f.key)" @change="changeValueType(f.key, ($event.target as HTMLSelectElement).value as ValueType)">
                <option v-for="t in VALUE_TYPES" :key="t" :value="t">{{ t }}</option>
              </select>
              <!-- string / number -->
              <input v-if="getSelectedType(f.key) === 'string'" class="mep-cfg-input" :value="String(getCfgVal(f.key) ?? '')" @change="setTypedVal(f.key, ($event.target as HTMLInputElement).value)" />
              <input v-else-if="getSelectedType(f.key) === 'number'" class="mep-cfg-input" type="number" :value="Number(getCfgVal(f.key)) || 0" @change="setTypedVal(f.key, Number(($event.target as HTMLInputElement).value) || 0)" />
              <!-- boolean -->
              <label v-else-if="getSelectedType(f.key) === 'boolean'" class="mep-check-label">
                <input type="checkbox" :checked="!!getCfgVal(f.key)" @change="setTypedVal(f.key, ($event.target as HTMLInputElement).checked)" />
                {{ getCfgVal(f.key) ? 'true' : 'false' }}
              </label>
              <!-- object / array → JSON textarea -->
              <textarea v-else-if="getSelectedType(f.key) === 'object' || getSelectedType(f.key) === 'array'" class="mep-cfg-textarea" :value="JSON.stringify(getCfgVal(f.key), null, 2)" @change="setTypedJsonVal(f.key, ($event.target as HTMLTextAreaElement).value)" rows="3" />
              <!-- null -->
              <span v-else class="mep-null">null</span>
            </template>
          </div>

          <!-- Code fields -->
          <div v-for="f in paramFields.filter(p => p.type === 'code')" :key="f.key" class="mep-code-row">
            <label class="mep-code-label">{{ f.key }}</label>
            <div class="mep-code-editor">
              <MonacoEditor
                :model-value="String(getCfgVal(f.key) ?? '')"
                :language="'javascript'"
                @update:model-value="setCfgVal(f.key, $event)"
              />
            </div>
          </div>

          <!-- Branch-list fields -->
          <template v-for="f in paramFields.filter(p => p.type === 'branch-list')" :key="f.key">
            <div class="mep-cfg-section">{{ f.key }}</div>
            <div v-for="(b, bi) in getBranches(f.key)" :key="bi" class="mep-br-row">
              <input class="mep-br-key" :value="b.key" @change="updateBranchKey(f.key, bi, ($event.target as HTMLInputElement).value)" placeholder="key" />
              <input class="mep-br-label" :value="b.label" @change="updateBranchLabel(f.key, bi, ($event.target as HTMLInputElement).value)" placeholder="label" />
              <button class="mep-om-del" @click="deleteBranch(f.key, bi)" :title="getBranches(f.key).length <= 2 ? '至少保留 2 个分支' : '删除分支'">✕</button>
            </div>
            <button class="mep-om-add" @click="addBranch(f.key)">+ 新增分支</button>
            <button class="mep-br-norm" :disabled="normalizing" @click="normalizeGraph()">{{ normalizing ? '同步中…' : '🔄 同步端口' }}</button>
          </template>

          <!-- Object-map fields -->
          <template v-for="omf in objectMapFields" :key="omf.key">
            <div class="mep-cfg-section">{{ omf.key }}</div>
            <div v-for="entry in objectMapEntries(omf.key)" :key="entry.key" class="mep-om-row">
              <template v-if="renamingEntry?.fieldKey === omf.key && renamingEntry?.subKey === entry.key">
                <input class="mep-om-key-input" :value="renamingEntry.tempName" @input="renamingEntry!.tempName = ($event.target as HTMLInputElement).value" @keyup.enter="finishRename()" @keyup.escape="cancelRename()" @blur="finishRename()" />
              </template>
              <span v-else class="mep-om-key" @dblclick="startRename(omf.key, entry.key)" :title="'双击重命名'">{{ entry.key }}</span>
              <template v-if="isFieldBound(`${omf.key}.${entry.key}`)">
                <span class="mep-bound">{{ typeof entry.value === 'object' ? JSON.stringify(entry.value) : entry.value }} <em>⇠ {{ isFieldBound(`${omf.key}.${entry.key}`)!.nodeName }}</em></span>
              </template>
              <template v-else>
                <input v-if="entry.type === 'string'" class="mep-cfg-input" :value="String(entry.value ?? '')" @change="setObjectMapValue(omf.key, entry.key, ($event.target as HTMLInputElement).value)" />
                <input v-else-if="entry.type === 'number'" class="mep-cfg-input" type="number" :value="Number(entry.value) || 0" @change="setObjectMapValue(omf.key, entry.key, Number(($event.target as HTMLInputElement).value) || 0)" />
                <input v-else-if="entry.type === 'boolean'" type="checkbox" :checked="!!entry.value" @change="setObjectMapValue(omf.key, entry.key, ($event.target as HTMLInputElement).checked)" />
                <textarea v-else class="mep-cfg-textarea" :value="typeof entry.value === 'object' ? JSON.stringify(entry.value, null, 2) : String(entry.value ?? '')" @change="setJsonVal(`${omf.key}.${entry.key}`, ($event.target as HTMLTextAreaElement).value)" rows="2" />
              </template>
              <button class="mep-om-del" @click="deleteObjectMapKey(omf.key, entry.key)" title="删除此键">✕</button>
            </div>
            <div class="mep-om-empty" v-if="!objectMapEntries(omf.key).length">当前为空</div>
            <button class="mep-om-add" @click="addObjectMapKey(omf.key)">+ 新增条目</button>
          </template>

          <!-- Extra config sections (non-template, non-object-map) -->
          <template v-for="(sec, si) in extraConfigSections" :key="si">
            <div v-if="sec.section" class="mep-cfg-section">{{ sec.section }}</div>
            <div v-for="f in sec.rows" :key="f.path" class="mep-cfg-row">
              <label :title="f.path">{{ f.key }}</label>
              <span v-if="isFieldBound(f.path)" class="mep-bound">{{ f.value }} <em>⇠ {{ isFieldBound(f.path)!.nodeName }}:{{ isFieldBound(f.path)!.portId }}</em></span>
              <template v-else>
                <span v-if="f.type === 'string'" style="display:flex;gap:2px;flex:1">
                  <input class="mep-cfg-input" :value="String(f.value ?? '')" @change="setCfgVal(f.path, ($event.target as HTMLInputElement).value)" />
                  <button v-if="getParamSchema(f.key)?.editor_kind === 'path'" class="mep-path-btn" @click="pickPathForField(f.path)" title="选择路径">…</button>
                </span>
                <input v-else-if="f.type === 'number'" class="mep-cfg-input" type="number" :value="String(f.value ?? '')" @change="setCfgVal(f.path, Number(($event.target as HTMLInputElement).value) || 0)" />
                <input v-else-if="f.type === 'boolean'" type="checkbox" :checked="!!f.value" @change="setCfgVal(f.path, ($event.target as HTMLInputElement).checked)" />
                <textarea v-else class="mep-cfg-textarea" :value="typeof f.value === 'object' ? JSON.stringify(f.value, null, 2) : String(f.value ?? '')" @change="setJsonVal(f.path, ($event.target as HTMLTextAreaElement).value)" rows="3" />
              </template>
            </div>
          </template>
          <div v-if="!paramFields.length && !extraConfigSections.length && !objectMapFields.length" class="mep-empty-cfg">无配置参数</div>
        </div>
      </div>
    </template>
  </div>
</template>
<style scoped>
.mep { padding: var(--space-sm); font-size: var(--text-small); height: 100%; overflow-y: auto; }
.mep-search-row { position: relative; margin-bottom: var(--space-sm); }
.mep-search { width: 100%; padding: 2px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.mep-search-drop { position: absolute; top: 100%; left: 0; right: 0; z-index: 50; background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-menu); max-height: 180px; overflow-y: auto; }
.mep-search-item { display: flex; gap: var(--space-sm); padding: 3px 8px; cursor: pointer; font-size: var(--text-small); }
.mep-search-item:hover { background: var(--bg-hover); }
.mep-search-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mep-search-kid { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.mep-title { font-size: var(--text-body); font-weight: 600; color: var(--text-primary); }
.mep-locate-btn { padding: 1px 8px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: transparent; color: var(--accent); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.mep-locate-btn:hover { background: var(--accent-light); }
.mep-grid { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-lg); }
.mep-row { display: flex; gap: var(--space-sm); align-items: baseline; }
.mep-row label { width: 56px; flex-shrink: 0; color: var(--text-disabled); font-size: var(--text-caption); }
.mep-row code { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); background: var(--bg-input); padding: 1px 4px; border-radius: 2px; }
.mep-row span { color: var(--text-secondary); }
.mep-section { margin-top: var(--space-md); }
.mep-section h5 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: var(--space-xs); }
.mep-input { flex: 1; padding: 1px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.mep-hint { font-size: var(--text-caption); color: var(--text-disabled); }
.mep-config { margin-top: var(--space-xs); }
.mep-cfg-section { font-size: var(--text-caption); font-weight: 600; color: var(--text-disabled); text-transform: uppercase; letter-spacing: 0.04em; padding: 4px 0 2px; border-bottom: 1px dotted var(--border-subtle); margin-top: 4px; }
.mep-bound { flex: 1; font-size: var(--text-small); color: var(--state-info); font-weight: 500; }
.mep-bound em { font-style: normal; font-size: var(--text-caption); color: var(--text-disabled); }
.mep-cfg-row { display: flex; gap: var(--space-xs); padding: 2px 0; align-items: center; }
.mep-cfg-row label { width: 80px; flex-shrink: 0; font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); overflow: hidden; text-overflow: ellipsis; }
.mep-cfg-input { flex: 1; padding: 1px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.mep-empty-cfg { font-size: var(--text-small); color: var(--text-disabled); padding: var(--space-sm) 0; }
.mep-cfg-textarea { flex: 1; padding: 2px 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; resize: vertical; }
.mep-schema-block { margin-bottom: var(--space-sm); }
.mep-schema-block h6 { font-size: var(--text-caption); font-weight: 600; color: var(--text-secondary); margin-bottom: 2px; }
.mep-schema-row { display: flex; gap: var(--space-xs); padding: 1px 0; font-size: var(--text-caption); }
.mep-schema-key { font-family: var(--font-mono); color: var(--text-primary); min-width: 80px; }
.mep-schema-type { color: var(--text-disabled); }
.mep-schema-req { color: var(--state-error); font-weight: 600; font-size: 9px; }

/* Object-map editor */
.mep-om-row { display: flex; gap: var(--space-xs); padding: 2px 0; align-items: center; }
.mep-om-key { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-primary); min-width: 70px; cursor: pointer; padding: 1px 4px; border-radius: 2px; }
.mep-om-key:hover { background: var(--bg-hover); }
.mep-om-key-input { font-family: var(--font-mono); font-size: var(--text-caption); min-width: 70px; padding: 1px 4px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); }
.mep-om-del { width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; border-radius: 2px; padding: 0; flex-shrink: 0; }
.mep-om-del:hover { color: var(--state-error); background: rgba(208,112,96,0.08); }
.mep-om-add { margin-top: 2px; padding: 1px 8px; border: 1px dashed var(--border-default); border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.mep-om-add:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.mep-om-empty { font-size: var(--text-caption); color: var(--text-disabled); padding: 1px 0; }

/* Typed-value editor */
.mep-type-sel { padding: 1px 4px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-caption); cursor: pointer; width: 64px; flex-shrink: 0; }
.mep-check-label { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: var(--text-small); color: var(--text-primary); }
.mep-check-label input { margin: 0; }
.mep-null { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); font-style: italic; }
.mep-path-btn { padding: 1px 8px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-body); font-family: var(--font-ui); flex-shrink: 0; }
.mep-path-btn:hover { background: var(--bg-hover); }

/* Branch-list editor */
.mep-br-row { display: flex; gap: var(--space-xs); padding: 2px 0; align-items: center; }
.mep-br-key { width: 80px; padding: 1px 4px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-mono); font-size: var(--text-caption); }
.mep-br-label { flex: 1; padding: 1px 4px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.mep-br-norm { margin-top: 4px; padding: 2px 10px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: transparent; color: var(--accent); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.mep-br-norm:hover:not(:disabled) { background: var(--accent-light); }
.mep-br-norm:disabled { opacity: 0.5; }

.mep-code-row { display: flex; flex-direction: column; padding: 4px 0; }
.mep-code-label { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); margin-bottom: 2px; }
.mep-code-editor { height: 120px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); overflow: hidden; }
</style>
