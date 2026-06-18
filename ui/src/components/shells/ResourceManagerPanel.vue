<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { postResourceEnabled, postResourceTags } from '@/services/api'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import type { ResourceItem } from '@/types/domains/api'

const resource = useResourceStore()
const toast = useToastStore()
const loading = ref(true)
const expandedRes = ref<string | null>(null)
const filterCategory = ref<string[] | null>(null)
const filterTag = ref('')

onMounted(async () => { await resource.refreshAll(); loading.value = false })

function showCatPath(path: string[]) { return path.join(' / ') }
function selectCategory(path: string[]) { filterCategory.value = filterCategory.value?.[0] === path[0] ? null : path }
function selectTag(tag: string) {
  filterTag.value = filterTag.value === tag ? '' : tag
  resource.refreshAll(filterTag.value ? { tags: filterTag.value } : undefined)
}

const filteredResources = computed(() => {
  let list = resource.resources.filter(r => r.resource_manager_visible !== false)
  if (filterCategory.value) {
    const cat = filterCategory.value.join('/')
    list = list.filter(r => (r.category_group_path || r.category_path || []).join('/') === cat)
  }
  if (filterTag.value) {
    list = list.filter(r => r.tags?.includes(filterTag.value))
  }
  return list
})

function schemaFields(schema: Record<string, any> | undefined): { key: string; type: string; required: boolean }[] {
  if (!schema) return []
  return Object.entries(schema).map(([k, v]) => ({
    key: k, type: (v as any)?.type || 'string', required: !!(v as any)?.required,
  }))
}

async function toggleEnabled(r: ResourceItem) {
  try {
    const updated = await postResourceEnabled(r.resource_id, !r.enabled)
    await resource.refreshAll()
    toast.info('已更新', updated.resource.display_name)
  } catch (e: any) { toast.error('操作失败', e?.message) }
}
const editTagsId = ref<string | null>(null)
const editTagsInput = ref('')
function startTagEdit(r: ResourceItem) { editTagsId.value = r.resource_id; editTagsInput.value = (r.tags || []).join(', ') }
async function saveTags(r: ResourceItem) {
  const tags = editTagsInput.value.split(',').map(t => t.trim()).filter(Boolean)
  try { await postResourceTags(r.resource_id, tags); await resource.refreshAll(); editTagsId.value = null; toast.info('标签已更新') }
  catch (e: any) { toast.error('更新失败', e?.message) }
}
</script>
<template>
  <div class="rmp">
    <div class="rmp-toolbar">
      <button class="rmp-btn rmp-btn-new" disabled title="Core 待接入">新建</button>
      <button class="rmp-btn" disabled title="Core 待接入">编辑</button>
      <button class="rmp-btn" disabled title="Core 待接入">删除</button>
      <span class="rmp-sep"></span>
      <span class="rmp-label">导入/导出：请通过 Core CLI 操作</span>
    </div>
    <div v-if="loading" class="rmp-load">加载中…</div>
    <template v-else>
      <!-- Facets filters -->
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
      <table v-if="filteredResources.length" class="rmp-table">
      <thead><tr><th>名称</th><th>类型</th><th>标签</th><th>来源</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="r in filteredResources" :key="r.resource_id">
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
          <td>{{ r.origin ?? 'builtin' }}</td>
          <td><span :class="r.enabled ? 'rmp-on' : 'rmp-off'">{{ r.enabled ? '启用' : '禁用' }}</span></td>
          <td>
            <button class="rmp-toggle" @click="toggleEnabled(r)">{{ r.enabled ? '禁用' : '启用' }}</button>
            <button v-if="r.resource_type === 'subgraph_resource'" class="rmp-toggle" style="margin-left:4px" @click="expandedRes = expandedRes === r.resource_id ? null : r.resource_id">Schema</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="expandedRes" class="rmp-schema">
      <h5>{{ resource.resources.find(r => r.resource_id === expandedRes)?.display_name }} — Schema</h5>
      <div class="rmp-schema-grid">
        <div><strong>Input Schema</strong>
          <div v-if="!(resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema || !Object.keys((resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema || {}).length">未声明</div>
          <div v-for="f in schemaFields((resource.resources.find(r => r.resource_id === expandedRes) as any)?.input_schema)" :key="f.key" class="rmp-schema-row">
            {{ f.key }} <span class="rmp-mono">{{ f.type }}</span> <span v-if="f.required" class="rmp-req">必填</span>
          </div>
        </div>
        <div><strong>Output Schema</strong>
          <div v-if="!(resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema || !Object.keys((resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema || {}).length">未声明</div>
          <div v-for="f in schemaFields((resource.resources.find(r => r.resource_id === expandedRes) as any)?.output_schema)" :key="f.key" class="rmp-schema-row">
            {{ f.key }} <span class="rmp-mono">{{ f.type }}</span>
          </div>
        </div>
      </div>
    </div>
    </template>
    <div v-if="!loading && !filteredResources.length && !expandedRes" class="rmp-empty">暂无资源</div>
  </div>
</template>
<style scoped>
.rmp { padding: var(--space-sm); overflow-y: auto; font-size: var(--text-small); height: 100%; }
.rmp-toolbar { display: flex; gap: var(--space-xs); margin-bottom: var(--space-sm); align-items: center; }
.rmp-btn { padding: 2px 10px; border: 1px solid var(--border-default); background: var(--bg-panel); color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); font-size: var(--text-small); font-family: var(--font-ui); }
.rmp-btn:hover:not(:disabled) { background: var(--bg-hover); }
.rmp-btn:disabled { opacity: 0.5; cursor: not-allowed; color: var(--text-disabled); }
.rmp-btn-new:disabled { border-style: dashed; }
.rmp-sep { width: 1px; height: 18px; background: var(--border-default); margin: 0 var(--space-xs); }
.rmp-label { font-size: var(--text-caption); color: var(--text-disabled); }
.rmp-load, .rmp-empty { padding: var(--space-md); color: var(--text-disabled); }
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
.rmp-schema { padding: var(--space-sm); background: var(--bg-input); border-radius: var(--radius-sm); margin-bottom: var(--space-sm); }
.rmp-schema h5 { font-size: var(--text-small); font-weight: 600; margin-bottom: var(--space-xs); }
.rmp-schema-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); }
.rmp-schema-grid strong { font-size: var(--text-caption); color: var(--text-secondary); }
.rmp-schema-row { font-size: var(--text-caption); padding: 1px 0; }
.rmp-req { color: var(--state-error); font-weight: 600; font-size: 9px; }
.rmp-filters { padding: var(--space-xs) var(--space-sm); border-bottom: 1px solid var(--border-subtle); }
.rmp-filter-section { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; flex-wrap: wrap; }
.rmp-filter-label { font-size: var(--text-caption); color: var(--text-disabled); margin-right: 2px; }
.rmp-filter-chip { padding: 0 6px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-panel); color: var(--text-secondary); cursor: pointer; font-size: var(--text-caption); font-family: var(--font-ui); }
.rmp-filter-chip:hover { background: var(--bg-hover); }
.rmp-filter-chip.active { background: var(--accent-light); border-color: var(--accent); color: var(--accent); }
.rmp-filter-active { font-size: var(--text-caption); color: var(--accent); padding: 2px 0; }
.rmp-filter-clear { border: none; background: transparent; color: var(--text-disabled); cursor: pointer; font-size: var(--text-caption); margin-left: 4px; }
.rmp-filter-clear:hover { color: var(--state-error); }
</style>
