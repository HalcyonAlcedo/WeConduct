import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DocsMetadataPanel from './DocsMetadataPanel.vue'
import type { GraphNode } from './types'

const node: GraphNode = {
  node_id: 'node-browser-click-1',
  lowered_kind: 'execution',
  source_anchor_ref: 'docs:browser-click:1',
  expansion_role: 'action:click',
  display_name: '点击',
  node_kind: 'browser.click',
  position: { x: 320, y: 180 },
  ports: [
    { port_id: 'in', direction: 'input', relation_layer: 'control', semantic_slot: 'in.control' },
    { port_id: 'out', direction: 'output', relation_layer: 'control', semantic_slot: 'out.control' },
  ],
  node_config: {
    selector: '#submit',
    options: { timeout: 30, strict: true },
    fallbacks: [
      { label: '备用选择器', selector: '.submit' },
      null,
    ],
  },
}

describe('DocsMetadataPanel', () => {
  it('renders node identity, ports and nested configuration as structured metadata', () => {
    const wrapper = mount(DocsMetadataPanel, { props: { node, collapsed: false } })

    expect(wrapper.find('.wc-meta-title').text()).toBe('点击')
    expect(wrapper.text()).toContain('node-browser-click-1')
    expect(wrapper.text()).toContain('browser.click')
    expect(wrapper.text()).toContain('docs:browser-click:1')
    expect(wrapper.findAll('.wc-meta-port')).toHaveLength(2)
    expect(wrapper.findAll('.wc-meta-tree-key').map(item => item.text())).toEqual(
      expect.arrayContaining(['node_config', 'selector', 'options', 'timeout', 'strict', 'fallbacks', '0', 'label']),
    )
    expect(wrapper.text()).toContain('#submit')
    expect(wrapper.text()).toContain('备用选择器')
    expect(wrapper.text()).toContain('boolean')
    expect(wrapper.text()).toContain('null')
  })

  it('emits toggle and hides metadata content while collapsed', async () => {
    const wrapper = mount(DocsMetadataPanel, { props: { node, collapsed: true } })

    expect(wrapper.classes()).toContain('is-collapsed')
    expect(wrapper.find('.wc-meta-body').exists()).toBe(false)
    await wrapper.find('.wc-meta-toggle').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })
})
