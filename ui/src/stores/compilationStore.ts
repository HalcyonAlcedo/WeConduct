/** WeConduct — Compilation Store
 *  Manages the compilation lifecycle: source input, compile trigger, results display.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { postCompile } from '@/services/api'
import { useWorkspaceStore } from './workspaceStore'
import { useToastStore } from './toastStore'
import type { CompileRequestBody, CompileResponse } from '@/types/domains/api'
import type { CompilationStage, StageStatus } from '@/types/domains/compilation'

export type InputState = 'empty' | 'validating' | 'valid' | 'invalid'
export type CompilePhase = 'idle' | 'compiling' | 'completed' | 'failed'

export const useCompilationStore = defineStore('compilation', () => {
  // --- State ---
  const sourceText = ref('')
  const sourceKind = ref('native_flow')
  const entryDocument = ref('untitled.flow')
  const inputState = ref<InputState>('empty')

  const compilePhase = ref<CompilePhase>('idle')
  const compileError = ref<string | null>(null)
  const lastResponse = ref<CompileResponse | null>(null)

  // Simulated stage progress during compilation
  const stages: CompilationStage[] = ['parse', 'bind', 'validate', 'normalize', 'lower', 'emit']
  const stageStatuses = ref<Record<CompilationStage, StageStatus>>({
    parse: 'pending',
    bind: 'pending',
    validate: 'pending',
    normalize: 'pending',
    lower: 'pending',
    emit: 'pending',
  })

  // --- Getters ---
  const canCompile = computed(() =>
    inputState.value !== 'empty' && compilePhase.value !== 'compiling'
  )
  const outcome = computed(() => lastResponse.value?.outcome ?? null)
  const view = computed(() => lastResponse.value?.view ?? null)
  const compileStatus = computed(() => lastResponse.value?.status ?? null)
  const isCompiling = computed(() => compilePhase.value === 'compiling')
  const stageCards = computed(() => view.value?.stage_cards ?? [])
  const diagnosticGroups = computed(() => view.value?.diagnostic_groups ?? [])
  const graphStats = computed(() => view.value?.graph_stats ?? null)

  /** Get all diagnostics for a specific stage (for pipeline coloring) */
  function stageDiagnostics(stage: string) {
    const catalog = outcome.value?.diagnostic_catalog
    if (!catalog) return []
    return catalog.entries.filter(e => e.stage === stage)
  }

  // --- Actions ---
  function setSource(text: string) {
    sourceText.value = text
    if (text.trim().length === 0) {
      inputState.value = 'empty'
    } else {
      inputState.value = 'valid'
    }
    // Reset compilation on new input
    if (compilePhase.value !== 'idle') {
      resetCompilation()
    }
  }

  function setSourceKind(kind: string) {
    sourceKind.value = kind
  }

  function setEntryDocument(doc: string) {
    entryDocument.value = doc
  }

  function clearSource() {
    sourceText.value = ''
    inputState.value = 'empty'
    resetCompilation()
  }

  function resetCompilation() {
    compilePhase.value = 'idle'
    compileError.value = null
    lastResponse.value = null
    for (const stage of stages) {
      stageStatuses.value[stage] = 'pending'
    }
  }

  async function compile() {
    // Ensure fresh source from graph before compiling
    try {
      const { useGraphWorkspaceStore } = await import('./graphWorkspaceStore')
      const graphWs = useGraphWorkspaceStore()
      if (graphWs.graphModel) {
        const needSync = !sourceText.value.trim() || graphWs.syncStatus === 'stale'
        if (needSync) {
          await graphWs.syncSource()
        }
      }
    } catch {}
    if (!canCompile.value) return

    compilePhase.value = 'compiling'
    compileError.value = null

    // Reset stages to pending (real values come from backend response)
    for (const stage of stages) {
      stageStatuses.value[stage] = 'pending'
    }

    const body: CompileRequestBody = {
      source_kind: sourceKind.value,
      entry_document: entryDocument.value,
      source_text: sourceText.value,
    }

    try {
      const response = await postCompile(body)

      // Map stage statuses from the actual backend response
      if (response.view?.stage_cards) {
        for (const card of response.view.stage_cards) {
          const stage = card.stage as CompilationStage
          if (stages.includes(stage)) {
            stageStatuses.value[stage] = card.status === 'failed' ? 'failed' : 'succeeded'
          }
        }
      }

      lastResponse.value = response

      const toast = useToastStore()

      if (response.status === 'succeeded') {
        compilePhase.value = 'completed'
        const stats = response.view.graph_stats
        toast.success('编译成功', `${stats.node_count} 个节点, ${response.view.diagnostic_summary.total_count} 条诊断`)
      } else {
        compilePhase.value = 'failed'
        compileError.value = response.view?.primary_diagnostic?.message ?? 'Compilation failed'
        toast.error('编译失败', compileError.value ?? undefined)
      }

      const workspace = useWorkspaceStore()
      await workspace.refreshSnapshot()

    } catch (err: any) {
      compilePhase.value = 'failed'
      // Consume enhanced error body from backend
      const body: any = err?.body
      if (body) {
        compileError.value = body.message || body.error || 'Compilation failed'
        // Extract stage_cards from error body if present
        const errorView = body.view
        if (errorView?.stage_cards) {
          for (const card of errorView.stage_cards) {
            const stage = card.stage as CompilationStage
            if (stages.includes(stage)) {
              stageStatuses.value[stage] = card.status === 'failed' ? 'failed' : 'succeeded'
            }
          }
        } else {
          // No stage cards in error — mark pending stages as skipped
          for (const stage of stages) {
            if (stageStatuses.value[stage] === 'pending') {
              stageStatuses.value[stage] = 'skipped'
            }
          }
        }
        // Store outcome/diagnostic details from error body for diagnostics display
        if (body.details || body.outcome) {
          lastResponse.value = {
            status: 'failed',
            request: body,
            outcome: body.outcome || {},
            view: errorView || {},
          } as any
        }
      } else {
        compileError.value = err?.message || 'Compilation request failed'
        for (const stage of stages) {
          if (stageStatuses.value[stage] === 'pending') {
            stageStatuses.value[stage] = 'skipped'
          }
        }
      }
      const toast = useToastStore()
      toast.error('编译请求失败', compileError.value ?? undefined)
    }
  }

  // Expose for E2E testing
  if (typeof window !== 'undefined') {
    ;(window as any).__compilationStore = { setSource, compile, clearSource, sourceText, inputState }
  }

  return {
    sourceText,
    sourceKind,
    entryDocument,
    inputState,
    compilePhase,
    compileError,
    lastResponse,
    stageStatuses,
    canCompile,
    outcome,
    view,
    compileStatus,
    isCompiling,
    stageCards,
    diagnosticGroups,
    graphStats,
    stageDiagnostics,
    setSource,
    setSourceKind,
    setEntryDocument,
    clearSource,
    resetCompilation,
    compile,
  }
})
