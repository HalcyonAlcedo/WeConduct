---
product: weconduct
version: 0.8.1
doc_id: component-group:excel-read
---

# Excel 读取

覆盖 Excel 单元格、行和表读取。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取 Excel 单元格](read-cell.md) | `excel.read_cell` | 读取 Excel 单元格值。 |
| [读取 Excel 行](read-row.md) | `excel.read_row` | 读取 Excel 行数据。 |
| [读取 Excel 表](read-table.md) | `excel.read_table` | 读取 Excel 表数据。 |

## 典型搭配

这类节点通常会按 `读取 Excel 单元格 → 读取 Excel 行 → 读取 Excel 表` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/excel-read.json" title="Excel 读取节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [读取 Excel 单元格](read-cell.md) (`excel.read_cell`)
- [读取 Excel 行](read-row.md) (`excel.read_row`)
- [读取 Excel 表](read-table.md) (`excel.read_table`)
