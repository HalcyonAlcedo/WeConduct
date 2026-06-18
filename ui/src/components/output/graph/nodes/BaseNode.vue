<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed, ref } from 'vue'
import { useResourceStore } from '@/stores/resourceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { postFileDialog, postGraphNormalize } from '@/services/api'
import { useToastStore } from '@/stores/toastStore'

const toast = useToastStore()

const props = defineProps<{
  id: string
  data: { label: string; nodeId?: string; kind: string; expansionRole: string; nodeKind?: string; ports?: { port_id: string; direction: string; semantic_slot?: string; display_name?: string | null }[] }
  selected?: boolean
}>()

const resource = useResourceStore()
const workspace = useGraphWorkspaceStore()

const nodePorts = computed(() => props.data.ports || [])
const inputPorts = computed(() => nodePorts.value.filter(p => p.direction === 'input'))
const outputPorts = computed(() => nodePorts.value.filter(p => p.direction === 'output'))

function portLabel(p: { semantic_slot?: string; display_name?: string | null }) {
  const raw = p.display_name || p.semantic_slot || ''
  return raw.replace(/\.(in|out)$/, '').replace(/^(in|out)\./, '').replace(/\.(in|out)\./, '.') // direction already clear from L/R
}

const COMPAT_KINDS = new Set(['control.jump_to_step', 'control.end_foreach', 'control.foreach_continue', 'control.foreach_break'])
const isDisabled = computed(() => { const nk = props.data.nodeKind; if (!nk) return false; return resource.getResourceEnabledState(nk) === false })
const isCompatibility = computed(() => { const nk = props.data.nodeKind; if (!nk) return false; return COMPAT_KINDS.has(nk) })
const kindLabel = computed(() => { switch (props.data.kind) { case 'execution': return '执行'; case 'control': return '控制'; case 'observe': return '观察'; case 'bridge': return '桥接'; default: return props.data.kind } })
const kindClass = computed(() => `node-${props.data.kind}`)

// Config grouped by parent key: flat values directly, object values under section header
interface CfgRow { path: string; key: string; display: string; editable: boolean; value: unknown }
interface CfgSection { section?: string; rows: CfgRow[] }
// Check if a config field has a data edge binding (match by port_id suffix or port semantic_slot)
function findBinding(key: string): { nodeName: string; portId: string } | null {
  const nodeId = props.data.nodeId; if (!nodeId) return null
  const gm = workspace.graphModel; if (!gm) return null
  const targetNode = gm.nodes.find(n => n.node_id === nodeId)
  const edge = gm.edges.find(e => {
    if (e.to_node_id !== nodeId || e.relation_layer !== 'data') return false
    // Direct match: to_port_id equals the key or ends with .key
    if (e.to_port_id === key || e.to_port_id?.endsWith('.' + key)) return true
    // Semantic match: target port's semantic_slot matches the key
    const port = targetNode?.ports?.find(p => p.port_id === e.to_port_id)
    if (port && (port.semantic_slot === key || port.semantic_slot?.endsWith('.' + key) || key.endsWith('.' + (port.semantic_slot || '')))) return true
    return false
  })
  if (!edge) return null
  const srcNode = gm.nodes.find(n => n.node_id === edge.from_node_id)
  return { nodeName: srcNode?.display_name || edge.from_node_id, portId: edge.from_port_id || edge.to_port_id || 'out' }
}

const configSections = computed(() => {
  const node = workspace.graphModel?.nodes.find(n => n.node_id === props.data.nodeId)
  const cfg = node?.node_config || {}
  const sections: CfgSection[] = []
  for (const [k, v] of Object.entries(cfg)) {
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      const rows: CfgRow[] = []
      for (const [sk, sv] of Object.entries(v as Record<string, unknown>)) {
        const binding = findBinding(`${k}.${sk}`) || findBinding(sk)
        rows.push({ path: `${k}.${sk}`, key: sk, value: sv, editable: !binding && isEditable(sv), display: binding ? `⇠ ${binding.nodeName}:${binding.portId}` : formatVal(sv) })
      }
      sections.push({ section: k, rows })
    } else {
      const binding = findBinding(k)
      sections.push({ rows: [{ path: k, key: k, value: v, editable: !binding && isEditable(v), display: binding ? `⇠ ${binding.nodeName}:${binding.portId}` : formatVal(v) }] })
    }
  }
  return sections
})
function isEditable(v: unknown) { return typeof v === 'string' || typeof v === 'boolean' || typeof v === 'number' }
function formatVal(v: unknown): string {
  if (typeof v === 'string') return v.slice(0, 30)
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) {
    const labels = v.filter((b: any) => b && b.label).map((b: any) => b.label).slice(0, 3)
    return labels.join(', ') + (v.length > 3 ? ` …(${v.length})` : ` (${v.length})`)
  }
  return '(' + typeof v + ')'
}

