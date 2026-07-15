import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DocsBaseNode from './DocsBaseNode.vue'

vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({
    props: ['type', 'id', 'position'],
    setup(props) {
      return () => h('i', {
        class: 'mock-handle',
        'data-type': props.type,
        'data-id': props.id,
        'data-position': props.position,
      })
    },
  }),
  Position: { Left: 'left', Right: 'right' },
}))

const props = {
  id: 'node-browser-click-1',
  data: {
    label: '点击',
    nodeId: 'node-browser-click-1',
    kind: 'execution' as const,
    expansionRole: 'action:click',
    nodeKind: 'browser.click',
    ports: [
      { port_id: 'in', direction: 'input' as const, relation_layer: 'control' as const, semantic_slot: 'in.control' },
      { port_id: 'in:selector', direction: 'input' as const, relation_layer: 'data' as const, semantic_slot: 'in.selector' },
      { port_id: 'out', direction: 'output' as const, relation_layer: 'control' as const, semantic_slot: 'out.control' },
    ],
    nodeConfig: { selector: '#submit', timeout: 30, strict: true },
  },
}

describe('DocsBaseNode', () => {
  beforeEach(() => {
    document.documentElement.dataset.mdColorScheme = 'default'
  })

  it('matches the WeConduct read-only node structure', () => {
    const wrapper = mount(DocsBaseNode, {
      props,
      global: { provide: { wcGraphZoom: ref(1) } },
    })

    expect(wrapper.classes()).toContain('vf-node')
    expect(wrapper.classes()).toContain('node-execution')
    expect(wrapper.find('.vf-node-kind').text()).toBe('执行')
    expect(wrapper.find('.vf-node-id').text()).toBe('node-browser-click-1')
    expect(wrapper.find('.vf-node-label').text()).toBe('点击')
    expect(wrapper.findAll('.mock-handle')).toHaveLength(3)
    expect(wrapper.find('[data-id="in:selector"]').attributes('data-type')).toBe('target')
    expect(wrapper.find('[data-id="out"]').attributes('data-type')).toBe('source')
  })

  it('renders port labels and read-only configuration rows', () => {
    const wrapper = mount(DocsBaseNode, {
      props,
      global: { provide: { wcGraphZoom: ref(1) } },
    })

    expect(wrapper.findAll('.vf-port-label').map(item => item.text())).toEqual(['control', 'selector', 'control'])
    expect(wrapper.findAll('.vf-cfg-key').map(item => item.text())).toEqual(['selector', 'timeout', 'strict'])
    expect(wrapper.findAll('.vf-cfg-ro').map(item => item.text())).toEqual(['#submit', '30', 'true'])
    expect(wrapper.findAll('input')).toHaveLength(0)
  })

  it('keeps all read-only details visible at every zoom level', () => {
    const wrapper = mount(DocsBaseNode, {
      props,
      global: { provide: { wcGraphZoom: ref(0.1) } },
    })
    expect(wrapper.find('.vf-node-label').exists()).toBe(true)
    expect(wrapper.find('.vf-config').exists()).toBe(true)
    expect(wrapper.findAll('.vf-port-label')).toHaveLength(3)
    expect(wrapper.find('.vf-node-id').exists()).toBe(true)
  })
})
