import { createApp, shallowReactive, type App } from 'vue'
import GraphEmbed from './GraphEmbed.vue'
import { validateGraphPayload } from './graph-model'
import type { GraphRuntimeState } from './types'

const ELEMENT_NAME = 'weconduct-graph'
const SCRIPT_MARKER = 'assets/graph-runtime/weconduct-graph.js'
const STYLE_MARKER = 'assets/graph-runtime/weconduct-graph.css'
let instanceSequence = 0

export function resolveGraphSource(source: string): string {
  const normalized = String(source || '').replace(/\\/g, '/')
  const graphMarker = 'assets/graphs/'
  const graphIndex = normalized.indexOf(graphMarker)
  if (graphIndex < 0) return source

  const runtimeStyle = Array.from(document.querySelectorAll<HTMLLinkElement>('link[href]'))
    .find(link => link.href.includes(STYLE_MARKER))
  if (runtimeStyle) {
    const siteRoot = runtimeStyle.href.split(STYLE_MARKER, 1)[0]
    return `${siteRoot}${normalized.slice(graphIndex)}`
  }

  const loader = Array.from(document.scripts).find(script => script.src.includes(SCRIPT_MARKER))
  if (!loader) return source
  const siteRoot = loader.src.split(SCRIPT_MARKER, 1)[0]
  return `${siteRoot}${normalized.slice(graphIndex)}`
}

export class WeConductGraphElement extends HTMLElement {
  static get observedAttributes(): string[] {
    return ['src', 'title']
  }

  private app: App<Element> | null = null
  private abortController: AbortController | null = null
  private requestToken = 0
  private fallback = ''
  private readonly state = shallowReactive<GraphRuntimeState>({
    instanceId: `wc-docs-flow-${++instanceSequence}`,
    title: 'WeConduct 图',
    graph: null,
    loading: false,
    error: '',
    fallback: '',
  })

  connectedCallback(): void {
    if (!this.fallback) this.fallback = this.textContent?.trim() || ''
    this.state.fallback = this.fallback
    this.state.title = this.currentTitle()
    this.mountVueApp()
    void this.load()
  }

  disconnectedCallback(): void {
    this.abortActiveRequest()
    this.app?.unmount()
    this.app = null
    this.replaceChildren()
  }

  attributeChangedCallback(name: string, oldValue: string | null, newValue: string | null): void {
    if (!this.isConnected || oldValue === newValue) return
    if (name === 'title') {
      this.state.title = this.currentTitle()
      return
    }
    if (name === 'src') {
      this.abortActiveRequest()
      void this.load()
    }
  }

  private mountVueApp(): void {
    if (this.app) return
    this.replaceChildren()
    const mountPoint = document.createElement('div')
    mountPoint.className = 'wc-graph-mount'
    this.append(mountPoint)
    this.app = createApp(GraphEmbed, { state: this.state })
    this.app.mount(mountPoint)
  }

  private async load(): Promise<void> {
    const source = this.getAttribute('src')
    if (!source) {
      this.state.loading = false
      this.state.graph = null
      this.state.error = '加载失败：缺少 src 属性。'
      return
    }

    this.abortActiveRequest()
    const controller = new AbortController()
    const token = ++this.requestToken
    this.abortController = controller
    this.state.loading = true
    this.state.error = ''
    this.state.graph = null

    try {
      const response = await fetch(resolveGraphSource(source), {
        cache: 'no-store',
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`加载失败：HTTP ${response.status}`)
      const graph = validateGraphPayload(await response.json())
      if (token !== this.requestToken) return
      this.state.graph = graph
    } catch (error) {
      if (controller.signal.aborted || token !== this.requestToken) return
      this.state.error = error instanceof Error ? error.message : '加载失败。'
    } finally {
      if (token === this.requestToken) this.state.loading = false
      if (this.abortController === controller) this.abortController = null
    }
  }

  private abortActiveRequest(): void {
    this.abortController?.abort()
    this.abortController = null
    this.requestToken += 1
  }

  private currentTitle(): string {
    return this.getAttribute('title') || 'WeConduct 图'
  }
}

export function registerWeConductGraph(): void {
  if (!customElements.get(ELEMENT_NAME)) {
    customElements.define(ELEMENT_NAME, WeConductGraphElement)
  }
}
