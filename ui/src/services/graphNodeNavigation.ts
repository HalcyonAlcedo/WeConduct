import { nextTick } from 'vue'
import { useDockStore } from '@/stores/dockStore'
import { useGraphStore } from '@/stores/graphStore'

export type GraphElementTarget = { kind: 'node' | 'edge'; id: string }

type GraphNodeNavigator = (nodeId: string) => void
type GraphElementNavigator = (target: GraphElementTarget) => void

let registeredNavigator: GraphElementNavigator | null = null
let pendingTarget: GraphElementTarget | null = null

function flushPendingGraphLocation() {
  if (!registeredNavigator || !pendingTarget) return
  const target = pendingTarget
  pendingTarget = null
  registeredNavigator(target)
}

/** Registers the mounted graph canvas as the destination for graph element location requests. */
export function registerGraphElementNavigator(navigator: GraphElementNavigator): () => void {
  registeredNavigator = navigator
  flushPendingGraphLocation()
  return () => {
    if (registeredNavigator === navigator) registeredNavigator = null
  }
}

/** Compatibility wrapper for callers that only support node locations. */
export function registerGraphNodeNavigator(navigator: GraphNodeNavigator): () => void {
  return registerGraphElementNavigator(target => {
    if (target.kind === 'node') navigator(target.id)
  })
}

async function locateGraphElement(target: GraphElementTarget): Promise<void> {
  const normalizedId = target.id.trim()
  if (!normalizedId) return
  useDockStore().restorePanel('graph')
  pendingTarget = { kind: target.kind, id: normalizedId }
  await nextTick()
  flushPendingGraphLocation()
}

/** Selects a node, restores the graph panel, then centers it after the canvas mounts. */
export async function locateGraphNode(nodeId: string): Promise<void> {
  const normalizedNodeId = nodeId.trim()
  if (!normalizedNodeId) return
  useGraphStore().selectNode(normalizedNodeId)
  await locateGraphElement({ kind: 'node', id: normalizedNodeId })
}

/** Restores the graph panel and centers the requested edge after the canvas mounts. */
export async function locateGraphEdge(edgeId: string): Promise<void> {
  await locateGraphElement({ kind: 'edge', id: edgeId })
}
