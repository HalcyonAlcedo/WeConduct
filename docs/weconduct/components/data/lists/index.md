---
product: weconduct
version: 0.8.1
doc_id: component-group:data-lists
---

# 列表处理

覆盖列表创建、读写、切片、排序与反转。

## 如何选择

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

## 常见组合

可从 `创建列表 → 列表追加 → 列表扩展 → 列表读取` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/data-lists.json" title="列表处理节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [创建列表](create-list.md) (`data.create_list`)：组件库可见。
- [列表追加](list-append.md) (`data.list_append`)：组件库可见。
- [列表扩展](list-extend.md) (`data.list_extend`)：组件库可见。
- [列表读取](list-get.md) (`data.list_get`)：组件库可见。
- [列表索引](list-index.md) (`data.list_index`)：组件库可见。
- [列表插入](list-insert.md) (`data.list_insert`)：组件库可见。
- [列表长度](list-length.md) (`data.list_length`)：组件库可见。
- [列表移除](list-remove.md) (`data.list_remove`)：组件库可见。
- [列表反转](list-reverse.md) (`data.list_reverse`)：组件库可见。
- [列表写入](list-set.md) (`data.list_set`)：组件库可见。
- [列表切片](list-slice.md) (`data.list_slice`)：组件库可见。
- [列表排序](list-sort.md) (`data.list_sort`)：组件库可见。
