<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGraphWorkspaceStore } from '@/stores/graphWorkspaceStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useToastStore } from '@/stores/toastStore'
import { fetchComponentLibrary } from '@/services/api'
import type { ComponentLibraryItem } from '@/types/domains/api'

const workspace = useGraphWorkspaceStore()
const resource = useResourceStore()
const toast = useToastStore()

const searchQuery = ref('')
const searchResults = ref<ComponentLibraryItem[]>([])
const collapsedGroups = ref<Set<string>>(new Set())
const suggestions = ref<ComponentLibraryItem[]>([])
const showSuggestions = ref(false)

function toggleGroup(key: string) {
  if (collapsedGroups.value.has(key)) collapsedGroups.value.delete(key)
  else collapsedGroups.value.add(key)
}

let debounceTimer: ReturnType<typeof setTimeout>
async function doSearch() {
  try {
    const q = searchQuery.value.trim()
    if (q) {
      const r = await fetchComponentLibrary({ query: q })
      searchResults.value = r.items
    } else {
      searchResults.value = []
    }
  } catch {}
}

// Debounced server-side search + instant local suggestions
watch(searchQuery, (q) => {
  clearTimeout(debounceTimer)
  if (!q.trim()) {
    suggestions.value = []; showSuggestions.value = false; searchResults.value = []; return
  }
  // Instant local suggestions from store data
  const lower = q.toLowerCase()
  const allItems = resource.components
  suggestions.value = allItems.filter(i =>
    i.display_name.toLowerCase().includes(lower) ||
    i.resource_key.toLowerCase().includes(lower) ||
    (i.display_name_i18n?.['zh-CN'] || '').includes(lower)
  ).slice(0, 8)
  showSuggestions.value = suggestions.value.length > 0
  // Debounced server search
  debounceTimer = setTimeout(doSearch, 300)
})

function selectSuggestion(item: ComponentLibraryItem) {
  searchQuery.value = displayName(item)
  showSuggestions.value = false
  addNode(item)
}

async function addNode(item: ComponentLibraryItem) {
  const nodeId = await workspace.addNode(item)
  if (nodeId) toast.info('已添加节点', item.display_name)
}
function onDragStart(e: DragEvent, item: ComponentLibraryItem) { e.dataTransfer!.setData('application/json', JSON.stringify(item)); e.dataTransfer!.effectAllowed = 'copy' }

// Data source: store (default) or search results
const items = computed(() => searchQuery.value.trim() ? searchResults.value : resource.components)

const visible = computed(() => items.value.filter(i => i.component_library_visible !== false && !i.compatibility_only))

// P18: Top-level "内置组件 / 用户组件" + secondary category grouping
const builtinItems = computed(() => visible.value.filter(i => i.resource_type === 'builtin_component' || i.category_path?.[0] === 'builtin'))
const userItems = computed(() => visible.value.filter(i => i.resource_type === 'custom_node_graph' || i.category_path?.[0] === 'project'))
const otherItems = computed(() => visible.value.filter(i => !builtinItems.value.includes(i) && !userItems.value.includes(i)))

function makeGroups(list: ComponentLibraryItem[]): [string, ComponentLibraryItem[]][] {
  const map: Record<string, ComponentLibraryItem[]> = {}
  for (const i of list) {
    const key = i.category_group_label || i.category_group_path?.slice(0, 2).join(' / ') || i.category_path?.slice(0, 2).join(' / ') || 'other'
    if (!map[key]) map[key] = []
    map[key].push(i)
  }
  return Object.entries(map)
}

const topGroups = computed(() => {
  const result: { label: string; icon: string; groups: [string, ComponentLibraryItem[]][] }[] = []
  if (builtinItems.value.length) result.push({ label: '内置组件', icon: '📦', groups: makeGroups(builtinItems.value) })
  if (userItems.value.length) result.push({ label: '用户组件', icon: '🔧', groups: makeGroups(userItems.value) })
  if (otherItems.value.length) result.push({ label: '其他', icon: '📋', groups: makeGroups(otherItems.value) })
  return result
})

function taxonomyLabel(t: string | undefined) {
  switch (t) { case 'builtin_component': return '能力'; case 'control_structure': return '流程'; case 'logic_expression': return '逻辑'; case 'user_component': return '用户'; default: return '' }
}