function updateConfigField(path: string, raw: string) {
  const node = workspace.graphModel?.nodes.find(n => n.node_id === props.data.nodeId)
  if (!node) return
  const cfg = JSON.parse(JSON.stringify(node.node_config || {})) // deep clone
  if (path.includes('.')) {
    const [parent, key] = path.split('.')
    if (!cfg[parent] || typeof cfg[parent] !== 'object') cfg[parent] = {}
    ;(cfg[parent] as Record<string, unknown>)[key] = coerceType((cfg[parent] as Record<string, unknown>)[key], raw)
  } else {
    cfg[path] = coerceType(cfg[path], raw)
  }
  workspace.updateNode(node.node_id, { node_config: cfg })
}

function getNodeKind(): string {
  const n = workspace.graphModel?.nodes.find(n => n.node_id === props.data.nodeId)
  return n?.node_kind || ''
}

function isPathField(fieldKey: string): boolean {
  const schemas = workspace.parameterSchemas[getNodeKind()]
  return schemas?.[fieldKey]?.editor_kind === 'path'
}

async function pickPathForInline(fieldKey: string) {
  const schemas = workspace.parameterSchemas[getNodeKind()]
  const schema = schemas?.[fieldKey]
  if (!schema) return
  const mode = schema.path_kind === 'save_file' ? 'save_file'
    : schema.path_kind === 'open_directory' ? 'open_folder'
    : 'open_file'
  try {
    const r = await postFileDialog({ mode, title: schema.label || `选择 ${fieldKey}` })
    if (r.status === 'selected' && r.paths.length) {
      updateConfigField(fieldKey, r.paths[0])
    }
  } catch { /* unsupported */ }
}
function coerceType(prev: unknown, raw: string): unknown {
  if (typeof prev === 'number') { const n = Number(raw); return isNaN(n) ? raw : n }
  if (typeof prev === 'boolean') return raw === 'true'
  return raw
}

// ---- Branch inline editor popup ----
const branchEditorOpen = ref(false)
const branchEditorKey = ref('')
interface BranchItem { key: string; label: string }
const branchEditorItems = ref<BranchItem[]>([])

function openBranchEditor(fieldKey: string) {
  const node = workspace.graphModel?.nodes.find(n => n.node_id === props.data.nodeId)
  const v = node?.node_config?.[fieldKey]
  if (Array.isArray(v)) {
    branchEditorKey.value = fieldKey
    branchEditorItems.value = JSON.parse(JSON.stringify(v.filter((b: any) => b && typeof b === 'object').map((b: any) => ({ key: String(b.key || ''), label: String(b.label || '') }))))
    branchEditorOpen.value = true
  }
}

function addBranchItem() {
  let n = branchEditorItems.value.length + 1
  while (branchEditorItems.value.some(b => b.key === `branch_${n}`)) n++
  branchEditorItems.value.push({ key: `branch_${n}`, label: `分支 ${n}` })
}

function deleteBranchItem(idx: number) {
  if (branchEditorItems.value.length <= 2) { toast.info('', '至少保留 2 个分支'); return }
  branchEditorItems.value.splice(idx, 1)
}

async function applyBranches() {
  const node = workspace.graphModel?.nodes.find(n => n.node_id === props.data.nodeId)
  if (!node) return
  const keys = branchEditorItems.value.map(b => b.key.trim())
  if (keys.some(k => !k)) { toast.info('', '分支 key 不能为空'); return }
  if (new Set(keys).size !== keys.length) { toast.info('', '分支 key 不能重复'); return }
  const cfg = JSON.parse(JSON.stringify(node.node_config || {}))
  cfg[branchEditorKey.value] = JSON.parse(JSON.stringify(branchEditorItems.value))
  workspace.updateNode(node.node_id, { node_config: cfg })
  try {
    const r = await postGraphNormalize(workspace.graphModel as any)
    if (r.graph_model) {
      workspace.graphModel = r.graph_model as any
      workspace.changeRevision++
    }
  } catch (e: any) { toast.error('同步失败', e?.message) }
  branchEditorOpen.value = false
}
</script>

