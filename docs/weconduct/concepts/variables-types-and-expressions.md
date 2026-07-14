---
product: weconduct
version: 0.8.1
doc_id: weconduct:concepts:variables-types-expressions
---

# 变量、类型与表达式

## 变量生命周期

`flow.start.initial_variables` 在流程入口写入初始变量。`data.set_variable` 写入或覆盖变量，`data.get_variable` 按名称读取；变量不存在时读取结果为 `null`。

变量值可为字符串、数字、布尔值、`null`、列表或对象。不要为了显示方便提前把所有值转成字符串。

## 引用语法

- `${message}`：变量 `message` 的值。
- `结果：${message}`：把值插入字符串。
- `${message|string}`：读取后转换为指定类型。
- `${node.node-id.value}`：读取节点输出字段。

引用可以出现在列表和对象内部，运行时会递归解析。

## 安全表达式

表达式节点与部分控制节点使用受限 AST 求值，不执行任意 Python。0.8.1 支持的核心形式包括：

- 常量、变量名、列表和元组
- `and` / `or`
- `+`、`-`、`*`、`/`、`//`
- 一元正负号
- 比较运算
- 下标访问
- `len(value)`
- 字典的 `get(key, default)`

函数调用、属性访问或语法不在白名单时会返回 `unsupported expression syntax` 或更具体的错误。表达式应保持短小；复杂处理优先拆成节点。
