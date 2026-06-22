<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { postResourceEnabled, postResourceTags, postCreateEmptyCustomComponent, postResourceDelete, postResourceMetadata } from '@/services/api'
import { useResourceStore } from '@/stores/resourceStore'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useToastStore } from '@/stores/toastStore'
import type { ResourceItem } from '@/types/domains/api'

const resource = useResourceStore()
const graphWs = useGraphWorkspaceStore()
const toast = useToastStore()
const loading = ref(true)
const expandedRes = ref<string | null>(null)
const showNewDlg = ref(false)
const newCompName = ref('')
const deleteConfirmId = ref<string | null>(null)
const editDialogId = ref<string | null>(null)
const editDialogName = ref('')
const filterCategory = ref<string[] | null>(null)
const filterTag = ref('')

onMounted(async () => { await resource.refreshAll(); loading.value = false })

function showCatPath(path: string[]) { return path.join(' / ') }
function selectCategory(path: string[]) { filterCategory.value = filterCategory.value?.[0] === path[0] ? null : path }
function selectTag(tag: string) {
  filterTag.value = filterTag.value === tag ? '' : tag
  resource.refreshAll(filterTag.value ? { tags: filterTag.value } : undefined)
}

const builtinResources = computed(() => {
  let list = resource.resources.filter(r => r.resource_type === 'builtin_component')
  if (filterCategory.value) { const cat = filterCategory.value.join('/'); list = list.filter(r => (r.category_group_path || r.category_path || []).join('/') === cat) }
  if (filterTag.value) list = list.filter(r => r.tags?.includes(filterTag.value))
  return list
})
const userResources = computed(() => {
  let list = resource.resources.filter(r => r.resource_type === 'custom_node_graph' || r.origin === 'project')
  if (filterCategory.value) { const cat = filterCategory.value.join('/'); list = list.filter(r => (r.category_group_path || r.category_path || []).join('/') === cat) }
  if (filterTag.value) list = list.filter(r => r.tags?.includes(filterTag.value))
  return list
})

function schemaFields(schema: Record<string, any> | undefined): { key: string; type: string; required: boolean }[] {
  if (!schema) return []
  return Object.entries(schema).map(([k, v]) => ({ key: k, type: (v as any)?.type || 'string', required: !!(v as any)?.required }))
}

async function toggleEnabled(r: ResourceItem) {
  try { await postResourceEnabled(r.resource_id, !r.enabled); await resource.refreshAll(); toast.info('已更新', r.display_name) }
  catch (e: any) { toast.error('操作失败', e?.message) }
}

const editTagsId = ref<string | null>(null)
const editTagsInput = ref('')
function startTagEdit(r: ResourceItem) { editTagsId.value = r.resource_id; editTagsInput.value = (r.tags || []).join(', ') }
async function saveTags(r: ResourceItem) {
  const tags = editTagsInput.value.split(',').map(t => t.trim()).filter(Boolean)
  try { await postResourceTags(r.resource_id, tags); await resource.refreshAll(); editTagsId.value = null; toast.info('标签已更新') }
  catch (e: any) { toast.error('更新失败', e?.message) }
}

async function openComponentGraph(r: ResourceItem) {
  const docId = `custom_node_graph:${r.resource_id}`
  await graphWs.loadGraph(docId)
  await graphWs.syncSource()
  await graphWs.refreshGraphDocuments()
  toast.info('已打开', r.display_name)
}

async function createNewComponent() {
  const name = newCompName.value.trim()
  if (!name) return
  try {
    const r = await postCreateEmptyCustomComponent(name)
    toast.success('已创建', r.resource.display_name)
    await resource.refreshAll()
    await graphWs.refreshGraphDocuments()
    showNewDlg.value = false; newCompName.value = ''
  } catch (e: any) { toast.error('创建失败', e?.message) }
}

function startDelete(r: ResourceItem) { deleteConfirmId.value = r.resource_id }
async function confirmDelete() {
  if (!deleteConfirmId.value) return
  try { await postResourceDelete(deleteConfirmId.value); await resource.refreshAll(); deleteConfirmId.value = null; toast.info('已删除') }
  catch (e: any) { toast.error('删除失败', e?.message) }
}

