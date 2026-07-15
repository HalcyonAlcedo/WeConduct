import { describe, expect, it } from 'vitest'
import { toVueFlowGraph, validateGraphPayload } from './graph-model'
import type { GraphModel } from './types'

function graphFixture(): GraphModel {
  return {
    graph_model_id: 'graph:test',
    graph_schema_version: 'graph-v1',
    nodes: [
      {
        node_id: 'node-a',
        lowered_kind: 'execution',
        expansion_role: 'action:click',
        display_name: '点击',
        node_kind: 'browser.click',
        position: { x: 190, y: 128 },
        ports: [
          { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
          { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
        ],
        node_config: { selector: '#submit' },
      },
      {
        node_id: 'node-b',
        lowered_kind: 'control',
        expansion_role: 'branch:if',
        display_name: '条件',
        node_kind: 'control.if',
        position: { x: 480, y: 128 },
        ports: [
          { port_id: 'condition', direction: 'input', relation_layer: 'data', semantic_slot: 'in.condition' },
          { port_id: 'true', direction: 'output', relation_layer: 'control', semantic_slot: 'out.true' },
        ],
        node_config: { condition: '{{ready}}' },
      },
    ],
    edges: [
      {
        edge_id: 'edge-a-b',
        relation_layer: 'control',
        from_node_id: 'node-a',
        to_node_id: 'node-b',
        from_port_id: 'out',
        to_port_id: 'condition',
      },
    ],
  }
}

describe('validateGraphPayload', () => {
  it('rejects unsupported graph schemas and malformed nodes', () => {
    expect(() => validateGraphPayload({ graph_schema_version: 'graph-v2', nodes: [], edges: [] })).toThrow('graph-v1')
    expect(() => validateGraphPayload({ graph_schema_version: 'graph-v1', nodes: [{}], edges: [] })).toThrow('position')
  })
})

describe('toVueFlowGraph', () => {
  it('uses the WeConduct 180 x 56 center-coordinate conversion', () => {
    const result = toVueFlowGraph(graphFixture())
    expect(result.nodes[0].position).toEqual({ x: 100, y: 100 })
    expect(result.nodes[0].type).toBe('execution')
    expect(result.nodes[0].data).toMatchObject({
      label: '点击',
      nodeId: 'node-a',
      kind: 'execution',
      nodeKind: 'browser.click',
      nodeConfig: { selector: '#submit' },
    })
  })

  it('maps relation layers and port ids to Vue Flow bezier edges', () => {
    const result = toVueFlowGraph(graphFixture())
    expect(result.edges[0]).toMatchObject({
      id: 'edge-a-b',
      source: 'node-a',
      target: 'node-b',
      sourceHandle: 'out',
      targetHandle: 'condition',
      type: 'bezier',
      class: 'vf-edge-control',
      style: {
        stroke: 'var(--edge-control)',
        strokeWidth: '1.75',
      },
    })
  })

  it('falls back to the execution renderer for unknown lowered kinds', () => {
    const graph = graphFixture()
    graph.nodes[0].lowered_kind = 'future-kind'
    const result = toVueFlowGraph(graph)
    expect(result.nodes[0].type).toBe('execution')
    expect(result.nodes[0]!.data!.kind).toBe('execution')
  })
})
