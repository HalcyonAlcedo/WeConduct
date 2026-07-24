/** WeConduct — Graph Layout Store
 *  Computes dagre-based positions for GraphModel nodes.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import dagre from 'dagre'
import type { GraphModel, GraphNode, GraphPort } from '@/types/domains/graph'
import type { Node, Edge } from '@vue-flow/core'

const NODE_WIDTH = 180
const NODE_HEIGHT = 56

export const useGraphStore = defineStore('graph', () => {
  const selectedNodeId = ref<string | null>(null)

  /** Convert WeConduct GraphModel to Vue Flow nodes with dagre layout */
  // Map the edge_line_style preference to a VueFlow edge type.
  // 'bezier' → VueFlow 'default' (bezier curve); others map 1:1.
  function resolveEdgeType(edgeLineStyle?: string): string {
    if (edgeLineStyle === 'straight') return 'straight'
    if (edgeLineStyle === 'bezier') return 'default'
    return 'smoothstep'
  }

  function toVueFlow(graph: GraphModel, edgeLineStyle?: string): { nodes: Node[]; edges: Edge[] } {
    const edgeType = resolveEdgeType(edgeLineStyle)
    if (!graph.nodes.length) {
      return { nodes: [], edges: [] }
    }

    // Build dagre graph
    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 40, marginy: 40 })

    for (const node of graph.nodes) {
      g.setNode(node.node_id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    }

    for (const edge of graph.edges) {
      g.setEdge(edge.from_node_id, edge.to_node_id)
    }

    // If no edges, layout in a grid
    if (graph.edges.length === 0) {
      dagre.layout(g)
    } else {
      dagre.layout(g)
    }

    // Convert nodes: use saved position, only dagre for initial layout
    const vfNodes: Node[] = graph.nodes.map((node) => {
      const dagrePos = g.node(node.node_id) ?? { x: 0, y: 0 }
      const hasSavedPos = node.position && typeof node.position.x === 'number' && typeof node.position.y === 'number'
      // Both dagre and saved positions are center-based; convert to top-left for VueFlow
      const cx = hasSavedPos ? node.position!.x : dagrePos.x
      const cy = hasSavedPos ? node.position!.y : dagrePos.y
      return {
        id: node.node_id,
        type: node.lowered_kind,
        position: { x: cx - NODE_WIDTH / 2, y: cy - NODE_HEIGHT / 2 },
        data: {
          label: node.display_name || node.node_kind || node.node_id,
          nodeId: node.node_id,
          kind: node.lowered_kind,
          expansionRole: node.expansion_role,
          nodeKind: node.node_kind,
          ports: deriveVisualPorts(node),
        },
      }
    })

    // Convert edges
    const vfEdges: Edge[] = graph.edges.map((edge) => ({
      id: edge.edge_id,
      source: edge.from_node_id,
      target: edge.to_node_id,
      sourceHandle: edge.from_port_id || undefined,
      targetHandle: edge.to_port_id || undefined,
      type: edgeType,
      class: `vf-edge-${edge.relation_layer}`,
      style: edgeStyle(edge.relation_layer),
    }))

    return { nodes: vfNodes, edges: vfEdges }
  }

  function selectNode(id: string | null) { selectedNodeId.value = id }
  const selectedNode = computed(() => selectedNodeId.value)

  /** Unified graph selection: prefers workspace (with nodes) > compilation outcome (with nodes) > null */
  function selectGraphModel(opts: {
    workspaceModel: GraphModel | null | undefined
    compilationModel: GraphModel | null | undefined
  }): { model: GraphModel | null; source: 'workspace' | 'compilation' | null } {
    const wsModel = opts.workspaceModel
    const compModel = opts.compilationModel
    const wsOk = wsModel && (wsModel.nodes?.length ?? 0) > 0
    const compOk = compModel && (compModel.nodes?.length ?? 0) > 0

    if (wsOk) return { model: wsModel!, source: 'workspace' }
    if (compOk) return { model: compModel!, source: 'compilation' }
    return { model: null, source: null }
  }

  return { selectedNodeId, selectedNode, toVueFlow, selectNode, selectGraphModel }
})

