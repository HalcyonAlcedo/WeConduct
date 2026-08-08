---
product: weconduct
version: 0.9.0
doc_id: weconduct:reference:variable-syntax
---

# 变量语法

## 变量来源

- `flow.start.node_config.initial_variables`：图入口初始变量。
- 数据节点：通过 `name`、`variable_name` 或 `output_variable_name` 写入 runtime 变量。
- Debug 变量编辑：只修改当前暂停会话；历史投影只读。
- 节点输出：保存在当前 runtime 的 `node_outputs` 中。

## 字符串引用

运行时引用使用 `${...}`：

```text
${username}
Hello, ${username}
${node.node-http.body}
${count|int}
```

整段字符串只有一个引用时保留原值类型；嵌入普通文本时转换为字符串，字典和列表转为 JSON 文本，`None` 转为空字符串。

## 节点输出路径

`${node.<node_id>.<field>}` 从指定节点结果读取字段。路径可继续访问字典键或列表索引；路径不存在时返回 `None`。

## 类型转换

引用末尾可加：

- `|string`
- `|int`
- `|float`
- `|bool`
- `|json`

别名包括 `str/text`、`integer`、`number`、`boolean`、`object/array`。无效转换会产生运行错误，不会静默保留原值。

## 使用建议

变量名区分拼写。需要跨节点传递复杂数据时优先使用数据边；字符串引用适合路径、文本模板和没有显式数据端口的参数。
