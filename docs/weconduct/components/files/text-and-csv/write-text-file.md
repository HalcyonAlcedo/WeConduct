---
product: weconduct
version: 0.9.0
doc_id: component:file.write_text_file
---

# 写入文本文件

资源键：`file.write_text_file`　|　英文名：Write Text File
## 功能说明

写入文本文件内容。

## 什么时候用

把文本或可转换的运行时值写入允许文件根中的目标文件。

## 需要什么权限

需要开启文件访问权限，并确保目标路径在允许的目录范围内。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:content` | input | `data` | `in.content` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `path` | `string` | 是 | `""` | `path` |
| `encoding` | `string` | 否 | `"utf-8"` | `text` |
| `content` | `any` | 否 | `""` | `textarea` |

## 输入、输出与副作用

输入端口：`in`、`in:content`。输出端口：`out`。对外影响：创建或覆盖目标文本文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/file/file-write-text-file.json" title="写入文本文件配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.txt",
  "encoding": "utf-8",
  "content": "example"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

字符串原样写入；`dict`/`list` 转为 UTF-8 JSON 文本；其他值使用运行时字符串表示，并返回路径、编码和 `bytes_written`。

## 常见问题

缺少必填参数：`path`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；路径越界、编码不匹配、内容无法转换或文件不可写。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

该节点不使用 CSV 行列索引或 `has_header`；需要长期保存会话数据时应显式选择持久化路径；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[文本与 CSV 文件](index.md)聚合页查看更多同类节点。
- [读取文本文件](read-text-file.md) (`file.read_text_file`)。
- [读取 CSV 单元格](read-csv-cell.md) (`file.read_csv_cell`)。
- [读取 CSV 行](read-csv-row.md) (`file.read_csv_row`)。
- [读取 CSV 表](read-csv-table.md) (`file.read_csv_table`)。
