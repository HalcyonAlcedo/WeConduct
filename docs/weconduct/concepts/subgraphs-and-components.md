---
product: weconduct
version: 0.8.1
doc_id: weconduct:concepts:subgraphs-components
---

# 子图与自定义组件

WeConduct 可以把图封装为可复用资源。边界由 `component.input` 和 `component.output` 节点声明，而不是任意把主图中的局部连线当成函数。

## 输入与输出边界

- `component.input` 定义组件接收的字段和类型。
- `component.output` 定义组件对调用方提供的字段和类型。
- 调用时输入映射和输出映射必须与 schema 一致。

缺少必填输入、映射未知输出或类型不匹配时，会返回 `component.input_mapping_invalid` 或 `component.output_mapping_invalid`。

## 子图资源

子图资源保存来源图、输入 schema 和输出 schema。兼容调用节点 `graph.call_subgraph` 需要 `subgraph_id`，并检查资源是否存在、是否启用、递归调用和最大调用深度。

## 上下文

组件运行使用子运行上下文，并从父上下文取得允许共享的运行设置、项目目录和变量。不要假设组件可以无条件访问调用方的所有内部节点状态。

自定义组件适合稳定、可复用的业务步骤；只使用一次的简单顺序流程通常保留在主图更容易维护。
