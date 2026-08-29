---
product: weconduct
version: 0.9.1
doc_id: weconduct:example:file-csv-transformation
---

# CSV 读取与文本输出

## 这个示例做什么

读取项目内示例 CSV 表格，并把处理说明写入文本文件。

## 准备工作

启用文件访问；下载项目已包含 `sample/input.csv`，输出目录必须位于允许根。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/file-csv-transformation.json" title="CSV 读取与文本输出">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [读取 CSV 表](../components/files/text-and-csv/read-csv-table.md) (`file.read_csv_table`)：读取 CSV 表数据。
- [数据映射](../components/data/conversion-and-expressions/map.md) (`data.map`)：内置数据映射能力。
- [写入文本文件](../components/files/text-and-csv/write-text-file.md) (`file.write_text_file`)：写入文本文件内容。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

CSV 行写入 `rows`，映射结果写入 `csv_rows`，并生成 `output/summary.txt`。

## 如果出错怎么办

检查项目根、文件权限、UTF-8 编码和 `has_header` 是否与实际 CSV 一致。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 file-csv-transformation.zip](../../downloads/weconduct/0.9.1/file-csv-transformation.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/file-csv-transformation.json)

下载包基于 WeConduct 0.9.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
