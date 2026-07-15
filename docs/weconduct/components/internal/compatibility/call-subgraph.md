---
product: weconduct
version: 0.8.1
doc_id: component:graph.call_subgraph
---

# 调用子图

资源键：`graph.call_subgraph`　|　英文名：Call Subgraph
## 功能说明

按 subgraph_id 调用可复用子图资源。

## 什么时候用

定义自定义组件边界或调用已有子图；输入输出必须与组件 schema 一致。

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
| `subgraph_id` | `string` | 是 | `""` | `default` |
| `inputs` | `object` | 否 | `{}` | `default` |
| `outputs` | `object` | 否 | `{}` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`。对外影响：在父图与子图之间映射变量和控制上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/internal/graph-call-subgraph.json" title="调用子图配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "subgraph_id": "example",
  "inputs": {},
  "outputs": {}
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

子图完成后按输出映射把结果返回调用方。

## 常见问题

缺少必填参数：`subgraph_id`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；子图不存在、schema 不匹配或输入输出映射引用无效。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

该节点仅用于兼容旧版项目或内部图加载，不会出现在普通组件库中，不建议在新流程中使用；该节点不能从普通组件库直接添加；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[兼容与内部节点](index.md)聚合页查看更多同类节点。
- [跳转步骤](jump-to-step.md) (`control.jump_to_step`)。
- [结束遍历](end-foreach.md) (`control.end_foreach`)。
- [遍历继续](foreach-continue.md) (`control.foreach_continue`)。
- [遍历中断](foreach-break.md) (`control.foreach_break`)。
- [调用蓝图](call-blueprint.md) (`call_blueprint`)。
