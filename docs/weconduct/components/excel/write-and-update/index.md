---
product: weconduct
version: 0.9.1
doc_id: component-group:excel-write-and-update
---

# Excel 写入与更新

覆盖 Excel 写入、整表输出与批量更新。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [批量更新 Excel](update-batch.md) | `excel.update_batch` | 按条件批量更新 Excel 行。 |
| [更新 Excel 单元格](update-cells.md) | `excel.update_cells` | 更新多个 Excel 单元格。 |
| [写入 Excel 单元格](write-cell.md) | `excel.write_cell` | 写入 Excel 单元格的值。 |
| [写入 Excel 文件](write-file.md) | `excel.write_file` | 创建或追加 Excel 文件。 |
| [写入 Excel 行](write-row.md) | `excel.write_row` | 写入 Excel 行数据。 |
| [写入 Excel 表](write-table.md) | `excel.write_table` | 写入 Excel 表数据。 |

## 典型搭配

这类节点通常会按 `批量更新 Excel → 更新 Excel 单元格 → 写入 Excel 单元格 → 写入 Excel 文件` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/excel-write-and-update.json" title="Excel 写入与更新节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [批量更新 Excel](update-batch.md) (`excel.update_batch`)
- [更新 Excel 单元格](update-cells.md) (`excel.update_cells`)
- [写入 Excel 单元格](write-cell.md) (`excel.write_cell`)
- [写入 Excel 文件](write-file.md) (`excel.write_file`)
- [写入 Excel 行](write-row.md) (`excel.write_row`)
- [写入 Excel 表](write-table.md) (`excel.write_table`)
