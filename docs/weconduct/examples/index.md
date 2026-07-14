---
product: weconduct
version: 0.8.1
doc_id: weconduct:examples:index
---

# 示例

本页汇总 WeConduct 0.8.1 当前已经存在的示例形态、校验边界和后续可下载项目的验收口径。

## 当前示例结构

- 现阶段公开可直接引用的是文档内嵌图示和 smoke 示例图，不是完整可下载项目包。
- 图示示例的实际资源位于 `docs/assets/graphs/smoke/flow-start.json`，并由 [`内嵌图示`](../reference/embedded-graphs.md) 页面直接加载。
- 当前示例主要用于说明节点连接、控制流和数据流，不替代真实项目模板。

## 图示与版本校验

- 当前文档示例必须满足 `graph-v1` 顶层结构。
- `root_metadata.graph_compatibility.built_with_app_version` 当前固定要求 `0.8.1`。
- 节点端口和节点 key 需要与 WeConduct 0.8.1 component manifest 对齐，否则示例在验证阶段就会失败。
- 如果示例图只是教学用途，也不能跳过这些校验；否则页面展示和后续导入预期会偏离真实行为。

## 当前 smoke 示例

- 当前 smoke 示例用于验证最基本的图加载路径、JSON 结构和前端图示组件是否工作。
- 建议先打开 [`内嵌图示`](../reference/embedded-graphs.md) 页面确认 smoke 示例能否正常加载，再扩展更复杂的教学图。

## 后续可下载项目的验收维度

- 当前仓库没有提供可下载项目示例，本页不伪造下载入口。
- 后续如果新增可下载项目，至少要验收：结构是否可打开、图数据是否通过 `graph-v1 / 0.8.1` 校验、节点依赖是否齐全、页面示例与文档说明是否一致。
- 如果示例包含外部资源，还要额外验收资源路径、运行前置条件和失败回退说明。

## 使用建议

- 先用当前 smoke 示例和图示参考验证文档链路。
- 需要演示完整业务流程时，再在后续任务中补更完整的示例项目和下载产物说明。