<template>
  <div :class="['vf-node', kindClass, { selected, 'node-disabled': isDisabled }]">
    <!-- Header: full width -->
    <div class="vf-node-header">
      <span class="vf-node-kind">{{ kindLabel }}</span>
      <span v-if="isDisabled" class="vf-disabled-badge">禁用</span>
      <span v-if="isCompatibility" class="vf-compat-badge">兼容</span>
      <span v-if="data.nodeId" class="vf-node-id">{{ data.nodeId }}</span>
    </div>

    <!-- Body: three-column — left ports | content | right ports -->
    <div class="vf-node-row">
      <div class="vf-port-col" v-if="inputPorts.length">
        <div v-for="p in inputPorts" :key="p.port_id" class="vf-port-item">
          <Handle type="target" :position="Position.Left" :id="p.port_id" class="vf-handle" />
          <span class="vf-port-label">{{ portLabel(p) }}</span>
        </div>
      </div>

      <div class="vf-node-main">
        <div class="vf-node-body">
          <span class="vf-node-label">{{ data.label }}</span>
          <div v-if="configSections.length" class="vf-config">
            <template v-for="(sec, si) in configSections" :key="si">
              <div v-if="sec.section" class="vf-cfg-section">{{ sec.section }}</div>
              <div v-for="e in sec.rows" :key="e.path" class="vf-cfg-row">
                <span class="vf-cfg-key">{{ e.key }}</span>
                <input v-if="e.editable && typeof e.value === 'boolean'" type="checkbox" :checked="!!e.value" @change="updateConfigField(e.path, String(($event.target as HTMLInputElement).checked))" @mousedown.stop @click.stop />
                <input v-else-if="e.editable && typeof e.value === 'number'" class="vf-cfg-input" type="number" :value="e.value as number" @change="updateConfigField(e.path, ($event.target as HTMLInputElement).value)" @mousedown.stop @click.stop />
                <span v-else-if="e.editable" style="display:flex;gap:1px;align-items:center">
                  <input class="vf-cfg-input" :value="String(e.value ?? '')" @change="updateConfigField(e.path, ($event.target as HTMLInputElement).value)" @mousedown.stop @click.stop />
                  <button v-if="isPathField(e.key)" class="vf-path-btn" @mousedown.stop @click.stop @click="pickPathForInline(e.path)" title="选择路径">…</button>
                </span>
                <span v-else class="vf-cfg-ro" :class="{ 'vf-bound': e.display.startsWith('⇠') }">{{ e.display }}</span>
                <button v-if="Array.isArray(e.value)" class="vf-branch-edit" @mousedown.stop @click.stop @click="openBranchEditor(e.path)" title="编辑分支">⚙</button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div class="vf-port-col" v-if="outputPorts.length">
        <div v-for="p in outputPorts" :key="p.port_id" class="vf-port-item">
          <span class="vf-port-label">{{ portLabel(p) }}</span>
          <Handle type="source" :position="Position.Right" :id="p.port_id" class="vf-handle" />
        </div>
      </div>
    </div>

    <!-- No ports: still allow edge connection via node-level (no Handle id) -->
    <template v-if="!nodePorts.length">
      <Handle type="target" :position="Position.Left" class="vf-handle vf-no-port" />
      <Handle type="source" :position="Position.Right" class="vf-handle vf-no-port" />
    </template>

    <!-- Branch editor popup -->
    <Teleport to="body">
      <div v-if="branchEditorOpen" class="br-overlay" @click.self="branchEditorOpen = false">
        <div class="br-box">
          <div class="br-hd">
            <span>编辑 {{ branchEditorKey }}</span>
            <button class="br-close" @click="branchEditorOpen = false">✕</button>
          </div>
          <div class="br-body">
            <div v-for="(b, bi) in branchEditorItems" :key="bi" class="br-row">
              <input class="br-key" :value="b.key" @change="branchEditorItems[bi].key = ($event.target as HTMLInputElement).value" placeholder="key" />
              <input class="br-label" :value="b.label" @change="branchEditorItems[bi].label = ($event.target as HTMLInputElement).value" placeholder="label" />
              <button class="br-del" @click="deleteBranchItem(bi)">✕</button>
            </div>
            <button class="br-add" @click="addBranchItem">+ 新增分支</button>
          </div>
          <div class="br-ft">
            <button class="br-apply" @click="applyBranches">应用并同步端口</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.vf-node {
  background: var(--bg-panel); border: 1.5px solid var(--border-default);
  border-radius: var(--radius-md); min-width: 180px; padding: 0;
  font-family: var(--font-ui); font-size: var(--text-small);
  box-shadow: var(--shadow-panel); transition: border-color 100ms, box-shadow 100ms;
}
.vf-node.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-light); }

/* Three-column row */
.vf-node-row { display: flex; align-items: stretch; }
.vf-node-main { flex: 1; min-width: 100px; }

