import type { Diagnostic } from '@/types/domains/diagnostics'
import type { GraphModel } from '@/types/domains/graph'

export interface GraphDiagnosticTargets {
  errorNodeIds: Set<string>
  errorEdgeIds: Set<string>
}

function graphReference(entry: Diagnostic): Record<string, unknown> | null {
  const extension = entry.stage_extension
  if (!extension || typeof extension !== 'object') return null
  const graphRef = (extension as Record<string, unknown>).graph_ref
  return graphRef && typeof graphRef === 'object' && !Array.isArray(graphRef)
    ? graphRef as Record<string, unknown>
    : null
}

function nodeIdFromReference(value: unknown, nodeIds: Set<string>): string | null {
  if (typeof value !== 'string') return null
  if (nodeIds.has(value)) return value
  const match = value.match(/^node:([^\s]+)$/)
  return match && nodeIds.has(match[1]) ? match[1] : null
}

function edgeIdFromReference(value: unknown, edgeIds: Set<string>): string | null {
  if (typeof value !== 'string') return null
  if (edgeIds.has(value)) return value
  const match = value.match(/^edge:([^\s]+)$/)
  return match && edgeIds.has(match[1]) ? match[1] : null
}

/** Resolves only fatal/error diagnostics that reference elements in the active graph. */
export function resolveGraphDiagnosticTargets(
  graph: GraphModel,
  diagnostics: readonly Diagnostic[],
): GraphDiagnosticTargets {
  const nodeIds = new Set(graph.nodes.map(node => node.node_id))
  const edgeIds = new Set(graph.edges.map(edge => edge.edge_id))
  const errorNodeIds = new Set<string>()
  const errorEdgeIds = new Set<string>()

  for (const entry of diagnostics) {
    if (entry.severity !== 'fatal' && entry.severity !== 'error') continue
    const graphRef = graphReference(entry)
    const nodeId = nodeIdFromReference(entry.object_ref, nodeIds)
      ?? nodeIdFromReference(graphRef?.node_id, nodeIds)
    const edgeId = edgeIdFromReference(entry.object_ref, edgeIds)
      ?? edgeIdFromReference(graphRef?.edge_id, edgeIds)
    if (nodeId) errorNodeIds.add(nodeId)
    if (edgeId) errorEdgeIds.add(edgeId)
  }

  return { errorNodeIds, errorEdgeIds }
}
