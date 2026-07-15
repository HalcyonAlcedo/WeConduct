---
product: weconduct
version: 0.8.1
doc_id: component:data.list_remove
---

# 列表移除

资源键：`data.list_remove`
英文名：List Remove

## 功能说明

按值或索引移除运行时列表项。

该节点属于“列表处理”。实现类型为 `builtin_custom_component`，运行展开角色为 `action:list_remove`。

## 适用场景

对运行时变量中的列表执行定位、读取或变更；索引从 `0` 开始。

## 前置条件与权限

不要求额外程序权限；仍需满足图结构、输入类型和项目资源约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:index` | input | `data` | `in.index` |
| `in:value` | input | `data` | `in.value` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `variable_name` | `string` | 是 | `""` | `default` |
| `index` | `integer` | 否 | `null` | `default` |
| `value` | `any` | 否 | `null` | `default` |

## 输入、输出与副作用

输入：`in`、`in:index`、`in:value`。输出：`out`、`out:value`。副作用：直接更新原列表变量。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/data/data-list-remove.json" title="列表移除配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "variable_name": "result",
  "index": null,
  "value": null
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

列表操作完成后返回结果；变更类节点会保留更新后的原列表。

## 常见错误

缺少必填参数：`variable_name`；端口不存在或关系层不匹配；输入类型与参数要求不一致；目标变量不是列表、索引越界或待查找值不存在。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

切片的 `end` 遵循不包含结束位置的列表切片语义；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[列表处理](index.md)聚合页。
- [创建列表](create-list.md) (`data.create_list`)。
- [列表追加](list-append.md) (`data.list_append`)。
- [列表扩展](list-extend.md) (`data.list_extend`)。
- [列表读取](list-get.md) (`data.list_get`)。
- [列表写入](list-set.md) (`data.list_set`)。
