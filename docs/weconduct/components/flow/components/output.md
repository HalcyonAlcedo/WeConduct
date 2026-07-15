---
product: weconduct
version: 0.8.1
doc_id: component:component.output
---

# 组件输出

资源键：`component.output`  
英文名：Component Output

## 功能说明

在自定义节点图中声明正式组件输出边界。

该节点属于“流程与组件边界”。实现类型为 `core_atomic`，运行展开角色为 `component:output`。

## 适用场景

定义自定义组件边界或调用已有子图；输入输出必须与组件 schema 一致。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `outputs` | `object` | 否 | `{}` | `component_outputs` |

## 输入、输出与副作用

输入：`in`。输出：无显式输出端口。副作用：在父图与子图之间映射变量和控制上下文。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/flow/component-output.json" title="组件输出配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "outputs": {}
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

子图完成后按输出映射把结果返回调用方。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致；子图不存在、schema 不匹配或输入输出映射引用无效。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[流程与组件边界](index.md)聚合页。
- [开始](start.md) (`flow.start`)。
- [组件输入](input.md) (`component.input`)。
