---
product: weconduct
version: 0.8.1
doc_id: component-group:files-text-and-csv
---

# 文本与 CSV 文件

覆盖文本文件和 CSV 读取写入。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取 CSV 单元格](read-csv-cell.md) | `file.read_csv_cell` | 读取 CSV 单元格值。 |
| [读取 CSV 行](read-csv-row.md) | `file.read_csv_row` | 读取 CSV 行数据。 |
| [读取 CSV 表](read-csv-table.md) | `file.read_csv_table` | 读取 CSV 表数据。 |
| [读取文本文件](read-text-file.md) | `file.read_text_file` | 读取文本文件内容。 |
| [写入文本文件](write-text-file.md) | `file.write_text_file` | 写入文本文件内容。 |

## 常见组合

可从 `读取 CSV 单元格 → 读取 CSV 行 → 读取 CSV 表 → 读取文本文件` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/files-text-and-csv.json" title="文本与 CSV 文件节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [读取 CSV 单元格](read-csv-cell.md) (`file.read_csv_cell`)：组件库可见。
- [读取 CSV 行](read-csv-row.md) (`file.read_csv_row`)：组件库可见。
- [读取 CSV 表](read-csv-table.md) (`file.read_csv_table`)：组件库可见。
- [读取文本文件](read-text-file.md) (`file.read_text_file`)：组件库可见。
- [写入文本文件](write-text-file.md) (`file.write_text_file`)：组件库可见。
