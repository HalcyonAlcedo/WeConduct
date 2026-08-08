---
product: weconduct
version: 0.9.0
doc_id: component:control.jump_to_step
---

# 跳转步骤

资源键：`control.jump_to_step`　|　英文名：Jump To Step
## 功能说明

跳转到目标步骤。

## 什么时候用

构造分支、循环、并行或可靠性控制结构，由编译器管理控制出口和运行状态。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `target_node_id` | `string` | 是 | `""` | `default` |
| `target_step` | `any` | 否 | `null` | `default` |
| `condition` | `string` | 否 | `"true"` | `default` |
| `max_jumps` | `integer` | 否 | `-1` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：改变后续执行路径。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/internal/control-jump-to-step.json" title="跳转步骤配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "target_node_id": "example",
  "target_step": null,
  "condition": "true",
  "max_jumps": -1
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

条件、汇合或尝试状态确定后，从对应控制输出继续。

## 常见问题

缺少必填参数：`target_node_id`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；控制出口未连接、表达式无效或循环/重试边界配置不合法。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

该节点仅用于兼容旧版项目或内部图加载，不会出现在普通组件库中，不建议在新流程中使用；该节点不能从普通组件库直接添加；控制节点必须按端口语义成对组织，不能用普通执行节点替代结构边界；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[兼容与内部节点](index.md)聚合页查看更多同类节点。
- [结束遍历](end-foreach.md) (`control.end_foreach`)。
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)。
- [遍历中断](foreach-break.md) (`control.foreach_break`)。
- [调用子图](call-subgraph.md) (`graph.call_subgraph`)。
- [调用蓝图](call-blueprint.md) (`call_blueprint`)。
