---
product: weconduct
version: 0.8.1
doc_id: weconduct:concepts:nodes-ports-edges
---

# 节点、端口与边

节点图的持久化契约是 `graph-v1`。图由 `GraphNode`、`GraphPort` 和 `GraphEdge` 组成。

<weconduct-graph src="../../assets/graphs/getting-started/first-project.json" title="节点、端口与控制边">图示加载失败时，可阅读下方字段说明。</weconduct-graph>

## 节点

每个节点至少有稳定的 `node_id`、`lowered_kind`、`source_anchor_ref` 和 `expansion_role`。可编辑图还使用：

- `node_kind`：组件资源键，例如 `data.set_variable`。
- `display_name`：画布显示名称。
- `position`：画布坐标。
- `ports`：端口列表。
- `node_config`：组件配置。

## 端口

端口由 `port_id` 唯一标识，并声明：

- `direction`：`input` 或 `output`。
- `relation_layer`：`control`、`data` 或内部观察层 `observe`。
- `semantic_slot`：运行和编译使用的语义槽位。
- `display_name`：可选显示名。
- `max_connections`：可选连接上限。

连接时必须使用组件实际声明的端口。端口层与边层不一致会产生图验证诊断。

## 边

边记录 `from_node_id`、`to_node_id`、可选的两端 `port_id` 和 `relation_layer`。源节点、目标节点与所引用端口都必须存在。

控制边和数据边解决不同问题，不要因为画布位置接近就混用。详细区别见[控制流与数据流](control-and-data-flow.md)。
