(function registerWeConductGraph() {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const SUPPORTED_LAYERS = new Set(["control", "data"]);

  function readCompactConfig(nodeConfig) {
    if (!nodeConfig || typeof nodeConfig !== "object") {
      return "{}";
    }
    const keys = Object.keys(nodeConfig).slice(0, 3);
    if (keys.length === 0) {
      return "{}";
    }
    const compact = {};
    for (const key of keys) {
      compact[key] = nodeConfig[key];
    }
    return JSON.stringify(compact);
  }

  function validateGraphPayload(graph) {
    if (!graph || typeof graph !== "object") {
      throw new Error("Validation failed: graph root must be an object.");
    }
    if (graph.graph_schema_version !== "graph-v1") {
      throw new Error("Validation failed: graph_schema_version must be graph-v1.");
    }
    if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new Error("Validation failed: nodes and edges must be arrays.");
    }
    for (const [index, node] of graph.nodes.entries()) {
      if (!node || typeof node !== "object") {
        throw new Error(`Validation failed: nodes[${index}] must be an object.`);
      }
      if (!node.position || typeof node.position.x !== "number" || typeof node.position.y !== "number") {
        throw new Error(`Validation failed: nodes[${index}].position is required.`);
      }
      if (!Array.isArray(node.ports)) {
        throw new Error(`Validation failed: nodes[${index}].ports must be an array.`);
      }
    }
    return graph;
  }

  class WeConductGraphElement extends HTMLElement {
    static get observedAttributes() {
      return ["src", "title"];
    }

    constructor() {
      super();
      this._fallbackText = "";
      this._state = {
        scale: 1,
        translateX: 0,
        translateY: 0,
        minScale: 0.5,
        maxScale: 2.5,
        pointerId: null,
        dragOriginX: 0,
        dragOriginY: 0,
        startTranslateX: 0,
        startTranslateY: 0,
        isFullscreen: false,
      };
    }

    connectedCallback() {
      if (!this._fallbackText) {
        this._fallbackText = this.textContent.trim();
      }
      this.classList.add("wc-graph-host");
      this.load();
      document.addEventListener("fullscreenchange", this._onFullscreenChange);
    }

    disconnectedCallback() {
      document.removeEventListener("fullscreenchange", this._onFullscreenChange);
    }

    attributeChangedCallback() {
      if (this.isConnected) {
        this.load();
      }
    }

    _onFullscreenChange = () => {
      this._state.isFullscreen = document.fullscreenElement === this;
      this.updateTransform();
    };

    async load() {
      const src = this.getAttribute("src");
      const title = this.getAttribute("title") || "WeConduct 图";
      if (!src) {
        this.renderError("加载失败：缺少 src 属性。");
        return;
      }

      this.renderLoading(title);

      try {
        const response = await fetch(src, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`加载失败：HTTP ${response.status}`);
        }
        const graph = validateGraphPayload(await response.json());
        this.renderGraph(graph, title);
      } catch (error) {
        const message = error instanceof Error ? error.message : "加载失败。";
        this.renderError(message);
      }
    }

    renderLoading(title) {
      this.innerHTML = "";
      const shell = this.createShell(title);
      const status = document.createElement("p");
      status.className = "wc-graph-status";
      status.textContent = "正在加载图示...";
      shell.viewport.append(status);
      this.append(shell.root);
    }

    renderError(message) {
      this.innerHTML = "";
      const shell = this.createShell(this.getAttribute("title") || "WeConduct 图");
      const panel = document.createElement("div");
      panel.className = "wc-graph-error";
      const summary = document.createElement("p");
      summary.textContent = message;
      panel.append(summary);
      if (this._fallbackText) {
        const fallback = document.createElement("p");
        fallback.className = "wc-graph-fallback";
        fallback.textContent = this._fallbackText;
        panel.append(fallback);
      }
      shell.viewport.append(panel);
      this.append(shell.root);
    }

    renderGraph(graph, title) {
      this.innerHTML = "";
      const shell = this.createShell(title);
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 960 540");
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
      svg.classList.add("wc-graph-svg");

      const edgeLayer = document.createElementNS(SVG_NS, "g");
      edgeLayer.setAttribute("data-layer", "edges");
      const nodeLayer = document.createElement("div");
      nodeLayer.className = "wc-graph-nodes";

      const bounds = this.calculateBounds(graph.nodes);
      for (const edge of graph.edges.filter((item) => SUPPORTED_LAYERS.has(item.relation_layer))) {
        const source = graph.nodes.find((item) => item.node_id === edge.from_node_id);
        const target = graph.nodes.find((item) => item.node_id === edge.to_node_id);
        if (!source || !target) {
          continue;
        }
        edgeLayer.append(this.createEdge(edge, source, target));
      }
      svg.append(edgeLayer);

      for (const node of graph.nodes) {
        nodeLayer.append(this.createNode(node));
      }

      shell.canvas.append(svg, nodeLayer);
      shell.viewport.append(shell.canvas);
      this.append(shell.root);

      this._canvas = shell.canvas;
      this._shell = shell.root;
      this._graphBounds = bounds;
      this.installInteractionHandlers(shell.viewport);
      this.fitToGraph();
    }

    createShell(title) {
      const root = document.createElement("section");
      root.className = "wc-graph";

      const header = document.createElement("div");
      header.className = "wc-graph-header";
      const heading = document.createElement("p");
      heading.className = "wc-graph-title";
      heading.textContent = title;
      const controls = document.createElement("div");
      controls.className = "wc-graph-controls";
      controls.append(
        this.createControlButton("Fit", "⤢", () => this.fitToGraph()),
        this.createControlButton("Zoom in", "+", () => this.nudgeScale(0.18)),
        this.createControlButton("Zoom out", "−", () => this.nudgeScale(-0.18)),
        this.createControlButton("Fullscreen", "⛶", () => this.toggleFullscreen())
      );
      header.append(heading, controls);

      const viewport = document.createElement("div");
      viewport.className = "wc-graph-viewport";
      const canvas = document.createElement("div");
      canvas.className = "wc-graph-canvas";

      root.append(header, viewport);
      return { root, viewport, canvas };
    }

    createControlButton(label, symbol, onClick) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "wc-graph-control";
      button.textContent = symbol;
      button.title = label;
      button.setAttribute("aria-label", label);
      button.addEventListener("click", onClick);
      return button;
    }

    createNode(node) {
      const element = document.createElement("article");
      element.className = "wc-graph-node";
      element.style.left = `${node.position.x}px`;
      element.style.top = `${node.position.y}px`;

      const title = document.createElement("h3");
      title.className = "wc-graph-node-title";
      title.textContent = node.display_name || node.node_kind || node.node_id;
      const kind = document.createElement("p");
      kind.className = "wc-graph-node-kind";
      kind.textContent = node.node_kind || "unknown";
      const config = document.createElement("p");
      config.className = "wc-graph-node-config";
      config.textContent = readCompactConfig(node.node_config);
      const ports = document.createElement("ul");
      ports.className = "wc-graph-port-list";

      for (const port of node.ports) {
        const item = document.createElement("li");
        item.className = `wc-graph-port wc-graph-port-${port.relation_layer}`;
        item.textContent = `${port.port_id} · ${port.direction}`;
        ports.append(item);
      }

      element.append(title, kind, config, ports);
      return element;
    }

    createEdge(edge, source, target) {
      const path = document.createElementNS(SVG_NS, "path");
      const x1 = source.position.x + 176;
      const y1 = source.position.y + 54;
      const x2 = target.position.x;
      const y2 = target.position.y + 54;
      const curve = Math.max(64, Math.abs(x2 - x1) * 0.5);
      path.setAttribute("d", `M ${x1} ${y1} C ${x1 + curve} ${y1}, ${x2 - curve} ${y2}, ${x2} ${y2}`);
      path.setAttribute("fill", "none");
      path.setAttribute("class", `wc-graph-edge wc-graph-edge-${edge.relation_layer}`);
      return path;
    }

    calculateBounds(nodes) {
      const xs = nodes.map((node) => node.position.x);
      const ys = nodes.map((node) => node.position.y);
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs) + 176,
        minY: Math.min(...ys),
        maxY: Math.max(...ys) + 112,
      };
    }

    installInteractionHandlers(viewport) {
      viewport.onpointerdown = (event) => {
        this._state.pointerId = event.pointerId;
        this._state.dragOriginX = event.clientX;
        this._state.dragOriginY = event.clientY;
        this._state.startTranslateX = this._state.translateX;
        this._state.startTranslateY = this._state.translateY;
        viewport.setPointerCapture(event.pointerId);
      };
      viewport.onpointermove = (event) => {
        if (this._state.pointerId !== event.pointerId) {
          return;
        }
        this._state.translateX = this._state.startTranslateX + (event.clientX - this._state.dragOriginX);
        this._state.translateY = this._state.startTranslateY + (event.clientY - this._state.dragOriginY);
        this.updateTransform();
      };
      viewport.onpointerup = (event) => {
        if (this._state.pointerId === event.pointerId) {
          this._state.pointerId = null;
          viewport.releasePointerCapture(event.pointerId);
        }
      };
      viewport.addEventListener(
        "wheel",
        (event) => {
          event.preventDefault();
          const delta = event.deltaY < 0 ? 0.1 : -0.1;
          this.nudgeScale(delta);
        },
        { passive: false }
      );
    }

    nudgeScale(delta) {
      this._state.scale = Math.max(
        this._state.minScale,
        Math.min(this._state.maxScale, this._state.scale + delta)
      );
      this.updateTransform();
    }

    fitToGraph() {
      if (!this._graphBounds || !this._shell) {
        return;
      }
      const viewport = this._shell.querySelector(".wc-graph-viewport");
      if (!viewport) {
        return;
      }
      const width = viewport.clientWidth || 960;
      const height = viewport.clientHeight || 540;
      const graphWidth = Math.max(320, this._graphBounds.maxX - this._graphBounds.minX + 120);
      const graphHeight = Math.max(180, this._graphBounds.maxY - this._graphBounds.minY + 120);
      const scale = Math.min(width / graphWidth, height / graphHeight, 1.25);
      this._state.scale = Math.max(this._state.minScale, Math.min(this._state.maxScale, scale));
      this._state.translateX =
        width / 2 - ((this._graphBounds.minX + this._graphBounds.maxX) / 2) * this._state.scale;
      this._state.translateY =
        height / 2 - ((this._graphBounds.minY + this._graphBounds.maxY) / 2) * this._state.scale;
      this.updateTransform();
    }

    updateTransform() {
      if (!this._canvas) {
        return;
      }
      this._canvas.style.transform = `translate(${this._state.translateX}px, ${this._state.translateY}px) scale(${this._state.scale})`;
    }

    async toggleFullscreen() {
      if (document.fullscreenElement === this) {
        await document.exitFullscreen();
        return;
      }
      if (this.requestFullscreen) {
        await this.requestFullscreen();
        this._state.isFullscreen = true;
      }
    }
  }

  if (!customElements.get("weconduct-graph")) {
    customElements.define("weconduct-graph", WeConductGraphElement);
  }
})();
