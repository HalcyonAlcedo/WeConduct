export type LoweredNodeKind = 'execution' | 'control' | 'observe' | 'bridge'
export type RelationLayer = 'control' | 'data' | 'observe'

export interface GraphPosition {
  x: number
  y: number
}

export interface GraphPort {
  port_id: string
  direction: 'input' | 'output'
  relation_layer: RelationLayer
  semantic_slot?: string
  display_name?: string | null
}

export interface GraphNode {
  node_id: string
  lowered_kind: LoweredNodeKind | string
  source_anchor_ref?: string
  expansion_role?: string
  display_name?: string | null
  node_kind?: string | null
  position: GraphPosition
  ports: GraphPort[]
  node_config?: Record<string, unknown>
}

export interface GraphEdge {
  edge_id: string
  relation_layer: RelationLayer
  from_node_id: string
  to_node_id: string
  from_port_id?: string | null
  to_port_id?: string | null
}

export interface GraphModel {
  graph_model_id: string
  graph_schema_version: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface DocsNodeData extends Record<string, unknown> {
  label: string
  nodeId: string
  kind: LoweredNodeKind
  expansionRole: string
  nodeKind: string
  ports: GraphPort[]
  nodeConfig: Record<string, unknown>
}

export interface GraphRuntimeState {
  instanceId: string
  title: string
  graph: GraphModel | null
  loading: boolean
  error: string
  fallback: string
}
