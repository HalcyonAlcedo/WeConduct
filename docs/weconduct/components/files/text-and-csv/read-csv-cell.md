---
product: weconduct
version: 0.9.1
doc_id: component:file.read_csv_cell
---

# 读取 CSV 单元格

资源键：`file.read_csv_cell`　|　英文名：Read CSV Cell
## 功能说明

读取 CSV 单元格值。

## 什么时候用

读取 CSV 指定行和列的单元格值。

## 需要什么权限

需要开启文件访问权限，并确保目标路径在允许的目录范围内。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `path` | `string` | 是 | `""` | `path` |
| `encoding` | `string` | 否 | `"utf-8"` | `default` |
| `has_header` | `boolean` | 否 | `true` | `default` |
| `row_index` | `integer` | 否 | `0` | `default` |
| `column` | `any` | 否 | `null` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：读取目标 CSV 文件，不修改文件内容。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/file/file-read-csv-cell.json" title="读取 CSV 单元格配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.csv",
  "encoding": "utf-8",
  "has_header": true,
  "row_index": 0,
  "column": null,
  "variable_name": "result"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

返回选定行列的 `value`，并可按节点配置写入运行时变量。

## 常见问题

缺少必填参数：`path`、`variable_name`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；路径越界、CSV 格式/编码错误、行号越界或列不存在。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

`has_header` 会影响列名解析；`row_index` 从 `0` 开始；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[文本与 CSV 文件](index.md)聚合页查看更多同类节点。
- [读取文本文件](read-text-file.md) (`file.read_text_file`)。
- [写入文本文件](write-text-file.md) (`file.write_text_file`)。
- [读取 CSV 行](read-csv-row.md) (`file.read_csv_row`)。
- [读取 CSV 表](read-csv-table.md) (`file.read_csv_table`)。
