---
product: weconduct
version: 0.9.1
doc_id: weconduct:reference:project-format
---

# 项目格式

## 根项目文件

0.9.1 目录项目的根文件使用 `project_file_schema_version = 2`，项目对象使用 `project_schema_version = project-v2`。三个路径字段不可缺少：

```json
{
  "project_file_schema_version": 2,
  "project": {
    "project_schema_version": "project-v2",
    "main_graph_path": "demo.weconduct.data/graphs/workspace.graph.json",
    "project_resources_index_path": "demo.weconduct.data/resources/index.json",
    "resource_overrides_path": "demo.weconduct.data/resource-overrides.json"
  }
}
```

## 主图

主图使用 `graph-v1`，核心字段为 `graph_model_id`、可空的 `compilation_id`、`nodes`、`edges`、`viewport` 和 `root_metadata`。每个节点保存完整端口快照和 `node_config`。

## 项目资源

`resources/index.json` 使用 `project_resources_schema_version = 1`，项目自定义组件项指向各自 `manifest.json` 和 `graph.json`。`resource-overrides.json` 使用 `resource_overrides_schema_version = 1`。

## 项目设置

`project-settings.json` 位于 `<项目文件名>.data/`。项目文件缺失时程序会按项目身份建立默认设置，但不应依赖这种回退分发项目。

## 兼容与迁移

旧单文件项目会进入迁移路径；`.wcrun` 是独立的只读包格式。手工编辑前关闭 WeConduct，并备份根文件和整个 `.data` 目录。
