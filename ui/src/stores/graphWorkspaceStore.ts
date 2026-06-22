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
  /** P18: current active document_id. null/undefined = main graph. "custom_node_graph:<id>" = custom component. */
  const currentDocumentId = ref<string | undefined>(undefined)
  const isCustomComponentGraph = computed(() => !!currentDocumentId.value)
  /** P18: graph document list (main + custom components) */
  const graphDocuments = ref<{ document_id: string; document_role: string; display_name?: string; resource_id?: string }[]>([])

  /** P18: Per-document draft cache. Keyed by document_id (undefined = main graph). */
  const draftsByDocumentId = ref<Map<string | undefined, {
    document: GraphDocumentResponse | null
    graphModel: GraphModel | null
    view: GraphDocumentView | null
    isDirty: boolean
    changeRevision: number
    undoStack: string[]
    redoStack: string[]
  }>>(new Map())

  function saveCurrentDraft() {
    const key = currentDocumentId.value
    draftsByDocumentId.value.set(key, {
      document: JSON.parse(JSON.stringify(document.value)),
      graphModel: JSON.parse(JSON.stringify(graphModel.value)),
      view: JSON.parse(JSON.stringify(view.value)),
      isDirty: isDirty.value,
      changeRevision: changeRevision.value,
      undoStack: [...undoStack.value],
      redoStack: [...redoStack.value],
    })
  }

  function restoreDraft(docId: string | undefined): boolean {
    const draft = draftsByDocumentId.value.get(docId)
    if (!draft) return false
    document.value = draft.document
    graphModel.value = draft.graphModel
    view.value = draft.view
    isDirty.value = draft.isDirty
    changeRevision.value = draft.changeRevision
    undoStack.value = draft.undoStack
    redoStack.value = draft.redoStack
    currentDocumentId.value = docId
    loadState.value = 'loaded'
    return true
  }

  function clearAllDrafts() {
    draftsByDocumentId.value.clear()
    staleDrafts.value.clear()
  }

  /** P18: Drafts known to be stale (e.g. main graph after subgraph schema changed) */
  const staleDrafts = ref<Set<string | undefined>>(new Set())

  function invalidateMainGraphDrafts() {
    // Invalidate main graph draft + any graph that might reference changed resources
    staleDrafts.value.add(undefined) // main graph
    for (const key of draftsByDocumentId.value.keys()) {
      if (typeof key === 'string' && key.startsWith('custom_node_graph:')) continue
      staleDrafts.value.add(key)
    }
  }
  async function refreshGraphDocuments() {
    try {
      const { fetchProjectDocuments } = await import('@/services/api')
      const r = await fetchProjectDocuments()
      graphDocuments.value = r.documents || []
    } catch { graphDocuments.value = [] }
  }

  // Getters
  const saveRevision = computed(() => view.value?.graph_document_save_revision ?? 0)
  const hasGraph = computed(() => !!graphModel.value && (graphModel.value.nodes?.length ?? 0) > 0)
  const isLoaded = computed(() => loadState.value === 'loaded')
  const lastCompileMatches = computed(() => view.value?.last_compile_matches_saved_graph ?? false)
  /** Graph is editable (false when .wcrun loaded or source_of_truth === wcrun_package) */
  const isGraphEditable = computed(() => view.value?.is_editable !== false)

  // Actions
  async function loadGraph(documentId?: string, options?: { forceRefresh?: boolean }) {
    const isSwitching = currentDocumentId.value !== documentId
    // Save current graph state to draft cache before switching documents
    if (loadState.value === 'loaded' && isSwitching) {
      saveCurrentDraft()
    }
    // Skip stale drafts (e.g. main graph after subgraph schema changed)
    const isStale = staleDrafts.value.has(documentId)
    if (isStale) staleDrafts.value.delete(documentId)
    // Try restoring from local draft only when switching documents (not force-refreshing) and not stale
    if (!options?.forceRefresh && !isStale && restoreDraft(documentId)) {
      changeRevision.value++ // trigger source-projection
      hydrateSchemasFromGraph()
      return
    }
    // Fetch from API
    loadState.value = 'loading'
    loadError.value = null
    try {
      const doc = await fetchGraphDocument(documentId)
      document.value = doc
      graphModel.value = doc.graph_model
      view.value = doc.view
      currentDocumentId.value = documentId || undefined
      loadState.value = 'loaded'
      clearDirty()
      changeRevision.value++ // trigger source-projection auto-sync after load
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
      const result = await putGraphDocument(model, saveRevision.value, currentDocumentId.value)
      // Full state sync: graph model + document + view + changeRevision for source projection
      document.value = { graph_model: result.graph_model, view: result.view }
      graphModel.value = result.graph_model
      view.value = result.view
      changeRevision.value++ // triggers source-projection auto-sync
      saveState.value = 'saved'
      clearDirty()
      // Saving subgraph invalidates main graph drafts (schema may have changed)
      if (currentDocumentId.value) invalidateMainGraphDrafts()
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

  /** P18: Check boundary/singleton placement rules. Returns error message or null if allowed. */
  function canPlaceNode(resourceKey: string): string | null {
    const isMainGraph = !currentDocumentId.value
    const nodes = graphModel.value?.nodes || []
    const hasFlowStart = nodes.some(n => n.node_kind === 'flow.start')
    const hasCompInput = nodes.some(n => n.node_kind === 'component.input')
    const hasCompOutput = nodes.some(n => n.node_kind === 'component.output')
    // Subgraph boundary rules
    if (!isMainGraph) {
      if (resourceKey === 'flow.start') return '子图中不能放置 flow.start'
      if (resourceKey === 'component.input' && hasCompInput) return '子图中已有 component.input'
      if (resourceKey === 'component.output' && hasCompOutput) return '子图中已有 component.output'
      return null
    }
    // Main graph boundary rules
    if (resourceKey === 'component.input') return 'component.input 只能在子图中使用'
    if (resourceKey === 'component.output') return 'component.output 只能在子图中使用'
    if (resourceKey === 'flow.start' && hasFlowStart) return '主图中已有 flow.start'
    return null
  }

  /** Add a node via Core node-draft API. Returns new nodeId, or null on failure.
   *  If no position given, places node at current viewport center. */
  async function addNode(item: { resource_key: string; display_name: string; resource_type?: string }, position?: { x: number; y: number }): Promise<string | null> {
    if (!isGraphEditable.value) return null
    const blockReason = canPlaceNode(item.resource_key)
    if (blockReason) { useToastStore().info('无法放置', blockReason); return null }
    const toast = useToastStore()
    try {
      // Use viewport center when no explicit position (click, not drag)
      const x = position?.x ?? viewport.value.x
      const y = position?.y ?? viewport.value.y
      const draft = await fetchNodeDraft({
        resource_key: item.resource_key,
        x,
        y,
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
    if (!isGraphEditable.value) return null
    if (!source.node_kind) {
      useToastStore().error('无法粘贴', '复制缓存缺少 node_kind')
      return null
    }
    const blockReason = canPlaceNode(source.node_kind)
    if (blockReason) { useToastStore().info('无法放置', blockReason); return null }
    const toast = useToastStore()
    try {
      // Paste at current viewport center (not source offset)
      const px = viewport.value.x + (pasteCounter++ * 30) % 300
      const py = viewport.value.y + (pasteCounter * 20) % 200
      const draft = await fetchNodeDraft({
        resource_key: source.node_kind,
        x: Math.round(px),
        y: Math.round(py),
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
    if (!isGraphEditable.value) return
    pushUndo()
    if (!graphModel.value) return
    graphModel.value.nodes = graphModel.value.nodes.filter(n => n.node_id !== nodeId)
    graphModel.value.edges = graphModel.value.edges.filter(e => e.from_node_id !== nodeId && e.to_node_id !== nodeId)
    markChanged()
  }

  function updateNode(nodeId: string, patch: Partial<{ display_name: string; node_config: Record<string, unknown> }>) {
    if (!isGraphEditable.value) return
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
    if (!isGraphEditable.value) return
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    gm.edges.push({ edge_id: edge.edge_id, relation_layer: edge.relation_layer as any, from_node_id: edge.from_node_id, to_node_id: edge.to_node_id, from_port_id: edge.from_port_id ?? null, to_port_id: edge.to_port_id ?? null })
    markChanged()
  }
  function removeEdge(edgeId: string) {
    if (!isGraphEditable.value) return
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    gm.edges = gm.edges.filter(e => e.edge_id !== edgeId); markChanged()
  }
  function updateEdgeRelation(edgeId: string, layer: string) {
    if (!isGraphEditable.value) return
    pushUndo()
    const gm = graphModel.value; if (!gm) return
    const edge = gm.edges.find(e => e.edge_id === edgeId); if (!edge) return
    edge.relation_layer = layer as any; markChanged()
  }

  function reset() {
    loadState.value = 'idle'; saveState.value = 'idle'; loadError.value = null; saveError.value = null
    document.value = null; graphModel.value = null; view.value = null; currentDocumentId.value = undefined
    graphDocuments.value = []
    clearAllDrafts()
    syncStatus.value = 'idle'; syncError.value = null
    clearDirty()
  }

  // ---- Parameter schema cache (from node drafts) ----
  const parameterSchemas = ref<Record<string, Record<string, ParameterFieldSchema>>>({})

  // ---- Current viewport (for placing new nodes at view center) ----
  const viewport = ref<{ x: number; y: number; zoom: number }>({ x: 0, y: 0, zoom: 1 })
  let pasteCounter = 0
  function updateViewport(v: { x: number; y: number; zoom: number }) { viewport.value = v }

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
    saveRevision, hasGraph, isLoaded, lastCompileMatches, isGraphEditable,
    currentDocumentId, isCustomComponentGraph, graphDocuments, refreshGraphDocuments,
    draftsByDocumentId, saveCurrentDraft, restoreDraft, clearAllDrafts, invalidateMainGraphDrafts,
    loadGraph, saveGraph, addNode, pasteNode, removeNode, updateNode,
    updateNodePosition, addEdge, removeEdge, updateEdgeRelation, pushUndo, undo, redo, reset,
    syncStatus, syncError, syncSource, scheduleAutoSync,
    parameterSchemas, cacheParameterSchema,
    viewport, updateViewport,
  }
})
