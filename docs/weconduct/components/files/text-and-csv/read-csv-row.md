---
product: weconduct
version: 0.8.1
doc_id: component:file.read_csv_row
---

# 读取 CSV 行

资源键：`file.read_csv_row`
英文名：Read CSV Row

## 功能说明

读取 CSV 行数据。

该节点属于“文本与 CSV 文件”。实现类型为 `未声明`，运行展开角色为 `action:read_csv_row`。

## 适用场景

在允许文件根中读取或写入文本、CSV 数据，并显式选择编码和表头规则。

## 前置条件与权限

启用文件访问，并确保路径位于允许根内。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `out` | output | `control` | `out.control` |
| `out:row` | output | `data` | `out.row` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `path` | `string` | 是 | `""` | `path` |
| `encoding` | `string` | 否 | `"utf-8"` | `default` |
| `has_header` | `boolean` | 否 | `true` | `default` |
| `row_index` | `integer` | 否 | `0` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入：`in`。输出：`out`、`out:row`。副作用：可能读取或写入文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/file/file-read-csv-row.json" title="读取 CSV 行配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.csv",
  "encoding": "utf-8",
  "has_header": true,
  "row_index": 0,
  "variable_name": "result"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

读取结果写入指定变量，或文件写入完成后返回保存信息。

## 常见错误

缺少必填参数：`path`、`variable_name`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；路径越界、编码不匹配、CSV 行列越界或文件不可访问。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

CSV 行列索引和 `has_header` 会共同影响实际定位；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[文本与 CSV 文件](index.md)聚合页。
- [读取文本文件](read-text-file.md) (`file.read_text_file`)。
- [写入文本文件](write-text-file.md) (`file.write_text_file`)。
- [读取 CSV 单元格](read-csv-cell.md) (`file.read_csv_cell`)。
- [读取 CSV 表](read-csv-table.md) (`file.read_csv_table`)。
