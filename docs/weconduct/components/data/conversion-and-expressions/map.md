---
product: weconduct
version: 0.9.0
doc_id: component:data.map
---

# 数据映射

资源键：`data.map`　|　英文名：Data Map
## 功能说明

内置数据映射能力。

## 什么时候用

在流程中读取、写入或转换运行时变量，并把结果交给后续节点。

## 需要什么权限

该节点不需要额外的程序权限，但仍需要满足图结构、输入类型和项目资源的基本约束。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:source` | input | `data` | `in.source` |
| `out` | output | `control` | `out.control` |
| `out:value` | output | `data` | `out.value` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `source` | `any` | 否 | `null` | `default` |
| `variable_name` | `string` | 是 | `""` | `default` |
| `mode` | `string` | 否 | `"map"` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:source`。输出端口：`out`、`out:value`。对外影响：按 `variable_name` 或节点语义读取或更新运行时变量。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/data/data-map.json" title="数据映射配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "source": null,
  "variable_name": "result",
  "mode": "map"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

操作成功后返回处理结果；声明输出变量时同步写入运行时上下文。

## 常见问题

缺少必填参数：`variable_name`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；变量不存在、值类型不兼容或表达式/正则格式无效。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[转换与表达式](index.md)聚合页查看更多同类节点。
- [转换变量类型](convert-value.md) (`data.convert_value`)。
- [计算表达式](evaluate-expression.md) (`data.evaluate_expression`)。
- [正则替换](regex-replace.md) (`data.regex_replace`)。
