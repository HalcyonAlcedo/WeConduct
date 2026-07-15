---
product: weconduct
version: 0.8.1
doc_id: component-group:excel-read
---

# Excel 读取

覆盖 Excel 单元格、行和表读取。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取 Excel 单元格](read-cell.md) | `excel.read_cell` | 读取 Excel 单元格值。 |
| [读取 Excel 行](read-row.md) | `excel.read_row` | 读取 Excel 行数据。 |
| [读取 Excel 表](read-table.md) | `excel.read_table` | 读取 Excel 表数据。 |

## 常见组合

可从 `读取 Excel 单元格 → 读取 Excel 行 → 读取 Excel 表` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/excel-read.json" title="Excel 读取节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [读取 Excel 单元格](read-cell.md) (`excel.read_cell`)：组件库可见。
- [读取 Excel 行](read-row.md) (`excel.read_row`)：组件库可见。
- [读取 Excel 表](read-table.md) (`excel.read_table`)：组件库可见。
