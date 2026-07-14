---
product: weconduct
version: 0.8.1
doc_id: weconduct:getting-started:first-project
---

# 创建第一个项目

本例创建一个目录项目，依次写入并读取变量 `message`。

<weconduct-graph src="../../assets/graphs/getting-started/first-project.json" title="第一个项目：写入并读取变量">图示加载失败时，请按本页的节点和连线表继续操作。</weconduct-graph>

## 1. 新建项目

1. 打开顶部 **文件** 菜单，选择 **新建项目**。
2. 项目名称填写 `first-project`。
3. 选择一个可写的项目目录。
4. 确认创建。

指定目录后，0.8.1 会保存主项目文件 `first-project.weconduct.json`，并在同一目录维护项目存储内容。不要只移动其中一个文件；需要迁移时应移动整个项目目录。

## 2. 添加节点

从组件库依次添加：

1. **开始**，资源键 `flow.start`。
2. **写入变量**，资源键 `data.set_variable`。
3. **读取变量**，资源键 `data.get_variable`。

主图只能有一个 `flow.start`。它是标准运行的入口。

## 3. 配置节点

选择每个节点，在节点配置中填写：

- **开始**：`initial_variables` 添加 `project_name = "第一个流程"`；浏览器保持 `headless = true`、`slow_mo_ms = 0`。
- **写入变量**：`name = "message"`，`value = "WeConduct 0.8.1"`。
- **读取变量**：`name = "message"`。

`value` 是字符串常量，不要在本例中添加 `${...}`。

## 4. 连接控制流

建立两条控制边：

1. `开始.out` → `写入变量.in`
2. `写入变量.out` → `读取变量.in`

控制边决定执行顺序。本例不需要数据边：`读取变量` 通过变量名从运行时变量表取值，它没有数据输入端口。

## 5. 保存

从 **文件** 菜单选择 **保存**。如果新建时没有指定目录，程序会要求使用 **另存为** 选择 `.weconduct.json` 路径。

保存完成后，项目不应继续显示未保存状态。

## 6. 运行

点击顶部工具栏的运行按钮。运行时会自动执行准备、编译和运行流程，不需要手动执行 Prepare。

成功时，任务执行面板结束为成功状态；`读取变量` 节点的结果包含：

```json
{
  "variable_name": "message",
  "value": "WeConduct 0.8.1"
}
```

若失败，先看诊断与输出窗口。常见原因是变量名为空、主图缺少唯一的 `flow.start`，或控制边没有连到节点的 `in` 端口。

继续阅读：[第一次运行](first-run.md)和[节点、端口与边](../concepts/nodes-ports-and-edges.md)。
