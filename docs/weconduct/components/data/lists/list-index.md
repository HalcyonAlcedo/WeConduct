---
product: weconduct
version: 0.8.1
doc_id: component:data.list_index
---

# 列表索引

资源键：`data.list_index`　|　英文名：List Index
## 功能说明

查找运行时列表项索引。

## 什么时候用

对运行时变量中的列表执行定位、读取或变更；索引从 `0` 开始。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:value` | input | `data` | `in.value` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `variable_name` | `string` | 是 | `""` | `default` |
| `value` | `any` | 否 | `null` | `default` |
| `output_variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:value`。输出端口：`out`、`out:value`。对外影响：读取原列表并输出查询结果。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/data/data-list-index.json" title="列表索引配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "variable_name": "result",
  "value": null,
  "output_variable_name": "result"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

列表操作完成后返回结果；变更类节点会保留更新后的原列表。

## 常见问题

缺少必填参数：`variable_name`、`output_variable_name`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；目标变量不是列表、索引越界或待查找值不存在。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

切片的 `end` 遵循不包含结束位置的列表切片语义；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[列表处理](index.md)聚合页查看更多同类节点。
- [创建列表](create-list.md) (`data.create_list`)。
- [列表追加](list-append.md) (`data.list_append`)。
- [列表扩展](list-extend.md) (`data.list_extend`)。
- [列表读取](list-get.md) (`data.list_get`)。
- [列表写入](list-set.md) (`data.list_set`)。
