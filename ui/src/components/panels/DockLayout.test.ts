import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import DockLayout from './DockLayout.vue'
import { useDockStore } from '@/stores/dockStore'

describe('DockLayout membership guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('不会渲染不属于当前 zone 的 activePanelId，并回退到该 zone 的首个 panel', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const dock = useDockStore()
    dock.register({ id: 'left-a', title: 'Left A' })
    dock.register({ id: 'left-b', title: 'Left B' })
    dock.addToZone('left-a', 'left')
    dock.addToZone('left-b', 'left')
    dock.zones.left.activePanelId = 'ghost-panel'

    const wrapper = mount(DockLayout, {
      global: {
        plugins: [pinia],
      },
      slots: {
        'left-a': '<div data-testid="left-a-body">Left A Body</div>',
        'left-b': '<div data-testid="left-b-body">Left B Body</div>',
        'ghost-panel': '<div data-testid="ghost-body">Ghost Body</div>',
      },
    })

    await nextTick()

    expect(wrapper.find('[data-testid=\"left-a-body\"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid=\"ghost-body\"]').exists()).toBe(false)
    expect(wrapper.findAll('.dl-zone-tabs .dl-tab.active')[0]?.text()).toBe('Left A')
  })
})
