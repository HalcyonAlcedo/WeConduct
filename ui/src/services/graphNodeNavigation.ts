import { nextTick } from 'vue'
import { useDockStore } from '@/stores/dockStore'
import { useGraphStore } from '@/stores/graphStore'

type GraphNodeNavigator = (nodeId: string) => void

let registeredNavigator: GraphNodeNavigator | null = null
let pendingNodeId: string | null = null

function flushPendingNodeLocation() {
  if (!registeredNavigator || !pendingNodeId) return
  const nodeId = pendingNodeId
  pendingNodeId = null
  registeredNavigator(nodeId)
}

/** Registers the mounted graph canvas as the destination for node location requests. */
export function registerGraphNodeNavigator(navigator: GraphNodeNavigator): () => void {
  registeredNavigator = navigator
  flushPendingNodeLocation()
  return () => {
    if (registeredNavigator === navigator) registeredNavigator = null
  }
}

/** Selects a node, restores the graph panel, then centers it after the canvas mounts. */
export async function locateGraphNode(nodeId: string): Promise<void> {
  const normalizedNodeId = nodeId.trim()
  if (!normalizedNodeId) return
  useGraphStore().selectNode(normalizedNodeId)
  useDockStore().restorePanel('graph')
  pendingNodeId = normalizedNodeId
  await nextTick()
  flushPendingNodeLocation()
}
