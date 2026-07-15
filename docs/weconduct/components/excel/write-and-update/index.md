---
product: weconduct
version: 0.8.1
doc_id: component-group:excel-write-and-update
---

# Excel 写入与更新

覆盖 Excel 写入、整表输出与批量更新。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [批量更新 Excel](update-batch.md) | `excel.update_batch` | 按条件批量更新 Excel 行。 |
| [更新 Excel 单元格](update-cells.md) | `excel.update_cells` | 更新多个 Excel 单元格。 |
| [写入 Excel 单元格](write-cell.md) | `excel.write_cell` | 写入 Excel 单元格的值。 |
| [写入 Excel 文件](write-file.md) | `excel.write_file` | 创建或追加 Excel 文件。 |
| [写入 Excel 行](write-row.md) | `excel.write_row` | 写入 Excel 行数据。 |
| [写入 Excel 表](write-table.md) | `excel.write_table` | 写入 Excel 表数据。 |

## 常见组合

可从 `批量更新 Excel → 更新 Excel 单元格 → 写入 Excel 单元格 → 写入 Excel 文件` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/excel-write-and-update.json" title="Excel 写入与更新节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [批量更新 Excel](update-batch.md) (`excel.update_batch`)：组件库可见。
- [更新 Excel 单元格](update-cells.md) (`excel.update_cells`)：组件库可见。
- [写入 Excel 单元格](write-cell.md) (`excel.write_cell`)：组件库可见。
- [写入 Excel 文件](write-file.md) (`excel.write_file`)：组件库可见。
- [写入 Excel 行](write-row.md) (`excel.write_row`)：组件库可见。
- [写入 Excel 表](write-table.md) (`excel.write_table`)：组件库可见。
