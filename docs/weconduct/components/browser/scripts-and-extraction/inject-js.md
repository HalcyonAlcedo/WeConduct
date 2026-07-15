---
product: weconduct
version: 0.8.1
doc_id: component:browser.inject_js
---

# 注入 JS

资源键：`browser.inject_js`
英文名：Inject JS

## 功能说明

在当前浏览器上下文执行 JavaScript 且不存储结果。

该节点属于“脚本与提取”。实现类型为 `core_atomic`，运行展开角色为 `action:inject_js`。

## 适用场景

内置浏览器动作无法表达目标行为时，在当前页面上下文执行受控 JavaScript。

## 前置条件与权限

按节点行为启用 JavaScript 注入或求值；启用浏览器执行器，并确保存在可用页面目标。

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

输入：`in`、`in:script`。输出：`out`。副作用：脚本可读取或修改页面 DOM 和页面全局状态。

## 使用示例

<weconduct-graph src="../../../../assets/graphs/components/browser/browser-inject-js.json" title="注入 JS配置示例">图示加载失败时，可阅读下方配置。</weconduct-graph>

示例配置：

```json
{
  "script": "example"
}
```

将控制输入连接到上一个动作，填写上述配置，再把控制输出连接到后续动作。数据端口仅在需要显式传值时连接。

## 预期结果

脚本执行完成；`run_js` 可把可序列化返回值写入变量。

## 常见错误

缺少必填参数：`script`；端口不存在或关系层不匹配；输入类型与参数要求不一致；运行环境、资源路径或安全权限未满足；脚本语法错误、返回值不可序列化或 JavaScript 权限未开启。诊断应保留节点 ID、资源键和原始错误信息。

## 限制与注意事项

页面导航、动态 DOM 和超时会影响结果，选择器应尽量稳定；脚本依赖页面实现，导航后注入状态不会自动保留；示例图只展示节点配置；完整流程还需入口、控制边和业务输入。

## 相关节点

- 返回[脚本与提取](index.md)聚合页。
- [提取网页表格](extract-web-table.md) (`browser.extract_web_table`)。
- [提取网页表格到 Excel](extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)。
- [运行 JS](run-js.md) (`browser.run_js`)。
