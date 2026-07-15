---
product: weconduct
version: 0.8.1
doc_id: weconduct:troubleshooting:project-and-startup
---

# 项目无法创建、打开或恢复

## 提示项目文件缺少路径字段

常见原始错误：

```text
project file missing required string: project.main_graph_path
project file missing required string: project.project_resources_index_path
project file missing required string: project.resource_overrides_path
```

这表示根 `.weconduct.json` 不是完整 `project-v2` 清单，或手工修改时删除了目录项目引用。按[项目格式](../reference/project-format.md)检查三个路径，并确认目标 JSON 文件真实存在。

## 项目打开后显示资源损坏

检查 `<项目文件名>.data/resources/index.json` 中每个项目资源的 `manifest_path` 与 `graph_path`。不要只复制根项目文件；目录项目必须连同整个 `.data` 目录移动。

## 最近项目恢复到旧位置

最近项目和布局状态属于程序工作区状态，不是项目文件。先用 **文件 → 打开项目** 选择真实路径；确认可打开后再清理失效的最近项目记录。

## 打开 `.wcrun` 后无法编辑

这是只读包会话的设计。卸载包并打开用于构建它的原始 `.weconduct.json` 项目，不能把 `.wcrun` 当成可编辑项目。

## 需要提交的证据

- 根项目文件和对应 `.data` 目录树
- 三个路径字段的实际值
- 完整原始错误文本
- 项目是新建、迁移、WebControl 转换还是 `.wcrun` 加载
