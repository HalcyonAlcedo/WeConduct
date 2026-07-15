import type { Edge, Node } from '@vue-flow/core'
import type { DocsNodeData, GraphModel, LoweredNodeKind, RelationLayer } from './types'

export const NODE_WIDTH = 180
export const NODE_HEIGHT = 56

const NODE_KINDS = new Set<LoweredNodeKind>(['execution', 'control', 'observe', 'bridge'])

export interface VueFlowGraph {
  nodes: Node<DocsNodeData>[]
  edges: Edge[]
}

export function validateGraphPayload(value: unknown): GraphModel {
  if (!value || typeof value !== 'object') {
    throw new Error('Validation failed: graph root must be an object.')
  }

  const graph = value as Partial<GraphModel>
  if (graph.graph_schema_version !== 'graph-v1') {
    throw new Error('Validation failed: graph_schema_version must be graph-v1.')
  }
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    throw new Error('Validation failed: nodes and edges must be arrays.')
  }
  if (graph.nodes.length === 0) {
    throw new Error('Validation failed: graph must contain at least one node.')
  }

  graph.nodes.forEach((node, index) => {
    if (!node || typeof node !== 'object') {
      throw new Error(`Validation failed: nodes[${index}] must be an object.`)
    }
    if (!node.position || typeof node.position.x !== 'number' || typeof node.position.y !== 'number') {
      throw new Error(`Validation failed: nodes[${index}].position is required.`)
    }
    if (!Array.isArray(node.ports)) {
      throw new Error(`Validation failed: nodes[${index}].ports must be an array.`)
    }
  })

  return graph as GraphModel
}

export function toVueFlowGraph(graph: GraphModel): VueFlowGraph {
  const nodes: Node<DocsNodeData>[] = graph.nodes.map((node) => {
    const kind = normalizeNodeKind(node.lowered_kind)
    return {
      id: node.node_id,
      type: kind,
      position: {
        x: node.position.x - NODE_WIDTH / 2,
        y: node.position.y - NODE_HEIGHT / 2,
      },
      data: {
        label: node.display_name || node.node_kind || node.node_id,
        nodeId: node.node_id,
        kind,
        expansionRole: node.expansion_role || '',
        nodeKind: node.node_kind || '',
        ports: node.ports,
        nodeConfig: node.node_config || {},
      },
    }
  })

  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.edge_id,
    source: edge.from_node_id,
    target: edge.to_node_id,
    sourceHandle: edge.from_port_id || undefined,
    targetHandle: edge.to_port_id || undefined,
    type: 'bezier',
    class: `vf-edge-${edge.relation_layer}`,
    style: edgeStyle(edge.relation_layer),
  }))

  return { nodes, edges }
}

function normalizeNodeKind(value: string): LoweredNodeKind {
  return NODE_KINDS.has(value as LoweredNodeKind) ? value as LoweredNodeKind : 'execution'
}

function edgeStyle(layer: RelationLayer): Record<string, string> {
  switch (layer) {
    case 'data':
      return { stroke: 'var(--state-info)', strokeWidth: '1.75', strokeDasharray: '6 3' }
    case 'observe':
      return { stroke: 'var(--state-warning)', strokeWidth: '1.75', strokeDasharray: '3 2' }
    case 'control':
    default:
      return { stroke: 'var(--edge-control)', strokeWidth: '1.75' }
  }
}
