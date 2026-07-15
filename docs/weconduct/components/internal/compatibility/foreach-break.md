---
product: weconduct
version: 0.8.1
doc_id: component:control.foreach_break
---

# 遍历中断

资源键：`control.foreach_break`  
英文名：Foreach Break

## 功能说明

条件满足时退出当前遍历循环。

该节点属于“兼容与内部节点”。实现类型为 `core_atomic`，运行展开角色为 `control:foreach_break`。

## 适用场景

构造分支、循环、并行或可靠性控制结构，由编译器管理控制出口和运行状态。

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
| `condition` | `string` | 否 | `"true"` | `default` |
| `level` | `integer` | 否 | `1` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`。副作用：改变后续控制路径。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/internal/control-foreach-break.json" title="遍历中断配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "condition": "true",
  "level": 1
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

条件、汇合或尝试状态确定后，从对应控制输出继续。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致；控制出口未连接、表达式无效或循环/重试边界配置不合法。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

该节点仅用于兼容或内部图加载，不在普通组件库显示，不建议用于新流程；不能从普通组件库直接添加；控制节点必须按端口语义成对组织，不能用普通执行节点替代结构边界；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[兼容与内部节点](index.md)聚合页。
- [跳转步骤](jump-to-step.md) (`control.jump_to_step`)。
- [结束遍历](end-foreach.md) (`control.end_foreach`)。
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)。
- [调用子图](call-subgraph.md) (`graph.call_subgraph`)。
- [调用蓝图](call-blueprint.md) (`call_blueprint`)。
