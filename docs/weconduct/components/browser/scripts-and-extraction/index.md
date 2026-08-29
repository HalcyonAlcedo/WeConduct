---
product: weconduct
version: 0.9.1
doc_id: component-group:browser-scripts-and-extraction
---

# 脚本与提取

覆盖脚本执行、网页表格提取与结果导出。

## 节点速览

| 节点 | 资源键 | 主要用途 |
|---|---|---|
| [提取网页表格](extract-web-table.md) | `browser.extract_web_table` | 从当前浏览器页面提取 HTML 表格。 |
| [提取网页表格到 Excel](extract-web-table-to-excel.md) | `browser.extract_web_table_to_excel` | 从浏览器页面提取 HTML 表格并写入 Excel。 |
| [注入 JS](inject-js.md) | `browser.inject_js` | 在当前浏览器上下文执行 JavaScript 且不存储结果。 |
| [运行 JS](run-js.md) | `browser.run_js` | 在当前浏览器上下文执行 JavaScript 并存储结果。 |

## 典型搭配

这类节点通常会按 `提取网页表格 → 提取网页表格到 Excel → 注入 JS → 运行 JS` 的顺序串联使用。具体的连线方式取决于每个节点的端口定义和控制流语义，建议在画布中实际连接后运行校验确认。

## 节点对比图

<weconduct-graph src="../../../../assets/graphs/components/groups/browser-scripts-and-extraction.json" title="脚本与提取节点概览">如果图示加载失败，可以使用下方的节点列表查看每个节点的信息。</weconduct-graph>

上图展示了本组节点的外观、端口和默认配置，方便你快速对比，但不能直接作为完整流程运行。

## 全部节点

- [提取网页表格](extract-web-table.md) (`browser.extract_web_table`)
- [提取网页表格到 Excel](extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)
- [注入 JS](inject-js.md) (`browser.inject_js`)
- [运行 JS](run-js.md) (`browser.run_js`)
