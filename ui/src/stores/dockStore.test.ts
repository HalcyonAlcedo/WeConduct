import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDockStore } from './dockStore'

function seedPanels() {
  const store = useDockStore()
  store.register({ id: 'a', title: 'Panel A' })
  store.register({ id: 'b', title: 'Panel B' })
  store.register({ id: 'c', title: 'Panel C' })
  store.register({ id: 'd', title: 'Panel D' })
  return store
}

describe('dockStore movePanel invariants', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('移动活动标签后，来源区 activePanelId 优先切到右侧标签', () => {
    const store = seedPanels()
    store.addToZone('a', 'left')
    store.addToZone('b', 'left')
    store.addToZone('c', 'left')
    store.activatePanel('b')

    store.movePanel('b', 'right')

    expect(store.zones.left.panels.map(panel => panel.id)).toEqual(['a', 'c'])
    expect(store.zones.left.activePanelId).toBe('c')
    expect(store.zones.right.panels.map(panel => panel.id)).toEqual(['b'])
    expect(store.zones.right.activePanelId).toBe('b')
  })

  it('移动非活动标签后，来源区 activePanelId 保持不变', () => {
    const store = seedPanels()
    store.addToZone('a', 'left')
    store.addToZone('b', 'left')
    store.addToZone('c', 'left')
    store.activatePanel('b')

    store.movePanel('a', 'right')

    expect(store.zones.left.panels.map(panel => panel.id)).toEqual(['b', 'c'])
    expect(store.zones.left.activePanelId).toBe('b')
    expect(store.zones.right.activePanelId).toBe('a')
  })

  it('移走最后一个活动标签后，来源区 activePanelId 设为 null', () => {
    const store = seedPanels()
    store.addToZone('a', 'left')

    store.movePanel('a', 'right')

    expect(store.zones.left.panels).toEqual([])
    expect(store.zones.left.activePanelId).toBeNull()
    expect(store.zones.right.activePanelId).toBe('a')
  })

  it('活动标签没有右侧邻居时，来源区 activePanelId 回退到左侧标签', () => {
    const store = seedPanels()
    store.addToZone('a', 'left')
    store.addToZone('b', 'left')
    store.addToZone('c', 'left')
    store.activatePanel('c')

    store.movePanel('c', 'right')

    expect(store.zones.left.panels.map(panel => panel.id)).toEqual(['a', 'b'])
    expect(store.zones.left.activePanelId).toBe('b')
  })

  it('重复移动和同区移动不会产生重复 panel id，并保持目标区 active', () => {
    const store = seedPanels()
    store.addToZone('a', 'left')
    store.addToZone('b', 'left')

    store.movePanel('a', 'left')
    store.movePanel('a', 'right')
    store.movePanel('a', 'right')

    expect(store.zones.left.panels.map(panel => panel.id)).toEqual(['b'])
    expect(store.zones.left.activePanelId).toBe('b')
    expect(store.zones.right.panels.map(panel => panel.id)).toEqual(['a'])
    expect(store.zones.right.activePanelId).toBe('a')
    expect(store.visiblePanels).toEqual(['b', 'a'])
  })
})
