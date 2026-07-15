---
product: weconduct
version: 0.8.1
doc_id: component:browser.inject_js
---

# 注入 JS

资源键：`browser.inject_js`　|　英文名：Inject JS
## 功能说明

在当前浏览器上下文执行 JavaScript 且不存储结果。

## 什么时候用

内置浏览器动作无法表达目标行为时，在当前页面上下文执行受控 JavaScript。

## 需要什么权限

需要按节点行为开启 JavaScript 注入或求值权限；需要开启浏览器执行器，并确保存在可用的页面目标。

## 端口说明

| 端口 | 方向 | 关系层 | 语义 |
|---|---|---|---|
| `in` | input | `control` | `in.control` |
| `in:script` | input | `data` | `in.script` |
| `out` | output | `control` | `out.control` |

## 配置参数

| 参数 | 类型 | 必填 | 默认值 | 编辑器 |
|---|---|---|---|---|
| `script` | `string` | 是 | `""` | `default` |

## 输入、输出与副作用

输入端口：`in`、`in:script`。输出端口：`out`。对外影响：脚本可读取或修改页面 DOM 和页面全局状态。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-inject-js.json" title="注入 JS配置示例">如果图示加载失败，可以查看下方的示例配置。</weconduct-graph>

示例配置：

```json
{
  "script": "example"
}
```

使用时，将控制输入端口连接到上一个节点的输出，填写需要的配置参数，再把控制输出端口连接到下一个节点。数据端口只在需要显式传值时才连接。

## 预期结果

脚本执行完成；`run_js` 可把可序列化返回值写入变量。

## 常见问题

缺少必填参数：`script`；端口名称写错或关系层不匹配；输入值的类型与参数要求不一致；运行环境、资源路径或安全权限未正确配置；脚本语法错误、返回值不可序列化或 JavaScript 权限未开启。排查问题时，建议记录下节点 ID、资源键和原始错误信息，方便定位原因。

## 注意事项

页面的动态加载、DOM 变化和超时设置都会影响执行结果，建议使用尽可能稳定的选择器；脚本依赖页面实现，导航后注入状态不会自动保留；示例图只展示了节点的配置结构；要构成完整流程，还需要添加入口节点、控制边和业务输入。

## 相关节点

- 返回[脚本与提取](index.md)聚合页查看更多同类节点。
- [提取网页表格](extract-web-table.md) (`browser.extract_web_table`)。
- [提取网页表格到 Excel](extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)。
- [运行 JS](run-js.md) (`browser.run_js`)。
