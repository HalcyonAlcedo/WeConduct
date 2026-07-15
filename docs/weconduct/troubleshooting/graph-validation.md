---
product: weconduct
version: 0.8.1
doc_id: weconduct:troubleshooting:graph-validation
---

# 节点图无法校验或编译

## 提示缺少端口

诊断类别通常形如：

```text
graph.<node_kind>.missing_required_port
```

节点端口属于图契约，不能只改 `node_config` 模拟端口。删除异常节点后从组件库重新添加，或在元数据编辑器中按节点支持的分支配置重建动态端口。

## 提示边关系层不匹配

控制端口只能连接 `control` 边，数据端口只能连接 `data` 边。核对边两端的 `port_id`、方向和 `relation_layer`，不要把控制输出接到数据输入。

## 提示节点不可达

主图需要从 `flow.start` 沿控制边到达执行节点。只有数据边、孤立节点或未连接的分支不会进入标准运行。

## 分支、循环或并行结构无效

- `control.if` 使用 `true` / `false` 输出，回边使用专门的 `repeat` 输入。
- `control.while` 的循环体末端必须回到 `repeat`，正常退出走 `done`。
- `control.parallel_fork` 与 `control.join` 的分支 key 必须一致。
- `control.retry.max_attempts` 必须大于等于 `1`。

## 编译历史与运行历史不要混用

**输出 → 历史** 是编译历史；标准运行和 Debug 摘要位于 **任务执行 → 执行历史**。修复图后应重新校验和编译，旧历史不会自动变成成功记录。

