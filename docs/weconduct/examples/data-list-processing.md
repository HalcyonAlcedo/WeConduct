---
product: weconduct
version: 0.8.1
doc_id: weconduct:example:data-list-processing
---

# 列表整理与统计

## 场景

创建列表、追加元素、排序，并统计最终长度。

## 前置条件

不需要外部服务或高风险权限，可直接用于理解变量和列表节点。

## 流程图

<weconduct-graph src="../../assets/graphs/examples/data-list-processing.json" title="列表整理与统计">图示加载失败时，可按节点职责和配置步骤重建流程。</weconduct-graph>

## 节点职责

- [开始](../components/flow/components/start.md) (`flow.start`)：声明流程入口和初始变量。
- [创建列表](../components/data/lists/create-list.md) (`data.create_list`)：创建运行时列表。
- [列表追加](../components/data/lists/list-append.md) (`data.list_append`)：向运行时列表追加项。
- [列表排序](../components/data/lists/list-sort.md) (`data.list_sort`)：对运行时列表排序。
- [列表长度](../components/data/lists/list-length.md) (`data.list_length`)：读取运行时列表长度。

## 配置步骤

1. 下载并解压项目，打开同名 `.weconduct.json` 主文件。
2. 检查图中节点配置，把占位 URL、选择器、路径或凭据替换为实际值。
3. 按前置条件开启最小必要权限，先保存项目，再执行校验和运行。
4. 需要改动控制结构时，只连接各节点端口表中声明的控制或数据端口。

## 预期结果

`numbers` 变为 `[1, 2, 3, 4]`，`count` 为 `4`。

## 失败诊断

检查 `numbers` 是否被其他节点覆盖为非列表值，以及变量名是否完全一致。

保留诊断中的节点 ID、资源键、原始错误文本和会话状态，再判断是配置、权限、资源还是运行环境问题。

## 下载项目

- [下载 data-list-processing.zip](../../downloads/weconduct/0.8.1/data-list-processing.zip)
- [查看原始 graph-v1 JSON](../../assets/graphs/examples/data-list-processing.json)

下载包锁定 WeConduct 0.8.1。外部站点、凭据和网络响应不随示例分发。