function startEdit(r: ResourceItem) { editDialogId.value = r.resource_id; editDialogName.value = r.display_name }
async function confirmEdit() {
  if (!editDialogId.value || !editDialogName.value.trim()) return
  try { await postResourceMetadata(editDialogId.value, { display_name: editDialogName.value.trim() }); await resource.refreshAll(); editDialogId.value = null; toast.info('已更新') }
  catch (e: any) { toast.error('更新失败', e?.message) }
}
</script>
<template>
  <div class="rmp">
    <div class="rmp-toolbar">
      <button class="rmp-btn" @click="showNewDlg = true">新建</button>
    </div>
    <div v-if="loading" class="rmp-load">加载中…</div>
    <template v-else>
      <div class="rmp-filters" v-if="resource.resourceFacets">
        <div class="rmp-filter-section" v-if="resource.resourceFacets.category_groups?.length">
          <span class="rmp-filter-label">分类:</span>
          <button v-for="cg in resource.resourceFacets.category_groups.slice(0, 8)" :key="cg.label" class="rmp-filter-chip" :class="{ active: filterCategory && showCatPath(filterCategory) === showCatPath(cg.path) }" @click="selectCategory(cg.path)">{{ cg.label || showCatPath(cg.path) }}</button>
        </div>
        <div class="rmp-filter-section" v-if="resource.resourceFacets.user_tags?.length">
          <span class="rmp-filter-label">标签:</span>
          <button v-for="t in resource.resourceFacets.user_tags.slice(0, 10)" :key="t" class="rmp-filter-chip" :class="{ active: filterTag === t }" @click="selectTag(t)">{{ t }}</button>
        </div>
        <div v-if="filterCategory || filterTag" class="rmp-filter-active">
          筛选: {{ filterCategory ? showCatPath(filterCategory) : '' }}{{ filterTag ? ' ' + filterTag : '' }} <button class="rmp-filter-clear" @click="filterCategory=null;filterTag=''">✕ 清除</button>
        </div>
      </div>

      <!-- Builtin Section -->
      <h4 class="rmp-section-hd">📦 内置组件 ({{ builtinResources.length }})</h4>
      <table v-if="builtinResources.length" class="rmp-table">
        <thead><tr><th>名称</th><th>类型</th><th>标签</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in builtinResources" :key="r.resource_id">
            <td>{{ r.display_name }}</td>
            <td class="rmp-mono">{{ r.resource_type }}</td>
            <td>
              <template v-if="editTagsId === r.resource_id">
                <input v-model="editTagsInput" class="rmp-tag-input" @keyup.enter="saveTags(r)" @keyup.escape="editTagsId = null" @click.stop />
                <button class="rmp-toggle" @click.stop="saveTags(r)">✓</button>
              </template>
              <template v-else>
                <span v-for="t in (r.tags || [])" :key="t" class="rmp-tag">{{ t }}</span>
                <button class="rmp-tag-edit" @click.stop="startTagEdit(r)" title="编辑标签">+</button>
              </template>
            </td>
            <td><span :class="r.enabled ? 'rmp-on' : 'rmp-off'">{{ r.enabled ? '启用' : '禁用' }}</span></td>
            <td><button class="rmp-toggle" @click="toggleEnabled(r)">{{ r.enabled ? '禁用' : '启用' }}</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="rmp-empty">暂无内置组件</div>

      <!-- User Section -->
      <h4 class="rmp-section-hd" style="margin-top:16px">🔧 用户组件 ({{ userResources.length }})</h4>
      <table v-if="userResources.length" class="rmp-table">
        <thead><tr><th>名称</th><th>类型</th><th>标签</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in userResources" :key="r.resource_id">
            <td>{{ r.display_name }}</td>
            <td class="rmp-mono">{{ r.resource_type || r.resource_key }}</td>
            <td>
              <template v-if="editTagsId === r.resource_id">
                <input v-model="editTagsInput" class="rmp-tag-input" @keyup.enter="saveTags(r)" @keyup.escape="editTagsId = null" @click.stop />
                <button class="rmp-toggle" @click.stop="saveTags(r)">✓</button>
              </template>
              <template v-else>
                <span v-for="t in (r.tags || [])" :key="t" class="rmp-tag">{{ t }}</span>
                <button class="rmp-tag-edit" @click.stop="startTagEdit(r)" title="编辑标签">+</button>
              </template>
            </td>
            <td><span :class="r.enabled ? 'rmp-on' : 'rmp-off'">{{ r.enabled ? '启用' : '禁用' }}</span></td>
            <td>
              <button class="rmp-toggle" @click="toggleEnabled(r)">{{ r.enabled ? '禁用' : '启用' }}</button>
              <button v-if="r.resource_type === 'custom_node_graph'" class="rmp-toggle" style="margin-left:4px" @click="startEdit(r)">编辑</button>
              <button v-if="r.resource_type === 'custom_node_graph'" class="rmp-toggle" style="margin-left:4px" @click="openComponentGraph(r)">打开</button>
              <button v-if="r.resource_type === 'custom_node_graph'" class="rmp-toggle" style="margin-left:4px" @click="startDelete(r)">删除</button>
              <button v-if="r.resource_type === 'custom_node_graph'" class="rmp-toggle" style="margin-left:4px" @click="expandedRes = expandedRes === r.resource_id ? null : r.resource_id">Schema</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="rmp-empty">暂无用户组件 — 在节点图编辑器中点击 + 新建</div>

      <div v-if="expandedRes" class="rmp-schema">
        <h5>{{ resource.resources.find(r => r.resource_id === expandedRes)?.display_name }} — Schema</h5>
        <div class="rmp-schema-grid">
          <div><strong>Input Schema</strong>
            <div v-if="!(resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema || !Object.keys((resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema || {}).length">未声明</div>
            <div v-for="f in schemaFields((resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema)" :key="f.key" class="rmp-schema-row">{{ f.key }} <span class="rmp-mono">{{ f.type }}</span> <span v-if="f.required" class="rmp-req">必填</span></div>
          </div>
          <div><strong>Output Schema</strong>
            <div v-if="!(resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema || !Object.keys((resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema || {}).length">未声明</div>
            <div v-for="f in schemaFields((resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema)" :key="f.key" class="rmp-schema-row">{{ f.key }} <span class="rmp-mono">{{ f.type }}</span></div>
          </div>
        </div>
      </div>
    </template>
    <Teleport to="body">
      <!-- Delete confirm -->
      <div v-if="deleteConfirmId" class="rmp-dlg-overlay" @click.self="deleteConfirmId = null">
        <div class="rmp-dlg-box"><div class="rmp-dlg-hd">确认删除<span class="rmp-dlg-close" @click="deleteConfirmId = null">✕</span></div><div class="rmp-dlg-body">确定要删除此用户组件？此操作不可撤销。</div><div class="rmp-dlg-ft"><button class="rmp-dlg-btn" style="background:var(--state-error);border-color:var(--state-error)" @click="confirmDelete()">删除</button><button class="rmp-dlg-btn" style="background:transparent;color:var(--text-secondary);border-color:var(--border-default);margin-left:8px" @click="deleteConfirmId = null">取消</button></div></div>
      </div>
      <!-- Edit metadata -->
      <div v-if="editDialogId" class="rmp-dlg-overlay" @click.self="editDialogId = null">
        <div class="rmp-dlg-box"><div class="rmp-dlg-hd">编辑组件<span class="rmp-dlg-close" @click="editDialogId = null">✕</span></div><div class="rmp-dlg-body"><input v-model="editDialogName" class="rmp-dlg-input" placeholder="组件名称" @keyup.enter="confirmEdit()" /></div><div class="rmp-dlg-ft"><button class="rmp-dlg-btn" @click="confirmEdit()" :disabled="!editDialogName.trim()">保存</button></div></div>
      </div>
      <!-- New component -->
      <div v-if="showNewDlg" class="rmp-dlg-overlay" @click.self="showNewDlg = false">
        <div class="rmp-dlg-box">
          <div class="rmp-dlg-hd">新建用户组件<span class="rmp-dlg-close" @click="showNewDlg = false">✕</span></div>
          <div class="rmp-dlg-body"><input v-model="newCompName" class="rmp-dlg-input" placeholder="组件名称" @keyup.enter="createNewComponent" /></div>
          <div class="rmp-dlg-ft"><button class="rmp-dlg-btn" @click="createNewComponent" :disabled="!newCompName.trim()">创建</button></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
