---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:file-csv-transformation
---

# CSV 读取与文本输出

## 场景

读取项目内示例 CSV 表格，并把处理说明写入文本文件。

## 前置条件

启用文件访问；下载项目已包含 `sample/input.csv`，输出目录必须位于允许根。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/file-csv-transformation.json" title="CSV 读取与文本输出">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [读取 CSV 表](../components/files/text-and-csv/read-csv-table.md) (`file.read_csv_table`)：读取 CSV 表数据。
- [数据映射](../components/data/conversion-and-expressions/map.md) (`data.map`)：内置数据映射能力。
- [写入文本文件](../components/files/text-and-csv/write-text-file.md) (`file.write_text_file`)：写入文本文件内容。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

CSV 行写入 `rows`，映射结果写入 `csv_rows`，并生成 `output/summary.txt`。

## 失败诊断

检查项目根、文件权限、UTF-8 编码和 `has_header` 是否与实际 CSV 一致。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 file-csv-transformation.zip](../../downloads/weconduct/0.8.1/file-csv-transformation.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/file-csv-transformation.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
