---
product: weconduct
version: 0.8.1
doc_id: weconduct:guide:wcrun-packaging
---

# 构建 `.wcrun`

`.wcrun` 是只读运行包。打开 **文件 → .wcrun 包管理**，在 **校验 & 构建** 中操作。

## 打包前校验

预检固定使用 `mode = wcrun` 和 `source_of_truth = saved_project_only`，因此先保存项目。0.8.1 的预检检查已保存图的校验诊断，以及必需外部资源是否缺少绑定，并按错误、警告、信息汇总。

Python 运行时和安全需求会写入包 manifest，并在检查、加载和运行就绪阶段处理；不要把打包前预检通过理解为目标环境已经满足这些要求。

存在阻断项时不要构建。根据 `node_id`、`setting_field` 或 `resource_id` 修复后重新预检。

## 构建

1. 在项目设置确认默认输出名和嵌入资源。
2. 根据 Python 节点选择 `package_embed_mode`：`none`、`wheelhouse_rebuild` 或 `full_venv`。
3. 选择 `.wcrun` 输出路径。
4. 点击 **构建 .wcrun**。

包包含 manifest、入口图、图索引、项目设置、资源、依赖摘要、校验和，以及按策略生成的 Python 运行时内容。构建结果显示条目数、大小、图和资源摘要。

构建成功不等于目标机器必然可运行；应在目标环境先[检查和加载](wcrun-loading.md)。
