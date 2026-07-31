import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGraphStore } from './graphStore'
import type { GraphModel } from '@/types/domains/graph'

describe('graphStore python.run dynamic ports', () => {
  it('derives schema ports for immediate rendering before server normalization', () => {
    setActivePinia(createPinia())
    const store = useGraphStore()
    const graph: GraphModel = {
      graph_model_id: 'graph:workspace',
      compilation_id: null,
      graph_effective_diagnostic_anchor_refs: [],
      nodes: [
        {
          node_id: 'python-node',
          lowered_kind: 'execution',
          source_anchor_ref: 'n-python-node',
          expansion_role: 'action:python_run',
          node_kind: 'python.run',
          ports: [
            { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
            { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
          ],
          node_config: {
            input_schema: { username: { type: 'string' } },
            output_schema: { logged_in: { type: 'boolean' } },
            metadata_schema: { request_id: { type: 'string' } },
          },
        },
      ],
      edges: [],
    }

    const { nodes } = store.toVueFlow(graph)
    const ports = (nodes[0].data as any).ports as Array<{ port_id: string; semantic_slot: string }>

    expect(ports.map(port => port.semantic_slot)).toEqual([
      'in.control',
      'out.control',
      'in.username',
      'out.logged_in',
      'out.metadata.request_id',
    ])
    expect(ports.find(port => port.semantic_slot === 'in.username')?.port_id).toBe(
      'python-node::python::in-username',
    )
  })

  it('为命中诊断的节点和边附加错误样式类', () => {
    setActivePinia(createPinia())
    const store = useGraphStore()
    const graph: GraphModel = {
      graph_model_id: 'graph:workspace', compilation_id: null, graph_effective_diagnostic_anchor_refs: [],
      nodes: [
        { node_id: 'node-error', lowered_kind: 'execution', source_anchor_ref: 'n1', expansion_role: 'x', ports: [] },
        { node_id: 'node-ok', lowered_kind: 'execution', source_anchor_ref: 'n2', expansion_role: 'x', ports: [] },
      ],
      edges: [{ edge_id: 'edge-error', relation_layer: 'control', from_node_id: 'node-error', to_node_id: 'node-ok' }],
    }

    const rendered = (store.toVueFlow as any)(graph, undefined, {
      errorNodeIds: new Set(['node-error']),
      errorEdgeIds: new Set(['edge-error']),
    })

    expect(rendered.nodes.find((node: any) => node.id === 'node-error')?.class).toContain('vf-node-error')
    expect(rendered.nodes.find((node: any) => node.id === 'node-ok')?.class).toBeUndefined()
    expect(rendered.edges[0].class).toContain('vf-edge-error')
  })
})
