---
product: weconduct
version: 0.9.0
doc_id: component-group:data-lists
---

# 列表处理

覆盖列表创建、读写、切片、排序与反转。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [创建列表](create-list.md) | `data.create_list` | 创建运行时列表。 |
| [列表追加](list-append.md) | `data.list_append` | 向运行时列表追加项。 |
| [列表扩展](list-extend.md) | `data.list_extend` | 用多个项扩展运行时列表。 |
| [列表读取](list-get.md) | `data.list_get` | 读取运行时列表项。 |
| [列表索引](list-index.md) | `data.list_index` | 查找运行时列表项索引。 |
| [列表插入](list-insert.md) | `data.list_insert` | 按索引插入运行时列表项。 |
| [列表长度](list-length.md) | `data.list_length` | 读取运行时列表长度。 |
| [列表移除](list-remove.md) | `data.list_remove` | 按值或索引移除运行时列表项。 |
| [列表反转](list-reverse.md) | `data.list_reverse` | 反转运行时列表。 |
| [列表写入](list-set.md) | `data.list_set` | 写入运行时列表项。 |
| [列表切片](list-slice.md) | `data.list_slice` | 对运行时列表进行切片。 |
| [列表排序](list-sort.md) | `data.list_sort` | 对运行时列表排序。 |

## 典型搭配

这类节点通常会按 `创建列表 → 列表追加 → 列表扩展 → 列表读取` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-lists.json" title="列表处理节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [创建列表](create-list.md) (`data.create_list`)
- [列表追加](list-append.md) (`data.list_append`)
- [列表扩展](list-extend.md) (`data.list_extend`)
- [列表读取](list-get.md) (`data.list_get`)
- [列表索引](list-index.md) (`data.list_index`)
- [列表插入](list-insert.md) (`data.list_insert`)
- [列表长度](list-length.md) (`data.list_length`)
- [列表移除](list-remove.md) (`data.list_remove`)
- [列表反转](list-reverse.md) (`data.list_reverse`)
- [列表写入](list-set.md) (`data.list_set`)
- [列表切片](list-slice.md) (`data.list_slice`)
- [列表排序](list-sort.md) (`data.list_sort`)
