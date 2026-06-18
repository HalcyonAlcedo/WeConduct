import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SummaryTab from './SummaryTab.vue'
import { useCompilationStore } from '@/stores/compilationStore'

function mountWithCompilationState(durationMs: number | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useCompilationStore()
  store.compilePhase = 'completed'
  store.lastResponse = {
    status: 'succeeded',
    request: {
      compilation_id: 'comp-123',
      source: {
        kind: 'native_flow',
        entry_document: 'examples/native-flow.json',
        source_text: '{"nodes":[]}',
      },
      options: {
        stop_on_fatal: true,
      },
    },
    outcome: {
      graph_model: null,
      compilation_summary: {
        compilation_id: 'comp-123',
        stage_outcomes: [],
        duration_ms: durationMs,
      },
      diagnostic_catalog: {
        entries: [],
      },
    },
    view: {
      status: 'succeeded',
      duration_ms: durationMs,
      stage_cards: [],
      stage_overview: {
        total_stage_count: 6,
        succeeded_stage_count: 6,
        failed_stage_count: 0,
        terminal_stage: 'emit',
      },
      diagnostic_groups: [],
      diagnostic_summary: {
        total_count: 0,
        highest_severity: null,
      },
      primary_diagnostic: null,
      graph_stats: {
        graph_model_id: null,
        node_count: 0,
        edge_count: 0,
        effective_diagnostic_anchor_count: 0,
      },
    },
  }

  return mount(SummaryTab, {
    global: {
      plugins: [pinia],
    },
  })
}

describe('SummaryTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders formatted duration when backend returns duration_ms', () => {
    const wrapper = mountWithCompilationState(1234)

    expect(wrapper.text()).toContain('耗时: 1.23s')
  })

  it('keeps placeholder when duration_ms is unavailable', () => {
    const wrapper = mountWithCompilationState(null)

    expect(wrapper.text()).toContain('耗时: —')
  })
})
