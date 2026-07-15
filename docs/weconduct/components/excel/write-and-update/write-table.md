---
product: weconduct
version: 0.8.1
doc_id: component:excel.write_table
---

# 写入 Excel 表

资源键：`excel.write_table`
英文名：Write Excel Table

## 功能说明

写入 Excel 表数据。

该节点属于“Excel 写入与更新”。实现类型为 `未声明`，运行展开角色为 `action:write_excel_table`。

## 适用场景

在允许路径内读取或更新 Excel 工作簿；先确认文件、工作表和单元格/行表范围。

## 前置条件与权限

启用文件访问，并确保路径位于允许根内。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:data` | input | `data` | `in.data` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `path` | `string` | 是 | `""` | `path` |
| `sheet_name` | `string` | 否 | `"Sheet1"` | `default` |
| `data` | `array` | 否 | `[]` | `default` |
| `has_header` | `boolean` | 否 | `true` | `default` |

## 输入、输出与副作用

输入：`in`、`in:data`。输出：`out`。副作用：可能读取或写入文件。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/excel/excel-write-table.json" title="写入 Excel 表配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "path": "output/example.xlsx",
  "sheet_name": "Sheet1",
  "data": [],
  "has_header": true
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

读取节点返回结构化值；写入或批量更新节点保存工作簿后成功。

## 常见错误

缺少必填参数：`path`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；工作簿或工作表不存在、单元格/行参数无效或文件被占用。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

行号和表头选项会影响数据定位，写入前应确认目标文件备份；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[Excel 写入与更新](index.md)聚合页。
- [写入 Excel 单元格](write-cell.md) (`excel.write_cell`)。
- [写入 Excel 行](write-row.md) (`excel.write_row`)。
- [写入 Excel 文件](write-file.md) (`excel.write_file`)。
- [更新 Excel 单元格](update-cells.md) (`excel.update_cells`)。
- [批量更新 Excel](update-batch.md) (`excel.update_batch`)。
