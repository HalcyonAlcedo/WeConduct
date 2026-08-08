---
product: weconduct
version: 0.9.0
doc_id: component:flow.start
---

# 开始

资源键：`flow.start`　|　英文名：Start
## 功能说明

声明流程入口和初始变量。

## 什么时候用

当你需要 开始 功能时使用。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `out` | output | `control` | `out.control` |
| `out:variables` | output | `data` | `out.variables` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `initial_variables` | `object` | 否 | `{}` | `key_value_map` |
| `browser_config` | `object` | 否 | `{"headless": true, "slow_mo_ms": 0}` | `object` |

## 输入、输出与副作用

输入端口：没有显式输入端口。输出端口：`out`、`out:variables`。对外影响：更新运行时数据。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/flow/flow-start.json" title="开始配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "initial_variables": {},
  "browser_config": {
    "headless": true,
    "slow_mo_ms": 0
  }
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

节点执行成功后，状态为 `succeeded`。你可以从 `out:variables` 端口或节点输出字段获取结果。

## 常见问题

端口名称写错或关系层不匹配；输入值的类型与参数要求不一致。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[流程与组件边界](index.md)聚合页查看更多同类节点。
- [组件输入](input.md) (`component.input`)。
- [组件输出](output.md) (`component.output`)。
