---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:browser-table-to-excel
---

# 网页表格导出 Excel

## 场景

打开包含表格的页面，将表头和行数据提取到新的 Excel 工作簿。

## 前置条件

启用浏览器执行器、远程网络、文件访问和允许的输出目录。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/browser-table-to-excel.json" title="网页表格导出 Excel">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [导航](../components/browser/navigation/navigate.md) (`browser.navigate`)：导航浏览器到目标 URL。
- [提取网页表格到 Excel](../components/browser/scripts-and-extraction/extract-web-table-to-excel.md) (`browser.extract_web_table_to_excel`)：从浏览器页面提取 HTML 表格并写入 Excel。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

`output/table.xlsx` 被创建，`Data` 工作表包含页面表头和数据行。

## 失败诊断

检查表格选择器、文件允许根和目标文件占用；该节点新建工作簿，不会追加既有文件。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 browser-table-to-excel.zip](../../downloads/weconduct/0.8.1/browser-table-to-excel.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/browser-table-to-excel.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