<style scoped>
.rmp { padding: var(--space-sm); overflow-y: auto; font-size: var(--text-small); height: 100%; }
.rmp-toolbar { display: flex; gap: var(--space-xs); margin-bottom: var(--space-sm); align-items: center; }
.rmp-btn { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); }
.rmp-btn:disabled { opacity: 0.5; cursor: not-allowed; color: var(--text-disabled); border-style: dashed; }
.rmp-label { font-size: var(--text-caption); color: var(--text-disabled); }
.rmp-load, .rmp-empty { padding: var(--space-md); color: var(--text-disabled); }
.rmp-section-hd { font-size: var(--text-small); font-weight: 700; color: var(--text-primary); margin-bottom: 4px; border-bottom: 2px solid var(--accent); padding-bottom: 2px; }
.rmp-table { width: 100%; border-collapse: collapse; }
.rmp-table th { text-align: left; padding: 2px 6px; color: var(--text-disabled); font-weight: 600; font-size: var(--text-caption); border-bottom: 1px solid var(--border-subtle); }
.rmp-table td { padding: 2px 6px; border-bottom: 1px solid var(--border-subtle); }
.rmp-mono { font-family: var(--font-mono); font-size: var(--text-caption); }
.rmp-on { color: var(--state-success); font-weight: 600; }
.rmp-off { color: var(--text-disabled); }
.rmp-toggle { padding: 0 6px; border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-caption); }
.rmp-toggle:hover { background: var(--bg-hover); }
.rmp-tag { display: inline-block; padding: 0 4px; background: var(--accent-light); color: var(--accent); border-radius: 2px; font-size: 9px; margin-right: 2px; font-weight: 500; }
.rmp-tag-edit { padding: 0 4px; border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: 10px; }
.rmp-tag-edit:hover { color: var(--accent); }
.rmp-tag-input { padding: 1px 6px; border: 1px solid var(--accent); border-radius: 2px; background: var(--bg-input); color: var(--text-primary); font-size: var(--text-small); width: 120px; }
.rmp-schema { padding: var(--space-sm); background: var(--bg-input); border-radius: var(--radius-sm); margin: var(--space-sm) 0; }
.rmp-schema h5 { font-size: var(--text-small); font-weight: 600; margin-bottom: var(--space-xs); }
.rmp-schema-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); }
.rmp-schema-grid strong { font-size: var(--text-caption); color: var(--text-secondary); }
.rmp-schema-row { font-size: var(--text-caption); padding: 1px 0; }
.rmp-req { color: var(--state-error); font-weight: 600; font-size: 9px; }
.rmp-filters { padding: var(--space-xs) var(--space-sm); border-bottom: 1px solid var(--border-subtle); margin-bottom: var(--space-sm); }
.rmp-filter-section { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; flex-wrap: wrap; }
.rmp-filter-label { font-size: var(--text-caption); color: var(--text-disabled); margin-right: 2px; }
.rmp-filter-chip { padding: 0 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.rmp-filter-chip:hover { background: var(--bg-hover); }
.rmp-filter-chip.active { background: var(--accent-light); border-color: var(--accent); color: var(--accent); }
.rmp-filter-active { font-size: var(--text-caption); color: var(--accent); padding: 2px 0; }
.rmp-filter-clear { border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: var(--text-caption); margin-left: 4px; }
.rmp-filter-clear:hover { color: var(--state-error); }
.rmp-dlg-overlay { position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; }
.rmp-dlg-box { background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-md); min-width: 300px; box-shadow: var(--shadow-menu); }
.rmp-dlg-hd { display: flex; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); font-weight: 600; font-size: var(--text-body); }
.rmp-dlg-close { cursor: pointer; color: var(--text-disabled); }
.rmp-dlg-body { padding: 12px; }
.rmp-dlg-input { width: 100%; padding: 4px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-size: var(--text-body); }
.rmp-dlg-ft { padding: 8px 12px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: flex-end; }
.rmp-dlg-btn { padding: 4px 14px; border: 1px solid var(--accent); border-radius: var(--radius-sm); background: var(--accent); color: #fff; cursor: pointer; font-size: var(--text-small); }
.rmp-dlg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
