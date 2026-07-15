---
product: weconduct
version: 0.8.1
doc_id: component:call_blueprint
---

# 调用蓝图

资源键：`call_blueprint`  
英文名：Call Blueprint

## 功能说明

按 blueprint_id 调用可复用组件图。

该节点属于“兼容与内部节点”。实现类型为 `core_atomic`，运行展开角色为 `action:call_blueprint`。

## 适用场景

定义自定义组件边界或调用已有子图；输入输出必须与组件 schema 一致。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `blueprint_id` | `string` | 是 | `""` | `default` |
| `inputs` | `object` | 否 | `{}` | `default` |
| `outputs` | `object` | 否 | `{}` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：在父图与子图之间映射变量和控制上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/internal/call-blueprint.json" title="调用蓝图配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "blueprint_id": "example",
  "inputs": {},
  "outputs": {}
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

子图完成后按输出映射把结果返回调用方。

## 常见错误

缺少必填参数：`blueprint_id`；端口不存在或关系层不匹配；输入类型与参数要求不一致；子图不存在、schema 不匹配或输入输出映射引用无效。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

该节点仅用于兼容或内部图加载，不在普通组件库显示，不建议用于新流程；不能从普通组件库直接添加；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[兼容与内部节点](index.md)聚合页。
- [跳转步骤](jump-to-step.md) (`control.jump_to_step`)。
- [结束遍历](end-foreach.md) (`control.end_foreach`)。
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)。
- [遍历中断](foreach-break.md) (`control.foreach_break`)。
- [调用子图](call-subgraph.md) (`graph.call_subgraph`)。
