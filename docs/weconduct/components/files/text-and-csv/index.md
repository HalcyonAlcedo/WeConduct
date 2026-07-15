---
product: weconduct
version: 0.8.1
doc_id: component-group:files-text-and-csv
---

# 文本与 CSV 文件

覆盖文本文件和 CSV 读取写入。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [读取 CSV 单元格](read-csv-cell.md) | `file.read_csv_cell` | 读取 CSV 单元格值。 |
| [读取 CSV 行](read-csv-row.md) | `file.read_csv_row` | 读取 CSV 行数据。 |
| [读取 CSV 表](read-csv-table.md) | `file.read_csv_table` | 读取 CSV 表数据。 |
| [读取文本文件](read-text-file.md) | `file.read_text_file` | 读取文本文件内容。 |
| [写入文本文件](write-text-file.md) | `file.write_text_file` | 写入文本文件内容。 |

## 典型搭配

这类节点通常会按 `读取 CSV 单元格 → 读取 CSV 行 → 读取 CSV 表 → 读取文本文件` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/files-text-and-csv.json" title="文本与 CSV 文件节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [读取 CSV 单元格](read-csv-cell.md) (`file.read_csv_cell`)
- [读取 CSV 行](read-csv-row.md) (`file.read_csv_row`)
- [读取 CSV 表](read-csv-table.md) (`file.read_csv_table`)
- [读取文本文件](read-text-file.md) (`file.read_text_file`)
- [写入文本文件](write-text-file.md) (`file.write_text_file`)