.vf-node-header { display: flex; align-items: center; gap: 4px; padding: 3px 8px; border-bottom: 1px solid var(--border-subtle); background: var(--bg-panel-header); border-radius: var(--radius-md) var(--radius-md) 0 0; }
.vf-node-body { padding: 4px 8px; }
.vf-node-kind { font-size: var(--text-caption); font-weight: 600; color: var(--text-secondary); letter-spacing: 0.03em; }
.vf-node-id { font-family: var(--font-mono); font-size: 9px; color: var(--text-disabled); margin-left: auto; flex-shrink: 0; }
.vf-node-label { font-family: var(--font-ui); font-size: var(--text-body); color: var(--text-primary); font-weight: 500; display: block; margin-bottom: 2px; }
.vf-disabled-badge { font-size: var(--text-caption); font-weight: 600; color: var(--state-error); background: rgba(208,112,96,0.12); padding: 0 3px; border-radius: 2px; }
.vf-compat-badge { font-size: var(--text-caption); font-weight: 600; color: var(--state-info); background: rgba(107,154,168,0.12); padding: 0 3px; border-radius: 2px; }

/* Port columns — integrated into flow, not absolute */
.vf-port-col {
  display: flex; flex-direction: column; justify-content: center; gap: 8px;
  padding: 8px 3px; min-width: 14px; flex-shrink: 0;
}
.vf-port-item { display: flex; align-items: center; gap: 10px; height: 20px; position: relative; }
.vf-port-label { font-size: 8px; color: var(--text-disabled); white-space: nowrap; max-width: 50px; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; margin: 0 3px; }

.vf-handle { width: 8px !important; height: 8px !important; background: var(--border-default) !important; border: 2px solid var(--bg-panel) !important; border-radius: 50% !important; }
.vf-handle:hover { background: var(--accent) !important; outline: 2px solid var(--accent-light); outline-offset: 1px; }
.vf-no-port { opacity: 0.2; width: 5px !important; height: 5px !important; border-width: 1px !important; }

/* Inline config */
.vf-config { margin-top: 4px; border-top: 1px solid var(--border-subtle); padding-top: 3px; }
.vf-cfg-section { font-size: 8px; font-weight: 600; color: var(--text-disabled); text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 0 1px; border-bottom: 1px dotted var(--border-subtle); margin-top: 2px; }
.vf-cfg-row { display: flex; gap: 4px; align-items: center; padding: 1px 0; }
.vf-path-btn { padding: 0 4px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; border-radius: 2px; font-size: 10px; line-height: 1.2; flex-shrink: 0; }
.vf-path-btn:hover { background: var(--bg-hover); }
.vf-cfg-key { font-size: 9px; font-family: var(--font-mono); color: var(--text-disabled); width: 60px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vf-cfg-input { flex: 1; padding: 0 4px; border: 1px solid var(--border-subtle); border-radius: 2px; background: var(--bg-input); color: var(--text-primary); font-size: 10px; font-family: var(--font-ui); min-width: 0; }
.vf-cfg-input:focus { border-color: var(--accent); outline: none; }
.vf-cfg-ro { flex: 1; font-size: 10px; color: var(--text-disabled); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-style: italic; }
.vf-cfg-ro.vf-bound { color: var(--state-info); font-style: normal; font-weight: 500; }
.vf-branch-edit { margin-left: auto; padding: 0 3px; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; flex-shrink: 0; }
.vf-branch-edit:hover { color: var(--accent); }

/* Branch editor popup */
.br-overlay { position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; }
.br-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-lg); min-width: 320px; max-width: 420px; box-shadow: var(--shadow-menu); }
.br-hd { display: flex; align-items: center; padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--border-subtle); font-size: var(--text-body); font-weight: 600; color: var(--text-primary); }
.br-close { margin-left: auto; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 12px; }
.br-body { padding: var(--space-sm) var(--space-md); max-height: 300px; overflow-y: auto; }
.br-row { display: flex; gap: 4px; padding: 2px 0; align-items: center; }
.br-key { width: 80px; padding: 1px 4px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; }
.br-label { flex: 1; padding: 1px 4px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: 11px; }
.br-del { width: 18px; height: 18px; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; padding: 0; }
.br-del:hover { color: var(--state-error); }
.br-add { margin-top: 4px; padding: 1px 8px; border: 1px dashed var(--border-default); background: transparent; color: var(--text-secondary); cursor: pointer; font-size: 11px; border-radius: var(--radius-sm); }
.br-add:hover { border-color: var(--accent); color: var(--accent); }
.br-ft { padding: var(--space-sm) var(--space-md); border-top: 1px solid var(--border-subtle); }
.br-apply { width: 100%; padding: 4px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--accent); color: #fff; cursor: pointer; font-size: var(--text-small); font-family: var(--font-ui); }
.br-apply:hover { background: var(--accent-hover); }

.node-execution { border-left: 3px solid var(--state-info); }
.node-control   { border-left: 3px solid #9B80B4; }
.node-observe   { border-left: 3px solid var(--state-warning); }
.node-bridge    { border-left: 3px solid var(--state-success); }
.node-disabled { opacity: 0.55; }
</style>