function displayName(c: ComponentLibraryItem) {
  return c.display_name_i18n?.['zh-CN'] || c.display_name
}

function itemTooltip(c: ComponentLibraryItem) {
  const desc = c.description_i18n?.['zh-CN'] || c.description || ''
  return `${c.display_name}\n${c.resource_key}\n${desc}`
}
</script>
<template>
  <div class="clp">
    <div class="clp-search-row">
      <input v-model="searchQuery" class="clp-search" placeholder="搜索组件…" @focus="showSuggestions = suggestions.length > 0" @blur="showSuggestions = false" />
      <div v-if="showSuggestions" class="clp-suggestions">
        <div v-for="s in suggestions" :key="s.resource_id" class="clp-sug-item" @mousedown.prevent="selectSuggestion(s)">
          <span class="clp-sug-name">{{ displayName(s) }}</span>
          <span class="clp-sug-key">{{ s.resource_key }}</span>
        </div>
      </div>
    </div>
    <template v-if="topGroups.length">
      <template v-for="tg in topGroups" :key="tg.label">
        <h4 class="clp-top-hd">{{ tg.icon }} {{ tg.label }}</h4>
        <div class="clp-section" v-for="[group, items] in tg.groups" :key="group">
        <h4 class="clp-group-hd" @click="toggleGroup(group)">
          <span class="clp-arrow">{{ collapsedGroups.has(group) ? '▸' : '▾' }}</span>
          {{ group }} ({{ items.length }})
        </h4>
        <template v-if="!collapsedGroups.has(group)">
          <div v-for="c in items" :key="c.resource_id" class="clp-row"
            :title="itemTooltip(c)"
            draggable="true" @dragstart="onDragStart($event, c)" @click="addNode(c)">
            <span class="clp-name">{{ displayName(c) }}</span>
            <span v-if="c.node_taxonomy" class="clp-tax">{{ taxonomyLabel(c.node_taxonomy) }}</span>
          </div>
        </template>
      </div>
      </template>
    </template>
    <div v-else class="clp-empty">{{ searchQuery ? '无搜索结果' : '暂无组件' }}</div>
  </div>
</template>
<style scoped>
.clp { padding: var(--space-xs); overflow-y: auto; font-size: var(--text-small); height: 100%; }
.clp-empty { padding: var(--space-md); color: var(--text-disabled); }
.clp-search-row { position: relative; padding: var(--space-xs); }
.clp-search { width: 100%; padding: 2px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); font-family: var(--font-ui); font-size: var(--text-small); }
.clp-suggestions { position: absolute; top: 100%; left: var(--space-xs); right: var(--space-xs); z-index: 50; background: var(--bg-panel); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-menu); max-height: 200px; overflow-y: auto; }
.clp-sug-item { display: flex; gap: var(--space-sm); padding: 4px 8px; cursor: pointer; font-size: var(--text-small); }
.clp-sug-item:hover { background: var(--bg-hover); }
.clp-sug-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clp-sug-key { font-family: var(--font-mono); font-size: var(--text-caption); color: var(--text-disabled); }
.clp-top-hd { font-size: var(--text-small); font-weight: 700; color: var(--text-primary); padding: 4px 4px 2px; border-bottom: 2px solid var(--accent); margin-bottom: 4px; margin-top: 6px; }
.clp-section { margin-bottom: var(--space-sm); }
.clp-section h4 { font-size: var(--text-small); font-weight: 600; color: var(--text-secondary); margin-bottom: 2px; padding: 1px 4px; }
.clp-group-hd { cursor: pointer; user-select: none; }
.clp-group-hd:hover { background: var(--bg-hover); border-radius: var(--radius-sm); }
.clp-arrow { font-size: 10px; display: inline-block; width: 12px; }
.clp-row { display: flex; align-items: center; gap: 4px; padding: 2px 6px; color: var(--text-primary); cursor: pointer; border-radius: var(--radius-sm); line-height: 1.4; height: 22px; }
.clp-row:hover { background: var(--bg-hover); }
.clp-row:active { background: var(--bg-selected); }
.clp-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.clp-tax { font-size: 9px; font-weight: 600; color: var(--accent); background: var(--accent-light); padding: 0 3px; border-radius: 2px; white-space: nowrap; flex-shrink: 0; line-height: 1.3; }
</style>
