---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:component-library
---

# 组件库

0.9.1 冻结快照包含 135 个内置节点，其中 129 个在组件库可见，6 个仅用于兼容或内部图加载。

网络自动化、输入与消息是 0.9.1 新增的两个能力分组。网络分组包含 HTTP、GraphQL Query/Mutation、SSE、WebSocket、上传、下载、响应断言和批量请求；输入与消息分组包含多字段待输入和运行时消息发布。

## 查找组件

组件库按能力域和类别组织。可以按中文名称、英文名称或资源键搜索，例如 `写入变量`、`Set Variable`、`data.set_variable`。

点击组件会把节点加入当前图；拖放可以指定画布位置。加入后，实际端口和默认配置来自该组件的节点草稿，不由前端临时猜测。

## 可见与兼容节点

- `component_library_visible = true`：正常显示，可用于新流程。
- `compatibility_only = true`：不在普通组件库展示，仅为旧项目、旧蓝图或内部控制结构保留。

兼容节点仅用于旧项目迁移，不会出现在普通组件库中。需要了解全部节点时，请查看[内置节点参考](../components/index.md)。

## 添加失败

常见原因包括：当前图只读、主图已有 `flow.start`、把 `component.input` / `component.output` 加到主图，或当前自定义图不允许主流程入口。查看 toast 和 **输出 → 诊断** 获取具体原因。
