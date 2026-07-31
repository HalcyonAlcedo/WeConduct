import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import DiagnosticsTab from './DiagnosticsTab.vue'
import { useProjectDiagnosticsStore } from '@/stores/projectDiagnosticsStore'

const graphNavigationState = vi.hoisted(() => ({ locateGraphNode: vi.fn(), locateGraphEdge: vi.fn() }))
vi.mock('@/services/graphNodeNavigation', () => ({
  locateGraphNode: graphNavigationState.locateGraphNode,
  locateGraphEdge: graphNavigationState.locateGraphEdge,
}))

describe('DiagnosticsTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('hides non-user-facing debug stage-completed diagnostics while showing real debug errors', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const diagnostics = useProjectDiagnosticsStore()
    diagnostics.ingestCatalog({ entries: [
        {
          diagnostic_id: 'debug-1:parse',
          stage: 'parse',
          severity: 'info',
          category: 'parse.completed',
          message: 'parsed source document',
          object_ref: 'graph:workspace',
          trace_ref: null,
          subject_ref: 'debug-1',
          source_ref: { source_kind: 'graph_workspace' },
          graph_ref: null,
        },
        {
          diagnostic_id: 'debug-1:bind',
          stage: 'validate',
          severity: 'info',
          category: 'validate.completed',
          message: 'validated bound source',
          object_ref: 'graph:workspace',
          trace_ref: null,
          subject_ref: 'debug-1',
          source_ref: { source_kind: 'graph_workspace' },
          graph_ref: null,
        },
        {
          diagnostic_id: 'debug-1:bind-error',
          stage: 'bind',
          severity: 'error',
          category: 'graph.binding.invalid_reference',
          message: 'binding failed on node-start',
          object_ref: 'node:node-start',
          trace_ref: null,
          subject_ref: 'debug-1',
          source_ref: null,
          graph_ref: { node_id: 'node-start' },
        },
      ] }, { source: 'debug', operation: 'debug.start' })

    const wrapper = mount(DiagnosticsTab, {
      global: {
        plugins: [pinia],
        stubs: {
          PlaceholderBanner: {
            template: '<div><slot /></div>',
          },
          Teleport: true,
        },
      },
    })

    expect(wrapper.text()).not.toContain('parsed source document')
    expect(wrapper.text()).not.toContain('parse.completed')
    expect(wrapper.text()).not.toContain('validated bound source')
    expect(wrapper.text()).not.toContain('validate.completed')
    expect(wrapper.text()).toContain('binding failed on node-start')
    expect(wrapper.text()).toContain('graph.binding.invalid_reference')
  })

  it('右键边诊断时提供定位边操作', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const diagnostics = useProjectDiagnosticsStore()
    diagnostics.ingestCatalog({ entries: [{
      diagnostic_id: 'graph-edge-1', stage: 'validate', severity: 'fatal',
      category: 'graph.edge.relation_layer_mismatch', message: 'edge mismatch',
      object_ref: 'edge-invalid', trace_ref: null,
      stage_extension: { graph_ref: { edge_id: 'edge-invalid' } },
      degraded_extension: null,
    }] }, { source: 'compilation', operation: 'graph.validate' })
    const wrapper = mount(DiagnosticsTab, {
      global: { plugins: [pinia], stubs: { PlaceholderBanner: { template: '<div><slot /></div>' }, Teleport: true } },
    })

    await wrapper.get('.dt-group-row').trigger('contextmenu', { clientX: 10, clientY: 20 })
    const locateButton = wrapper.findAll('.dt-ctx-btn').find(button => button.text().includes('定位边'))
    expect(locateButton).toBeDefined()
    await locateButton!.trigger('click')

    expect(graphNavigationState.locateGraphEdge).toHaveBeenCalledWith('edge-invalid')
  })
})
