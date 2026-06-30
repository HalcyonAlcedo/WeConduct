/** WeConduct — Workspace Store
 *  Manages application-level workspace state: project loading, health check, connectivity.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchHealth, fetchSnapshot } from '@/services/api'
import type { HealthResponse, SnapshotResponse } from '@/types/domains/api'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'

export const useWorkspaceStore = defineStore('workspace', () => {
  // --- State ---
  const connectionState = ref<ConnectionState>('disconnected')
  const connectionError = ref<string | null>(null)
  const health = ref<HealthResponse | null>(null)
  const snapshot = ref<SnapshotResponse | null>(null)
  const isInitialized = ref(false)

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

  // --- Actions ---
  async function initialize() {
    if (isInitialized.value) return
    connectionState.value = 'connecting'
    connectionError.value = null

    try {
      const [healthData, snapshotData] = await Promise.all([
        fetchHealth(),
        fetchSnapshot(),
      ])

      health.value = healthData
      snapshot.value = snapshotData
      connectionState.value = 'connected'
      isInitialized.value = true
    } catch (err) {
      connectionState.value = 'error'
      connectionError.value = err instanceof Error ? err.message : 'Failed to connect'
      console.error('[WorkspaceStore] Initialization failed:', err)
    }
  }

  async function refreshSnapshot() {
    try {
      const data = await fetchSnapshot()
      snapshot.value = data
    } catch (err) {
      console.error('[WorkspaceStore] Snapshot refresh failed:', err)
    }
  }

  function reset() {
    connectionState.value = 'disconnected'
    connectionError.value = null
    health.value = null
    snapshot.value = null
    isInitialized.value = false
  }

  return {
    connectionState,
    connectionError,
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
    initialize,
    refreshSnapshot,
    reset,
  }
})
