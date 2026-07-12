/** WeConduct — Diagnostic Types
 *  Mirror of Python contracts at src/weconduct/contracts/diagnostics.py
 *  DO NOT modify without coordinating through docs/ui-collab/inbox-to-core/requests/
 */

export type DiagnosticSeverity = 'info' | 'warning' | 'degraded' | 'error' | 'fatal'

export type DiagnosticStage = 'parse' | 'bind' | 'validate' | 'normalize' | 'lower' | 'emit' | 'runtime' | 'debug' | 'workspace' | 'ui'

export interface Diagnostic {
  diagnostic_id: string
  stage: DiagnosticStage
  severity: DiagnosticSeverity
  category: string
  message: string
  object_ref: string | null
  trace_ref: string | null
  stage_extension: Record<string, unknown>
  degraded_extension: Record<string, unknown> | null
}

export interface DiagnosticCatalog {
  entries: Diagnostic[]
}

export type ProjectDiagnosticSource = 'compilation' | 'runtime' | 'debug' | 'workspace' | 'ui'

export interface ProjectDiagnostic extends Diagnostic {
  source: ProjectDiagnosticSource
  operation: string | null
  project_id: string | null
  project_name: string | null
  fingerprint: string
  http_status: number | null
  error_code: string | null
  raw_details: unknown
  count: number
  first_seen_at: string
  last_seen_at: string
}

/** API view model — diagnostic group for UI display */
export interface DiagnosticGroup {
  stage: string
  category: string
  severity: DiagnosticSeverity
  count: number
  message: string
}

/** API view model — diagnostic summary */
export interface DiagnosticSummary {
  total_count: number
  highest_severity: DiagnosticSeverity | null
}

/** API view model — primary diagnostic for quick display */
export interface PrimaryDiagnostic {
  stage: string
  category: string
  severity: DiagnosticSeverity
  message: string
}
