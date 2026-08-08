---
product: weconduct
version: 0.9.0
doc_id: weconduct:example:browser-table-to-excel
---

# 网页表格导出 Excel

## 这个示例做什么

打开包含表格的页面，将表头和行数据提取到新的 Excel 工作簿。

## 准备工作

启用浏览器执行器、远程网络、文件访问和允许的输出目录。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-table-to-excel.json" title="网页表格导出 Excel">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [提取网页表格到 Excel](../components/browser/scripts-and-extraction/extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)：从浏览器页面提取 HTML 表格并写入 Excel。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

`output/table.xlsx` 被创建，`Data` 工作表包含页面表头和数据行。

## 如果出错怎么办

检查表格选择器、文件允许根和目标文件占用；该节点新建工作簿，不会追加既有文件。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 browser-table-to-excel.zip](../../downloads/weconduct/0.9.0/browser-table-to-excel.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-table-to-excel.json)

下载包基于 WeConduct 0.9.0 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
