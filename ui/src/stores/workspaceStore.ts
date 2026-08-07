/** WeConduct — Workspace Store
 *  Manages application-level workspace state: project loading, health check, connectivity.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { consumeSse, fetchHealth, fetchSnapshot, type SseEvent } from '@/services/api'
import type { HealthResponse, SnapshotResponse } from '@/types/domains/api'
import { useProjectDiagnosticsStore } from './projectDiagnosticsStore'
import { useGraphWorkspaceStore } from './graphWorkspaceStore'
import { useRuntimeStore } from './runtimeStore'
import { useToastStore } from './toastStore'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'

export const useWorkspaceStore = defineStore('workspace', () => {
  // --- State ---
  const connectionState = ref<ConnectionState>('disconnected')
  const connectionError = ref<string | null>(null)
  /** Raw error object from the last failed initialize(), for startup diagnostics. */
  const initError = ref<unknown>(null)
  const health = ref<HealthResponse | null>(null)
  const snapshot = ref<SnapshotResponse | null>(null)
  const isInitialized = ref(false)
  const workbenchEventConnected = ref(false)
  const workbenchEventError = ref<string | null>(null)
  const workbenchEventLastId = ref<number | null>(null)
  let workbenchEventController: AbortController | null = null
  let workbenchEventGeneration = 0
  let workbenchEventReconnectTimer: ReturnType<typeof setTimeout> | null = null

  // --- Getters ---
  const isConnected = computed(() => connectionState.value === 'connected')
  const projectName = computed(() => snapshot.value?.project?.project_name ?? null)
  const projectId = computed(() => snapshot.value?.project?.project_id ?? null)
  const projectStatus = computed(() => snapshot.value?.project?.project_status ?? null)
  const lastCompileRequestSequence = computed(() => snapshot.value?.project?.last_compile_request_sequence ?? null)
  const compilerAvailable = computed(() => snapshot.value?.capabilities?.compiler_available ?? false)
  const runtimeAvailable = computed(() => snapshot.value?.capabilities?.runtime_available ?? false)
  const debugAvailable = computed(() => snapshot.value?.capabilities?.debug_available ?? false)
  const availableSourceKinds = computed(() => snapshot.value?.compiler?.available_source_kinds ?? [])
  const defaultSourceKind = computed(() => snapshot.value?.compiler?.default_source_kind ?? 'native_flow')
  const supportedStages = computed(() => snapshot.value?.compiler?.supported_stage_names ?? [])
  const sourceTemplates = computed(() => snapshot.value?.compiler?.source_templates ?? null)
  const lastCompile = computed(() => snapshot.value?.last_compile ?? null)
  const lastCompileTime = computed(() => snapshot.value?.last_compile?.compiled_at ?? null)
  const compileHistory = computed(() => snapshot.value?.compile_history ?? [])
  const uiHosting = computed(() => snapshot.value?.ui_hosting ?? null)
  const isUiHosted = computed(() => snapshot.value?.ui_hosting?.ui_hosted ?? false)
  const isLimitedBrowser = computed(() => snapshot.value?.ui_hosting?.ui_mode === 'limited_browser')
  const healthCapabilities = computed(() => health.value?.capabilities ?? null)
  const compileCounter = computed(() => snapshot.value?.workbench?.compile_counter ?? 0)
  // P12: project storage model upgrade fields
  const projectFileSchemaVersion = computed(() => snapshot.value?.project?.project_file_schema_version ?? null)
  const mainGraphPath = computed(() => snapshot.value?.project?.main_graph_path ?? null)
  const projectResourcesIndexPath = computed(() => snapshot.value?.project?.project_resources_index_path ?? null)
  const resourceOverridesPath = computed(() => snapshot.value?.project?.resource_overrides_path ?? null)
  const isDirectoryProject = computed(() => !!snapshot.value?.project?.main_graph_path)

  function applySnapshot(data: SnapshotResponse) {
    // 工作台事件首帧没有桌面启动时附带的 ui_hosting 元数据，保留本地已知值。
    snapshot.value = {
      ...snapshot.value,
      ...data,
      ui_hosting: data.ui_hosting ?? snapshot.value?.ui_hosting,
    } as SnapshotResponse
    useProjectDiagnosticsStore().switchProject({
      project_id: data.project?.project_id ?? null,
      project_name: data.project?.project_name ?? null,
    })
  }

  async function reconcileSnapshot(data: SnapshotResponse, previous: SnapshotResponse | null) {
    const graphWorkspace = useGraphWorkspaceStore()
    const previousProjectId = previous?.project?.project_id ?? null
    const nextProjectId = data.project?.project_id ?? null
    const projectChanged = previousProjectId !== nextProjectId
    const nextRevision = (data.graph_workspace as Record<string, unknown> | undefined)
      ?.graph_document_save_revision
    const revisionChanged = (
      typeof nextRevision === 'number'
      && Number.isInteger(nextRevision)
      && graphWorkspace.isLoaded
      && graphWorkspace.saveRevision !== nextRevision
    )
    if (data.project?.loaded && (projectChanged || revisionChanged)) {
      const documentId = projectChanged ? undefined : graphWorkspace.currentDocumentId
      // workbench.snapshot only carries the main graph revision.  A dirty
      // custom graph must not inherit a main-graph conflict; its own
      // workspace.graph_changed event carries the document_id and is the
      // authoritative conflict signal for that document.
      if (graphWorkspace.isDirty) {
        if (graphWorkspace.currentDocumentId === undefined) {
          const marked = graphWorkspace.markExternalGraphConflict({
            documentId,
            baseRevision: projectChanged ? null : graphWorkspace.saveRevision,
            remoteRevision: typeof nextRevision === 'number' ? nextRevision : null,
          })
          if (marked) {
            useToastStore().warning('图稿已被外部修改', '当前图稿有未保存修改，请处理冲突后再刷新')
          }
        }
      } else {
        await graphWorkspace.loadGraph(documentId, { forceRefresh: true })
      }
    }
    await useRuntimeStore().recoverActiveSession()
  }

  async function handleWorkbenchEvent(event: SseEvent) {
    if (event.id) {
      const parsedEventId = Number(event.id)
      if (Number.isSafeInteger(parsedEventId) && parsedEventId >= 0) {
        workbenchEventLastId.value = parsedEventId
      }
    }
    workbenchEventConnected.value = true
    workbenchEventError.value = null
    if (!event.data) return

    let payload: Record<string, unknown>
    try {
      const parsed = JSON.parse(event.data)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return
      payload = parsed as Record<string, unknown>
    } catch {
      return
    }

    if (event.event === 'workbench.snapshot') {
      const previous = snapshot.value
      applySnapshot(payload as unknown as SnapshotResponse)
      await reconcileSnapshot(payload as unknown as SnapshotResponse, previous)
      return
    }
    if (event.event === 'workspace.project_changed') {
      await refreshSnapshot()
      return
    }
    if (event.event === 'workspace.graph_changed') {
      const graphWorkspace = useGraphWorkspaceStore()
      const rawDocumentId = payload.document_id
      const documentId = rawDocumentId === 'graph:workspace' || typeof rawDocumentId !== 'string'
        ? undefined
        : rawDocumentId
      if (graphWorkspace.currentDocumentId !== documentId) {
        await graphWorkspace.refreshGraphDocuments()
        return
      }
      const revision = typeof payload.revision === 'number' ? payload.revision : null
      if (graphWorkspace.isDirty) {
        const marked = graphWorkspace.markExternalGraphConflict({
          documentId,
          baseRevision: graphWorkspace.saveRevision,
          remoteRevision: revision,
        })
        if (marked) {
          useToastStore().warning('图稿已被外部修改', '当前图稿有未保存修改，请处理冲突后再刷新')
        }
        return
      }
      await graphWorkspace.loadGraph(documentId, { forceRefresh: true })
      return
    }
    if (event.event === 'runtime.session_changed') {
      await useRuntimeStore().handleWorkbenchSessionEvent(payload)
    }
  }

  function stopEventStream() {
    workbenchEventGeneration += 1
    if (workbenchEventReconnectTimer) clearTimeout(workbenchEventReconnectTimer)
    workbenchEventReconnectTimer = null
    workbenchEventController?.abort()
    workbenchEventController = null
    workbenchEventConnected.value = false
  }

  function startEventStream() {
    stopEventStream()
    const generation = workbenchEventGeneration
    const controller = new AbortController()
    workbenchEventController = controller

    const run = async () => {
      while (generation === workbenchEventGeneration && !controller.signal.aborted) {
        try {
          await consumeSse('/workbench/events', {
            lastEventId: workbenchEventLastId.value,
            signal: controller.signal,
            onEvent: handleWorkbenchEvent,
          })
          if (controller.signal.aborted || generation !== workbenchEventGeneration) return
          await refreshSnapshot()
        } catch (error) {
          if (controller.signal.aborted || generation !== workbenchEventGeneration) return
          const apiError = error as { status?: number; body?: { error?: unknown } }
          let cursorRecovered = false
          if (apiError?.status === 409 && apiError.body?.error === 'workbench.event_cursor_expired') {
            workbenchEventLastId.value = null
            await refreshSnapshot()
            cursorRecovered = true
          }
          workbenchEventConnected.value = false
          workbenchEventError.value = cursorRecovered
            ? null
            : error instanceof Error ? error.message : '工作台事件流连接失败'
        }
        if (controller.signal.aborted || generation !== workbenchEventGeneration) return
        await new Promise<void>((resolve) => {
          workbenchEventReconnectTimer = setTimeout(() => {
            workbenchEventReconnectTimer = null
            resolve()
          }, 500)
        })
      }
    }
    void run()
  }

  // --- Actions ---
  async function initialize() {
    if (isInitialized.value) return
    connectionState.value = 'connecting'
    connectionError.value = null
    initError.value = null

    try {
      const [healthData, snapshotData] = await Promise.all([
        fetchHealth(),
        fetchSnapshot(),
      ])

      health.value = healthData
      applySnapshot(snapshotData)
      connectionState.value = 'connected'
      isInitialized.value = true
    } catch (err) {
      connectionState.value = 'error'
      connectionError.value = err instanceof Error ? err.message : 'Failed to connect'
      initError.value = err
      console.error('[WorkspaceStore] Initialization failed:', err)
      useProjectDiagnosticsStore().ingestApiError(err, { source: 'workspace', operation: 'workspace.initialize' })
    }
  }

  async function refreshSnapshot() {
    try {
      const data = await fetchSnapshot()
      const previous = snapshot.value
      applySnapshot(data)
      await reconcileSnapshot(data, previous)
    } catch (err) {
      console.error('[WorkspaceStore] Snapshot refresh failed:', err)
      useProjectDiagnosticsStore().ingestApiError(err, { source: 'workspace', operation: 'workspace.refresh_snapshot' })
    }
  }

  function reset() {
    stopEventStream()
    connectionState.value = 'disconnected'
    connectionError.value = null
    initError.value = null
    health.value = null
    snapshot.value = null
    workbenchEventLastId.value = null
    workbenchEventError.value = null
    isInitialized.value = false
    useProjectDiagnosticsStore().switchProject()
  }

  return {
    connectionState,
    connectionError,
    initError,
    health,
    snapshot,
    isInitialized,
    isConnected,
    projectName,
    projectId,
    projectStatus,
    lastCompileRequestSequence,
    compilerAvailable,
    runtimeAvailable,
    debugAvailable,
    availableSourceKinds,
    defaultSourceKind,
    supportedStages,
    sourceTemplates,
    lastCompile,
    lastCompileTime,
    compileHistory,
    uiHosting,
    isUiHosted,
    isLimitedBrowser,
    healthCapabilities,
    compileCounter,
    projectFileSchemaVersion, mainGraphPath, projectResourcesIndexPath, resourceOverridesPath, isDirectoryProject,
    workbenchEventConnected, workbenchEventError, workbenchEventLastId,
    initialize,
    refreshSnapshot,
    handleWorkbenchEvent,
    startEventStream,
    stopEventStream,
    reset,
  }
})
