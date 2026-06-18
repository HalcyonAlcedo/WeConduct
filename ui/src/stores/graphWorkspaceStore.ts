/** WeConduct P3 — Graph Workspace Store
 *  Manages the authoritative graph document flow: GET/PUT /api/workbench/graph
 *  Also owns the graph→source projection sync (global, not panel-scoped).
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { fetchGraphDocument, putGraphDocument, postSourceProjection, fetchNodeDraft } from '@/services/api'
import { useToastStore } from './toastStore'
import type { GraphDocumentResponse, GraphDocumentView, ParameterFieldSchema } from '@/types/domains/api'
import type { GraphModel } from '@/types/domains/graph'

export type GraphLoadState = 'idle' | 'loading' | 'loaded' | 'error'
export type GraphSaveState = 'idle' | 'saving' | 'saved' | 'error' | 'conflict'

export const useGraphWorkspaceStore = defineStore('graphWorkspace', () => {
  const loadState = ref<GraphLoadState>('idle')
  const saveState = ref<GraphSaveState>('idle')
  const loadError = ref<string | null>(null)
  const saveError = ref<string | null>(null)

  const document = ref<GraphDocumentResponse | null>(null)
  const graphModel = ref<GraphModel | null>(null)
  const view = ref<GraphDocumentView | null>(null)

  // Getters
  const saveRevision = computed(() => view.value?.graph_document_save_revision ?? 0)
  const hasGraph = computed(() => !!graphModel.value && (graphModel.value.nodes?.length ?? 0) > 0)
  const isLoaded = computed(() => loadState.value === 'loaded')
  const lastCompileMatches = computed(() => view.value?.last_compile_matches_saved_graph ?? false)

  // Actions
  async function loadGraph() {
    loadState.value = 'loading'
    loadError.value = null
    try {
      const doc = await fetchGraphDocument()
      document.value = doc
      graphModel.value = doc.graph_model
      view.value = doc.view
      loadState.value = 'loaded'
      clearDirty()
      changeRevision.value++ // trigger source-projection auto-sync after load
      // Hydrate parameter schemas for existing nodes
      hydrateSchemasFromGraph()
    } catch (err) {
      loadState.value = 'error'
      loadError.value = err instanceof Error ? err.message : 'Failed to load graph'
    }
  }

  async function saveGraph(model: Record<string, unknown>) {
    if (saveState.value === 'saving') return
    saveState.value = 'saving'
    saveError.value = null
    const toast = useToastStore()
    try {
      const result = await putGraphDocument(model, saveRevision.value)
      // Full state sync: graph model + document + view + changeRevision for source projection
      document.value = { graph_model: result.graph_model, view: result.view }
      graphModel.value = result.graph_model
      view.value = result.view
      changeRevision.value++ // triggers source-projection auto-sync
      saveState.value = 'saved'
      clearDirty()
      toast.success('图稿已保存', `修订号: ${result.view.graph_document_save_revision}`)
    } catch (err: any) {
      if (err?.status === 409 && err?.body?.error === 'graph_revision_conflict') {
        saveState.value = 'conflict'
        saveError.value = '图稿版本冲突：当前图稿已被其他操作修改，请刷新后重新保存。'
        toast.error('图稿版本冲突', '请刷新图稿后重新保存')
      } else {
        saveState.value = 'error'
        saveError.value = err instanceof Error ? err.message : '保存失败'
        toast.error('保存失败', saveError.value ?? undefined)
      }
    }
  }

  const isDirty = ref(false)
  const changeRevision = ref(0)
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])
  const MAX_UNDO = 50

  function markChanged() { isDirty.value = true; changeRevision.value++ }
  function clearDirty() { isDirty.value = false }

  function pushUndo() {
    if (graphModel.value) {
      undoStack.value.push(JSON.stringify(graphModel.value))
      if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
      redoStack.value = []
    }
  }
  function undo() {
    if (!undoStack.value.length) return
    redoStack.value.push(JSON.stringify(graphModel.value!))
    graphModel.value = JSON.parse(undoStack.value.pop()!)
    markChanged()
  }
  function redo() {
    if (!redoStack.value.length) return
    undoStack.value.push(JSON.stringify(graphModel.value!))
    graphModel.value = JSON.parse(redoStack.value.pop()!)
    markChanged()
  }

  /** Add a node via Core node-draft API. Returns new nodeId, or null on failure. */
  async function addNode(item: { resource_key: string; display_name: string; resource_type?: string }, position?: { x: number; y: number }): Promise<string | null> {
    const toast = useToastStore()
    try {
      const draft = await fetchNodeDraft({
        resource_key: item.resource_key,
        x: position?.x,
        y: position?.y,
      })
      pushUndo()
      if (!graphModel.value) {
        graphModel.value = { graph_model_id: 'graph:workspace', compilation_id: null, graph_schema_version: 'graph-v1', nodes: [], edges: [], graph_effective_diagnostic_anchor_refs: [] }
      }
      graphModel.value.nodes.push(draft.node)
      markChanged()
      cacheParameterSchema(item.resource_key, draft.parameter_schema)
      return draft.node.node_id
    } catch (e: any) {
      toast.error('创建节点失败', e?.message || item.resource_key)
      return null
    }
  }

  /** Deep merge: target provides defaults, source provides overrides.
   *  Plain objects recursively merged. Arrays and primitives: source wins.
   *  Draft keys not in source are preserved. */
  function deepMergeConfig(target: Record<string, unknown>, source: Record<string, unknown>): Record<string, unknown> {
    const result = { ...target }
    for (const key of Object.keys(source)) {
      const sv = source[key]
      const tv = target[key]
      if (sv !== null && typeof sv === 'object' && !Array.isArray(sv) &&
          tv !== null && typeof tv === 'object' && !Array.isArray(tv)) {
        result[key] = deepMergeConfig(tv as Record<string, unknown>, sv as Record<string, unknown>)
      } else {
        result[key] = sv
      }
    }
    return result
  }

  /** Paste a copied node via Core draft normalization.
   *  Only inherits user-editable data (display_name, node_config, offset position).
   *  Gets fresh node_id, source_anchor_ref, ports, lowered_kind from Core. */
  async function pasteNode(source: { node_kind?: string; display_name?: string; node_config?: Record<string, unknown>; position?: { x: number; y: number } }): Promise<string | null> {
    if (!source.node_kind) {
      useToastStore().error('无法粘贴', '复制缓存缺少 node_kind')
      return null
    }
    const toast = useToastStore()
    try {
      const draft = await fetchNodeDraft({
        resource_key: source.node_kind,
        x: (source.position?.x || 100) + 40,
        y: (source.position?.y || 80) + 40,
      })
      // Inherit user-editable fields
      if (source.display_name) draft.node.display_name = source.display_name
      if (source.node_config && draft.node.node_config) {
        draft.node.node_config = deepMergeConfig(draft.node.node_config as Record<string, unknown>, source.node_config)
      }
      pushUndo()
      if (!graphModel.value) {
        graphModel.value = { graph_model_id: 'graph:workspace', compilation_id: null, graph_schema_version: 'graph-v1', nodes: [], edges: [], graph_effective_diagnostic_anchor_refs: [] }
      }
      graphModel.value.nodes.push(draft.node)
      markChanged()
      cacheParameterSchema(source.node_kind, draft.parameter_schema)
      return draft.node.node_id
    } catch (e: any) {
      toast.error('粘贴节点失败', e?.message || source.node_kind)
      return null
    }
  }

  /** Remove a node from the local graph model */
  function removeNode(nodeId: string) {
    pushUndo()
    if (!graphModel.value) return
    graphModel.value.nodes = graphModel.value.nodes.filter(n => n.node_id !== nodeId)
    graphModel.value.edges = graphModel.value.edges.filter(e => e.from_node_id !== nodeId && e.to_node_id !== nodeId)
    markChanged()
  }

  function updateNode(nodeId: string, patch: Partial<{ display_name: string; node_config: Record<string, unknown> }>) {
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    const node = gm.nodes.find(n => n.node_id === nodeId); if (!node) return
    if (patch.display_name !== undefined) node.display_name = patch.display_name
    if (patch.node_config !== undefined) node.node_config = patch.node_config
    markChanged()
  }
  function updateNodePosition(nodeId: string, pos: { x: number; y: number }) {
    const gm = graphModel.value; if (!gm) return
    const node = gm.nodes.find(n => n.node_id === nodeId); if (!node) return
    node.position = pos; markChanged()
  }
  function addEdge(edge: { edge_id: string; relation_layer: string; from_node_id: string; to_node_id: string; from_port_id?: string; to_port_id?: string }) {
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    gm.edges.push({ edge_id: edge.edge_id, relation_layer: edge.relation_layer as any, from_node_id: edge.from_node_id, to_node_id: edge.to_node_id, from_port_id: edge.from_port_id ?? null, to_port_id: edge.to_port_id ?? null })
    markChanged()
  }
  function removeEdge(edgeId: string) {
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    gm.edges = gm.edges.filter(e => e.edge_id !== edgeId); markChanged()
  }
  function updateEdgeRelation(edgeId: string, layer: string) {
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    const edge = gm.edges.find(e => e.edge_id === edgeId); if (!edge) return
    edge.relation_layer = layer as any; markChanged()
  }

  function reset() {
    loadState.value = 'idle'; saveState.value = 'idle'; loadError.value = null; saveError.value = null
    document.value = null; graphModel.value = null; view.value = null
    syncStatus.value = 'idle'; syncError.value = null
    clearDirty()
  }

  // ---- Parameter schema cache (from node drafts) ----
  const parameterSchemas = ref<Record<string, Record<string, ParameterFieldSchema>>>({})

  function cacheParameterSchema(resourceKey: string, schema?: Record<string, ParameterFieldSchema>) {
    if (schema) parameterSchemas.value[resourceKey] = { ...parameterSchemas.value[resourceKey], ...schema }
  }

  /** Hydrate parameter_schema cache for existing graph nodes (e.g. after loadGraph / open project) */
  async function hydrateSchemasFromGraph() {
    const gm = graphModel.value
    if (!gm) return
    const kinds = [...new Set(gm.nodes.map(n => n.node_kind).filter(Boolean))] as string[]
    for (const kind of kinds) {
      if (parameterSchemas.value[kind]) continue // already cached
      try {
        const draft = await fetchNodeDraft({ resource_key: kind })
        cacheParameterSchema(kind, draft.parameter_schema)
      } catch { /* skip failed hydration */ }
    }
  }

  // ---- Graph → Source Projection Sync (global, always active) ----
  const syncStatus = ref<'idle' | 'syncing' | 'synced' | 'failed' | 'stale'>('idle')
  const syncError = ref<string | null>(null)
  let syncTimer: ReturnType<typeof setTimeout> | null = null

  async function syncSource() {
    if (!graphModel.value) return
    syncStatus.value = 'syncing'
    syncError.value = null
    try {
      const r = await postSourceProjection({
        target_source_kind: 'native_flow',
        graph_document: graphModel.value as any,
      })
      if (r.source_text) {
        // Dynamically import to avoid circular dependency
        const { useCompilationStore } = await import('./compilationStore')
        const comp = useCompilationStore()
        comp.setSource(r.source_text)
        // Sync source_kind + entry_document from backend (may have fallen back)
        if (r.source_kind) comp.setSourceKind(r.source_kind)
        if (r.entry_document) comp.setEntryDocument(r.entry_document)
        syncStatus.value = 'synced'
      } else {
        syncStatus.value = 'stale'
      }
    } catch (e: any) {
      syncStatus.value = 'failed'
      syncError.value = e?.message || '投影失败'
    }
  }

  function scheduleAutoSync() {
    if (syncTimer) clearTimeout(syncTimer)
    syncStatus.value = 'stale'
    syncTimer = setTimeout(() => syncSource(), 800)
  }

  // Global watcher: persists regardless of panel lifecycle
  watch(() => changeRevision.value, () => {
    if (graphModel.value) scheduleAutoSync()
  }, { immediate: false })

  return {
    loadState, saveState, loadError, saveError,
    document, graphModel, view, isDirty, changeRevision,
    saveRevision, hasGraph, isLoaded, lastCompileMatches,
    loadGraph, saveGraph, addNode, pasteNode, removeNode, updateNode,
    updateNodePosition, addEdge, removeEdge, updateEdgeRelation, pushUndo, undo, redo, reset,
    syncStatus, syncError, syncSource, scheduleAutoSync,
    parameterSchemas, cacheParameterSchema,
  }
})
