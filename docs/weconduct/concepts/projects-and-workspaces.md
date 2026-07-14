---
product: weconduct
version: 0.8.1
doc_id: weconduct:concepts:projects-and-workspaces
---

# 项目与工作区

**项目**是可保存、迁移和打包的自动化单位；**工作区**是程序当前加载的项目状态，包括主图、资源注册表、编辑历史、执行历史和项目设置。

## 项目路径

创建项目时，`project_name` 不能为空。指定 `project_directory` 后，主文件名为 `<项目名>.weconduct.json`。程序把主文件所在目录记录为 `workspace_root`。

保存操作分为：

- `save_project`：已有路径时写回当前项目。
- `save_project_as`：解析新路径并写入新位置。
- 无路径直接保存：返回 `project.needs_save_as`，由 UI 打开另存为流程。

## 工作区状态

打开项目时，后端重新建立工作区，并加载：

- `graph_document` 与图元数据
- `resource_registry`
- `editor_history`
- `execution_history`
- `project_settings`
- 图版本升级检查结果

UI 随后清理上一个项目的编译源与草稿，再强制刷新图、运行、Debug 和资源状态，避免跨项目缓存泄漏。

## 三种载入形态

- **目录项目**：0.8.1 的正常编辑形态，主文件与目录化存储共同组成项目。
- **旧式单文件项目**：仍可由 `.weconduct.json` 载入，保存后会同步目录化存储。
- **`.wcrun` 包**：来源为 `wcrun_package`，只读运行，不能替代原项目继续编辑。

操作说明见[保存和重新打开项目](../getting-started/save-and-open.md)。
