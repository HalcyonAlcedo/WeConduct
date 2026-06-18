/** WeConduct — Graph Model Types
 *  Mirror of Python contracts at src/weconduct/contracts/graph.py
 *  DO NOT modify without coordinating through docs/ui-collab/inbox-to-core/requests/
 */

export type LoweredNodeKind = 'execution' | 'control' | 'observe' | 'bridge'
export type RelationLayer = 'control' | 'data' | 'observe'

export interface GraphPosition { x: number; y: number }
export interface GraphViewport { x: number; y: number; zoom: number }

export interface GraphPort {
  port_id: string
  direction: 'input' | 'output'
  relation_layer: RelationLayer
  semantic_slot: string
  display_name?: string | null
  max_connections?: number | null
}

export interface GraphNode {
  node_id: string
  lowered_kind: LoweredNodeKind
  source_anchor_ref: string
  expansion_role: string
  display_name?: string | null
  node_kind?: string | null
  position?: GraphPosition | null
  ports?: GraphPort[]
  node_config?: Record<string, unknown>
}

export interface GraphEdge {
  edge_id: string
  relation_layer: RelationLayer
  from_node_id: string
  to_node_id: string
  from_port_id?: string | null
  to_port_id?: string | null
  edge_state?: string | null
}

export interface GraphModel {
  graph_model_id: string
  compilation_id: string | null
  graph_schema_version?: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  viewport?: GraphViewport | null
  root_metadata?: Record<string, unknown>
  graph_effective_diagnostic_anchor_refs: string[]
}

export interface GraphStats {
  graph_model_id: string | null
  node_count: number
  edge_count: number
  effective_diagnostic_anchor_count: number
}
