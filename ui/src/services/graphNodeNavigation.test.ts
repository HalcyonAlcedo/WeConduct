import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDockStore } from '@/stores/dockStore'
import { useGraphStore } from '@/stores/graphStore'
import { locateGraphNode, registerGraphNodeNavigator } from './graphNodeNavigation'

describe('graphNodeNavigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('画布晚于定位请求挂载时仍选中节点、打开图面板并完成居中', async () => {
    const dock = useDockStore()
    const graph = useGraphStore()
    const centeredNodeIds: string[] = []
    dock.register({ id: 'graph', title: '节点图编辑器' })

    await locateGraphNode('node-list-files')
    const unregister = registerGraphNodeNavigator(nodeId => centeredNodeIds.push(nodeId))

    expect(graph.selectedNode).toBe('node-list-files')
    expect(dock.isPanelVisible('graph')).toBe(true)
    expect(centeredNodeIds).toEqual(['node-list-files'])
    unregister()
  })

  it('画布晚于定位请求挂载时仍可定位边', async () => {
    const navigation = await import('./graphNodeNavigation') as any
    const dock = useDockStore()
    const locatedTargets: Array<{ kind: string; id: string }> = []
    dock.register({ id: 'graph', title: '节点图编辑器' })

    await navigation.locateGraphEdge('edge-invalid')
    const unregister = navigation.registerGraphElementNavigator((target: { kind: string; id: string }) => locatedTargets.push(target))

    expect(dock.isPanelVisible('graph')).toBe(true)
    expect(locatedTargets).toEqual([{ kind: 'edge', id: 'edge-invalid' }])
    unregister()
  })
})
