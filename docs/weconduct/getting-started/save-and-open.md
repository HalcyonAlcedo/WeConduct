---
product: weconduct
version: 0.8.1
doc_id: weconduct:getting-started:save-and-open
---

# 保存和重新打开项目

WeConduct 的项目是以 `.weconduct.json` 文件为核心的目录结构。了解项目文件的组织方式，能帮你更好地管理和迁移你的工作。

## 保存项目

点击 **文件 → 保存** 即可保存当前的项目状态，包括：

- 主图的内容（节点、连线和配置）
- 项目设置
- 自定义组件和资源

如果是第一次保存（项目还没有指定保存路径），WeConduct 会自动切换到"另存为"流程，让你选择 `.weconduct.json` 文件的存放位置。

## 项目文件是怎么组织的

保存项目后，你的项目目录看起来像这样：

```
你的项目目录/
├── first-project.weconduct.json    ← 主项目文件
└── first-project.weconduct.data/   ← 项目数据目录
    ├── graphs/                     ← 节点图文件
    ├── resources/                  ← 自定义组件等资源
    └── ...
```

因此，迁移或备份项目时，记得把**整个项目目录**一起复制。单独移动 `.weconduct.json` 文件会导致数据目录找不到。

## 打开已有项目

1. 点击 **文件 → 打开项目文件**。
2. 找到并选择项目的 `.weconduct.json` 文件。
3. WeConduct 会自动加载相关的图、资源、运行记录和设置。

最近打开过的项目会出现在"最近项目"列表中，方便你快速访问。如果项目目录被移动了，从列表中移除旧记录，再从新位置重新打开即可。

## 与 .wcrun 打包文件的区别

`.wcrun` 是一种**只读的运行包**格式，它把项目打包成一个可分发的文件。和普通项目不同：

- `.wcrun` 包打开后不能编辑图或修改配置
- 不能直接保存为 `.weconduct.json` 项目文件
- 适合分发和部署已经调试好的自动化流程

如果需要编辑流程，请打开原始的 `.weconduct.json` 项目文件。

## 相关阅读

- [项目与工作区](../concepts/projects-and-workspaces.md) — 深入了解项目结构
- [项目管理](../guide/project-management.md) — 更多项目操作技巧
