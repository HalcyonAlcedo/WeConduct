/** WeConduct — Compilation Types
 *  Mirror of Python contracts at src/weconduct/contracts/compilation.py
 *  DO NOT modify without coordinating through docs/ui-collab/inbox-to-core/requests/
 */

export type CompilationStage = 'parse' | 'bind' | 'validate' | 'normalize' | 'lower' | 'emit'

export type StageStatus = 'pending' | 'succeeded' | 'failed' | 'skipped'

export type SourceKind = 'native_flow' | 'webcontrol_main_flow'

export type CompileStatus = 'succeeded' | 'failed' | 'unsupported'

export interface CompilationSource {
  kind: SourceKind
  entry_document: string
  source_text: string
}

export interface CompilationOptions {
  stop_on_fatal: boolean
}

export interface CompilationRequest {
  compilation_id: string
  source: CompilationSource
  options: CompilationOptions
}

export interface StageOutcomeSummary {
  stage: CompilationStage
  status: StageStatus
  diagnostic_count: number
}

export interface CompilationSummary {
  compilation_id: string
  stage_outcomes: StageOutcomeSummary[]
  duration_ms: number | null
}

export interface CompilationOutcome {
  graph_model: GraphModel | null
  compilation_summary: CompilationSummary
  diagnostic_catalog: DiagnosticCatalog
}

// Re-import from sibling modules
import type { GraphModel } from './graph'
import type { DiagnosticCatalog } from './diagnostics'

export type { GraphModel, DiagnosticCatalog }