function edgeStyle(layer: string): Record<string, string> {
  switch (layer) {
    case 'data':
      return { stroke: 'var(--state-info)', strokeDasharray: '6 3' }
    case 'observe':
      return { stroke: 'var(--state-warning)', strokeDasharray: '3 2' }
    case 'control':
    default:
      return { stroke: 'var(--border-default)' }
  }
}

/**
 * Mirror the backend python.run schema-port contract for immediate canvas feedback.
 * The normalized graph remains the source of truth when the document is saved; this
 * visual derivation only prevents a schema edit from leaving the node without handles
 * until the next normalize request completes.
 */
function deriveVisualPorts(node: GraphNode): GraphPort[] {
  if (node.node_kind !== 'python.run') return [...(node.ports || [])]

  const existing = node.ports || []
  const existingPortIdForSlot = (slot: string, direction: GraphPort['direction'], fallback: string): string => {
    const match = existing.find(port => port.direction === direction && port.semantic_slot === slot)
    return match?.port_id || fallback
  }
  const nodeId = node.node_id.trim() || 'python-node'
  const safePortId = (fieldId: string, prefix: string): string => {
    const safeField = fieldId.replace(/[^A-Za-z0-9_-]/g, '-').replace(/^-+|-+$/g, '') || 'field'
    return `${nodeId}::python::${prefix}-${safeField}`
  }
  const schemaEntries = (raw: unknown): Array<[string, Record<string, unknown>]> => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return []
    return Object.entries(raw as Record<string, unknown>)
      .filter(([fieldId]) => fieldId.trim().length > 0)
      .map(([fieldId, metadata]) => [
        fieldId.trim(),
        metadata && typeof metadata === 'object' && !Array.isArray(metadata)
          ? metadata as Record<string, unknown>
          : {},
      ])
  }
  const config = node.node_config || {}
  const ports: GraphPort[] = [
    {
      port_id: existingPortIdForSlot('in.control', 'input', 'in'),
      direction: 'input',
      relation_layer: 'control',
      semantic_slot: 'in.control',
      display_name: null,
      max_connections: null,
    },
    {
      port_id: existingPortIdForSlot('out.control', 'output', 'out'),
      direction: 'output',
      relation_layer: 'control',
      semantic_slot: 'out.control',
      display_name: null,
      max_connections: null,
    },
  ]

  for (const [fieldId, metadata] of schemaEntries(config.input_schema)) {
    ports.push({
      port_id: existingPortIdForSlot(`in.${fieldId}`, 'input', safePortId(fieldId, 'in')),
      direction: 'input',
      relation_layer: 'data',
      semantic_slot: `in.${fieldId}`,
      display_name: typeof metadata.label === 'string' ? metadata.label : null,
      max_connections: null,
    })
  }
  for (const [fieldId, metadata] of schemaEntries(config.output_schema)) {
    ports.push({
      port_id: existingPortIdForSlot(`out.${fieldId}`, 'output', safePortId(fieldId, 'out')),
      direction: 'output',
      relation_layer: 'data',
      semantic_slot: `out.${fieldId}`,
      display_name: typeof metadata.label === 'string' ? metadata.label : null,
      max_connections: null,
    })
  }
  for (const [fieldId, metadata] of schemaEntries(config.metadata_schema)) {
    ports.push({
      port_id: existingPortIdForSlot(
        `out.metadata.${fieldId}`,
        'output',
        safePortId(fieldId, 'out-metadata'),
      ),
      direction: 'output',
      relation_layer: 'data',
      semantic_slot: `out.metadata.${fieldId}`,
      display_name: typeof metadata.label === 'string' ? metadata.label : null,
      max_connections: null,
    })
  }
  return ports
}
