/** WeConduct — Shared Resource/Component Registry Store
 *  Serves ResourceManagerPanel and ComponentLibraryPanel.
 *  refreshResources() invalidates both views atomically.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchResources, fetchComponentLibrary } from '@/services/api'
import type { ResourceItem, ComponentLibraryItem, Facets } from '@/types/domains/api'

export const useResourceStore = defineStore('resource', () => {
  const resources = ref<ResourceItem[]>([])
  const components = ref<ComponentLibraryItem[]>([])
  const resourceFacets = ref<Facets | null>(null)
  const componentFacets = ref<Facets | null>(null)
  const revision = ref(0)

  async function refreshAll(params?: { tags?: string }) {
    try { const r = await fetchResources(params); resources.value = r.resources; resourceFacets.value = r.facets ?? null } catch {}
    try { const r = await fetchComponentLibrary(); components.value = r.items; componentFacets.value = r.facets ?? null } catch {}
    revision.value++
  }

  function isResourceEnabled(key: string): boolean {
    const state = getResourceEnabledState(key)
    return state !== false
  }

  /** Returns true=enabled, false=disabled, null=not a resource-managed item */
  function getResourceEnabledState(key: string): boolean | null {
    const res = resources.value.find(r => r.resource_key === key || r.resource_id === key)
    if (res) return res.enabled
    const comp = components.value.find(c => c.resource_key === key || c.resource_id === key)
    if (comp) return comp.enabled
    return null
  }

  return { resources, components, resourceFacets, componentFacets, revision, refreshAll, isResourceEnabled, getResourceEnabledState }
})
