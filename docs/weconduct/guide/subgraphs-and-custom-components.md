---
product: weconduct
version: 0.9.0
doc_id: weconduct:guide:subgraphs-and-custom-components
---

# 子图与自定义组件

## 自定义组件边界

自定义节点图必须且只能包含一个 `component.input` 和一个 `component.output`。它们只允许出现在自定义组件图中，不能放到主图。

- `component.input.node_config.inputs` 定义输入 schema。
- `component.output.node_config.outputs` 定义输出 schema。
- schema 字段名必须非空，字段定义必须是对象，并声明支持的类型和必填状态。

保存自定义图时，WeConduct 从边界节点派生资源的输入/输出 schema。调用节点的映射必须覆盖必填输入，且不能引用未知输出。

## 变量作用域

默认情况下，组件使用独立变量上下文。只有在输入边界明确启用 `share_parent_variables`（兼容值 `variable_scope = "shared"`）时，子上下文才共享父变量；这会增加耦合，应优先通过 schema 传值。

组件仍继承必要的运行设置、项目目录和资源路径，但不能假设能访问调用方任意节点内部状态。未到达 `component.output` 会产生 `component.output_unreached`。

## 子图兼容调用

`graph.call_subgraph` 是兼容/内部节点，用 `subgraph_id` 指向 `subgraph_resource`，并配置输入、输出映射。它会检查资源存在、启用状态、schema 类型、递归调用和调用深度。

新建可复用能力时优先使用可见的自定义组件工作流；兼容节点主要用于加载历史项目。
