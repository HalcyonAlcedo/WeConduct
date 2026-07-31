import { describe, expect, it } from 'vitest'
import type { GraphModel } from '@/types/domains/graph'
import type { Diagnostic } from '@/types/domains/diagnostics'
import { resolveGraphDiagnosticTargets } from './graphDiagnosticTargets'

describe('resolveGraphDiagnosticTargets', () => {
  it('将 fatal/error 诊断中的对象引用与 graph_ref 映射为图元素', () => {
    const graph: GraphModel = {
      graph_model_id: 'graph:workspace', compilation_id: null, graph_effective_diagnostic_anchor_refs: [],
      nodes: [
        { node_id: 'node-invalid', lowered_kind: 'execution', source_anchor_ref: 'n1', expansion_role: 'x', ports: [] },
        { node_id: 'node-other', lowered_kind: 'execution', source_anchor_ref: 'n2', expansion_role: 'x', ports: [] },
      ],
      edges: [{ edge_id: 'edge-invalid', relation_layer: 'control', from_node_id: 'node-invalid', to_node_id: 'node-other' }],
    }
    const diagnostics: Diagnostic[] = [
      {
        diagnostic_id: 'edge-1', stage: 'validate', severity: 'fatal', category: 'graph.edge.invalid',
        message: 'invalid edge', object_ref: 'edge-invalid', trace_ref: null,
        stage_extension: { graph_ref: { edge_id: 'edge-invalid' } }, degraded_extension: null,
      },
      {
        diagnostic_id: 'node-1', stage: 'validate', severity: 'error', category: 'graph.node.invalid',
        message: 'invalid node', object_ref: 'node:node-invalid', trace_ref: null,
        stage_extension: {}, degraded_extension: null,
      },
      {
        diagnostic_id: 'warning-1', stage: 'validate', severity: 'warning', category: 'graph.edge.warning',
        message: 'warning only', object_ref: 'edge-invalid', trace_ref: null,
        stage_extension: {}, degraded_extension: null,
      },
    ]

    expect(resolveGraphDiagnosticTargets(graph, diagnostics)).toEqual({
      errorNodeIds: new Set(['node-invalid']),
      errorEdgeIds: new Set(['edge-invalid']),
    })
  })
})
