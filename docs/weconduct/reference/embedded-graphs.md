---
product: weconduct
version: 0.8.1
doc_id: weconduct:reference:embedded-graphs
---

# 内嵌图示

`<weconduct-graph>` 用于在文档里直接嵌入教学图，适合解释节点端口、控制流和数据流，不替代编辑器。

## 属性

- `src`：指向 `docs/assets/graphs/**/*.json` 的相对 URL。页面内建议使用相对当前 Markdown 的路径。
- `title`：图示标题，会显示在组件头部，也作为加载和错误状态的上下文说明。

## JSON 要求

- 文件必须是 `graph-v1` 顶层结构，至少包含 `graph_model_id`、`graph_schema_version`、`nodes`、`edges`、`root_metadata`。
- `root_metadata.graph_compatibility.built_with_app_version` 当前固定要求 `0.8.1`。
- 教学图目前只支持 `control` 和 `data` 两类边；`observe` 边会被验证器拒绝。
- 节点需要真实 `position`，节点端口必须与 WeConduct 0.8.1 组件 manifest 契约一致。
- 教学图建议最多 20 个节点，超出后请拆成多张图，避免移动端阅读和演示交互失控。

## 可访问性与回退

- 标签体内容会作为可访问回退文本；当加载或验证失败时，组件会直接显示这段文本。
- 按钮提供 `title` 与 `aria-label`，支持 `fit`、放大、缩小、全屏。

## 示例

下面示例使用相对 URL 引用 smoke fixture：

<weconduct-graph src="../../assets/graphs/smoke/flow-start.json" title="开始节点">可访问回退文本：如果图示加载失败，请直接阅读本页对 flow.start 的说明。</weconduct-graph>
