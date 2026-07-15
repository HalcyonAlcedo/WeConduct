---
product: weconduct
version: 0.8.1
doc_id: component:excel.read_cell
---

# 读取 Excel 单元格

资源键：`excel.read_cell`　|　英文名：Read Excel Cell
## 功能说明

读取 Excel 单元格值。

## 什么时候用

在允许路径内读取或更新 Excel 工作簿；先确认文件、工作表和单元格/行表范围。

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
| `sheet_name` | `string` | 否 | `"Sheet1"` | `default` |
| `cell` | `string` | 是 | `""` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`。输出端口：`out`、`out:value`。对外影响：可能读取或写入文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/excel/excel-read-cell.json" title="读取 Excel 单元格配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.xlsx",
  "sheet_name": "Sheet1",
  "cell": "A1",
  "variable_name": "result"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

读取节点返回结构化值；写入或批量更新节点保存工作簿后成功。

## 常见问题

缺少必填参数：`path`、`cell`、`variable_name`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；工作簿或工作表不存在、单元格/行参数无效或文件被占用。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

行号和表头选项会影响数据定位，写入前应确认目标文件备份；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[Excel 读取](index.md)聚合页查看更多同类节点。
- [读取 Excel 行](read-row.md) (`excel.read_row`)。
- [读取 Excel 表](read-table.md) (`excel.read_table`)。
