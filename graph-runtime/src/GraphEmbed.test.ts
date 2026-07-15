import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@vue-flow/core', () => ({
  VueFlow: defineComponent({
    props: [
      'id',
      'nodes',
      'edges',
      'nodeTypes',
      'minZoom',
      'maxZoom',
      'zoomOnDoubleClick',
    ],
    emits: ['nodeClick', 'nodeDoubleClick', 'paneClick'],
    setup(props, { emit, slots }) {
      return () => h('div', {
        class: 'mock-vue-flow',
        'data-min-zoom': props.minZoom,
        'data-max-zoom': props.maxZoom,
        'data-zoom-on-double-click': props.zoomOnDoubleClick,
      }, [
        h('button', {
          class: 'emit-node-click',
          onClick: () => emit('nodeClick', { node: { id: 'node-a' } }),
        }),
        h('button', {
          class: 'emit-node-double-click',
          onDblclick: () => emit('nodeDoubleClick', { node: { id: 'node-a' } }),
        }),
        h('button', {
          class: 'emit-pane-click',
          onClick: () => emit('paneClick'),
        }),
        slots.default?.(),
      ])
    },
  }),
}))

vi.mock('@vue-flow/background', () => ({
  Background: defineComponent(() => () => h('div', { class: 'mock-background' })),
}))

vi.mock('@vue-flow/controls', () => ({
  Controls: defineComponent(() => () => h('div', { class: 'mock-controls' })),
}))

vi.mock('@vue-flow/minimap', () => ({
  MiniMap: defineComponent(() => () => h('div', { class: 'mock-minimap' })),
}))

import GraphEmbed from './GraphEmbed.vue'
import type { GraphRuntimeState } from './types'

const state: GraphRuntimeState = {
  instanceId: 'wc-test',
  title: '测试图',
  loading: false,
  error: '',
  fallback: '',
  graph: {
    graph_model_id: 'graph:test',
    graph_schema_version: 'graph-v1',
    nodes: [{
      node_id: 'node-a',
      lowered_kind: 'execution',
      display_name: '点击',
      node_kind: 'browser.click',
      expansion_role: 'action:click',
      source_anchor_ref: 'docs:test:1',
      position: { x: 90, y: 28 },
      ports: [],
      node_config: { selector: '#submit' },
    }],
    edges: [],
  },
}

describe('GraphEmbed', () => {
  it('uses readable zoom limits and opens metadata only on node double-click', async () => {
    const wrapper = mount(GraphEmbed, { props: { state } })
    const flow = wrapper.find('.mock-vue-flow')

    expect(flow.attributes('data-min-zoom')).toBe('0.45')
    expect(flow.attributes('data-max-zoom')).toBe('1.5')
    expect(flow.attributes('data-zoom-on-double-click')).toBe('false')
    expect(wrapper.find('.wc-metadata-panel').exists()).toBe(false)

    await wrapper.find('.emit-node-click').trigger('click')
    expect(wrapper.find('.wc-metadata-panel').exists()).toBe(false)

    await wrapper.find('.emit-node-double-click').trigger('dblclick')
    expect(wrapper.find('.wc-metadata-panel').exists()).toBe(true)
    expect(wrapper.find('.wc-metadata-panel').classes()).not.toContain('is-collapsed')

    await wrapper.find('.wc-meta-toggle').trigger('click')
    expect(wrapper.find('.wc-metadata-panel').classes()).toContain('is-collapsed')

    await wrapper.find('.emit-node-double-click').trigger('dblclick')
    expect(wrapper.find('.wc-metadata-panel').classes()).not.toContain('is-collapsed')

    await wrapper.find('.emit-pane-click').trigger('click')
    expect(wrapper.find('.wc-metadata-panel').exists()).toBe(false)
  })
})
