---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:data-list-processing
---

# 列表整理与统计

## 这个示例做什么

创建列表、追加元素、排序，并统计最终长度。

## 准备工作

不需要外部服务或高风险权限，可直接用于理解变量和列表节点。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/data-list-processing.json" title="列表整理与统计">如果图示加载失败，你可以按照下方节点职责说明和配置步骤手动重建这个流程。</weconduct-graph>

## 图中使用了哪些节点

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [创建列表](../components/data/lists/create-list.md) (`data.create_list`)：创建运行时列表。
- [列表追加](../components/data/lists/list-append.md) (`data.list_append`)：向运行时列表追加项。
- [列表排序](../components/data/lists/list-sort.md) (`data.list_sort`)：对运行时列表排序。
- [列表长度](../components/data/lists/list-length.md) (`data.list_length`)：读取运行时列表长度。

## 如何运行

1. 下载 ZIP 并解压到你的项目目录，用 WeConduct 打开其中的 `.weconduct.json` 文件。
2. 逐个检查图中每个节点的配置，将示例中的占位 URL、选择器、文件路径或凭据替换为你自己的实际值。
3. 根据上方的准备工作，在项目设置中开启必要的权限，然后保存项目、执行校验，确认无误后即可运行。
4. 如果你调整了节点之间的连线，请确保每条边都连接到了节点端口表中实际声明的控制端口或数据端口。

## 运行后应该看到什么

`numbers` 变为 `[1, 2, 3, 4]`，`count` 为 `4`。

## 如果出错怎么办

检查 `numbers` 是否被其他节点覆盖为非列表值，以及变量名是否完全一致。

排查时建议记录节点的 ID、资源键和完整的错误信息，先判断是配置问题、权限问题还是运行环境问题，再对症解决。

## 下载项目

- [下载 data-list-processing.zip](../../downloads/weconduct/0.8.1/data-list-processing.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/data-list-processing.json)

下载包基于 WeConduct 0.8.1 版本。示例中的 URL、选择器和凭据均为占位值，外部站点和网络响应不随示例分发。
