---
product: weconduct
version: 0.8.1
doc_id: component:flow.start
---

# 开始

资源键：`flow.start`  
英文名：Start

## 功能说明

声明流程入口和初始变量。

该节点属于“流程与组件边界”。实现类型为 `core_atomic`，运行展开角色为 `flow:start`。

## 适用场景

在需要“开始”能力的流程中使用。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

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

输入：无显式输入端口。输出：`out`、`out:variables`。副作用：主要更新运行时数据。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/flow/flow-start.json" title="开始配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

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

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

节点成功后返回 `status = succeeded`，并可从 `out:variables` 或节点输出字段取得结果。

## 常见错误

端口不存在或关系层不匹配；输入类型与参数要求不一致。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[流程与组件边界](index.md)聚合页。
- [组件输入](input.md) (`component.input`)。
- [组件输出](output.md) (`component.output`)。
