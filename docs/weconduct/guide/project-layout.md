---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:project-layout
---

# 项目布局

假设主文件是 `demo.weconduct.json`，0.9.1 保存后的核心结构如下：

```text
demo.weconduct.json
demo.weconduct.data/
├── graphs/
│   └── workspace.graph.json
├── resources/
│   ├── index.json
│   └── ...项目自有资源目录
├── resource-overrides.json
├── project-settings.json
└── ...运行环境、转换报告或历史数据
```

存储目录名按主文件的 `stem` 加 `.data` 生成，因此 `demo.weconduct.json` 对应 `demo.weconduct.data`。

## 主文件

主文件是 `project-v2` 清单，包含项目身份、编辑/执行历史摘要和资源引用。关键引用包括：

- `main_graph_path` → `graphs/workspace.graph.json`
- `project_resources_index_path` → `resources/index.json`
- `resource_overrides_path` → `resource-overrides.json`

不要只改这些路径字段而不移动对应文件。

## 图与资源

`workspace.graph.json` 保存主图 `GraphModel`。`resources/index.json` 索引项目自有组件和子图；具体资源位于 `resources/` 下。`resource-overrides.json` 保存对资源的项目级覆盖。

## 项目设置

`project-settings.json` 保存项目身份、运行、Python 环境、资源和打包配置。程序设置不在这里；程序设置对所有项目生效。

手工编辑 JSON 前先关闭 WeConduct 并备份整个目录。格式错误、引用缺失或版本不兼容会阻止项目打开。
