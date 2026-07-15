---
product: weconduct
version: 0.8.1
doc_id: component:data.decrement_variable
---

# 变量递减

资源键：`data.decrement_variable`  
英文名：Decrement Variable

## 功能说明

递减数值型运行时变量。

该节点属于“变量读写”。实现类型为 `builtin_custom_component`，运行展开角色为 `action:decrement_variable`。

## 适用场景

在流程中读取、写入或转换运行时变量，并把结果交给后续节点。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `variable_name` | `string` | 是 | `""` | `default` |
| `step` | `integer` | 否 | `1` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`、`out:value`。副作用：按 `variable_name` 或节点语义读取或更新运行时变量。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/data/data-decrement-variable.json" title="变量递减配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "variable_name": "result",
  "step": 1
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

操作成功后返回处理结果；声明输出变量时同步写入运行时上下文。

## 常见错误

缺少必填参数：`variable_name`；端口不存在或关系层不匹配；输入类型与参数要求不一致；变量不存在、值类型不兼容或表达式/正则格式无效。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[变量读写](index.md)聚合页。
- [写入变量](set-variable.md) (`data.set_variable`)。
- [读取变量](get-variable.md) (`data.get_variable`)。
- [批量写入变量](set-variables-batch.md) (`data.set_variables_batch`)。
- [变量递增](increment-variable.md) (`data.increment_variable`)。
