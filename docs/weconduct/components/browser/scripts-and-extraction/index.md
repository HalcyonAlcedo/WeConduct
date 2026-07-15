---
product: weconduct
version: 0.8.1
doc_id: component-group:browser-scripts-and-extraction
---

# 脚本与提取

覆盖脚本执行、网页表格提取与结果导出。

## 如何选择

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [提取网页表格](extract-web-table.md) | `browser.extract_web_table` | 从当前浏览器页面提取 HTML 表格。 |
| [提取网页表格到 Excel](extract-web-table-to-excel.md) | `browser.extract_web_table_to_excel` | 从浏览器页面提取 HTML 表格并写入 Excel。 |
| [注入 JS](inject-js.md) | `browser.inject_js` | 在当前浏览器上下文执行 JavaScript 且不存储结果。 |
| [运行 JS](run-js.md) | `browser.run_js` | 在当前浏览器上下文执行 JavaScript 并存储结果。 |

## 常见组合

可从 `提取网页表格 → 提取网页表格到 Excel → 注入 JS → 运行 JS` 的顺序理解本组能力；实际连线必须按各节点端口和控制语义调整。

## 组合图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-scripts-and-extraction.json" title="脚本与提取节点概览">图示加载失败时，可使用下方节点列表。</weconduct-graph>

该图用于比较节点外形、端口和默认配置，不代表可直接运行的完整流程。

## 节点列表

- [提取网页表格](extract-web-table.md) (`browser.extract_web_table`)：组件库可见。
- [提取网页表格到 Excel](extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)：组件库可见。
- [注入 JS](inject-js.md) (`browser.inject_js`)：组件库可见。
- [运行 JS](run-js.md) (`browser.run_js`)：组件库可见。
