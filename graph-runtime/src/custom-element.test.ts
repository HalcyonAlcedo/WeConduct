import { defineComponent, h, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./GraphEmbed.vue', () => ({
  default: defineComponent({
    props: ['state'],
    setup(props) {
      return () => h('div', { class: 'graph-embed-stub' }, [
        h('strong', props.state.title),
        props.state.loading ? h('span', 'loading') : null,
        props.state.error ? h('span', props.state.error) : null,
        props.state.graph ? h('span', `nodes:${props.state.graph.nodes.length}`) : null,
      ])
    },
  }),
}))

import { registerWeConductGraph, resolveGraphSource } from './custom-element'

const graph = {
  graph_model_id: 'graph:test',
  graph_schema_version: 'graph-v1',
  nodes: [{
    node_id: 'node-a',
    lowered_kind: 'execution',
    display_name: '点击',
    position: { x: 90, y: 28 },
    ports: [],
    node_config: {},
  }],
  edges: [],
}

async function flush(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('weconduct-graph custom element', () => {
  beforeEach(() => {
    registerWeConductGraph()
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('registers and loads graph-v1 through the existing element contract', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(graph), { status: 200 }),
    )
    const element = document.createElement('weconduct-graph')
    element.setAttribute('src', 'fixture.json')
    element.setAttribute('title', '节点图示例')
    document.body.append(element)
    await flush()

    expect(customElements.get('weconduct-graph')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('fixture.json', expect.objectContaining({ cache: 'no-store' }))
    expect(element.textContent).toContain('节点图示例')
    expect(element.textContent).toContain('nodes:1')
  })

  it('updates titles without reloading and aborts stale src requests', async () => {
    const requests: Array<{ signal: AbortSignal; resolve: (response: Response) => void }> = []
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_url, options) => (
      new Promise<Response>((resolve) => requests.push({ signal: options!.signal as AbortSignal, resolve }))
    ))
    const element = document.createElement('weconduct-graph')
    element.setAttribute('src', 'first.json')
    element.setAttribute('title', '旧标题')
    document.body.append(element)
    await nextTick()

    element.setAttribute('title', '新标题')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await nextTick()
    expect(element.textContent).toContain('新标题')

    element.setAttribute('src', 'second.json')
    expect(requests[0].signal.aborted).toBe(true)
    requests[1].resolve(new Response(JSON.stringify(graph), { status: 200 }))
    await flush()
    expect(element.textContent).toContain('nodes:1')
  })

  it('unmounts Vue state when removed from the document', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(graph), { status: 200 }))
    const element = document.createElement('weconduct-graph')
    element.setAttribute('src', 'fixture.json')
    document.body.append(element)
    await flush()
    expect(element.querySelector('.graph-embed-stub')).toBeTruthy()

    element.remove()
    await nextTick()
    expect(element.querySelector('.graph-embed-stub')).toBeNull()
  })
})

describe('resolveGraphSource', () => {
  it('keeps direct URLs unchanged', () => {
    expect(resolveGraphSource('fixture.json')).toBe('fixture.json')
  })

  it('uses the stable runtime stylesheet root after MkDocs instant navigation', () => {
    const stylesheet = document.createElement('link')
    stylesheet.href = '/WeConduct/assets/graph-runtime/weconduct-graph.css'
    const staleScript = document.createElement('script')
    staleScript.type = 'application/json'
    staleScript.src = '/WeConduct/weconduct/components/assets/graph-runtime/weconduct-graph.js'
    document.head.append(stylesheet, staleScript)

    try {
      expect(resolveGraphSource('../../../../assets/graphs/components/browser/browser-click.json'))
        .toBe(`${location.origin}/WeConduct/assets/graphs/components/browser/browser-click.json`)
    } finally {
      stylesheet.remove()
      staleScript.remove()
    }
  })
})
