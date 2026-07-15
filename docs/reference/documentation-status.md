---
product: site
version: latest
doc_id: site:reference:documentation-status
---

# 文档状态

## 当前版本

- WeConduct 用户文档：`0.8.1`
- Weave 用户文档：`0.5.0`
- 当前只显示最新版本，不渲染版本切换器。

## 内容覆盖

- `126` 个 WeConduct 内置节点详情页。
- `25` 个同类节点聚合页。
- `151` 个节点详情或聚合教学图。
- `10` 个完整工作流示例和对应目录项目 ZIP。
- WeConduct 项目、编辑、运行、Debug、配置、资源、打包、排障和参考文档。
- Weave 独立安装、工作区、会话、页面分析、网络、存储、布局、插件和手工协作文档。

## 真值来源

- WeConduct：Git tag `0.8.1`。
- Weave：commit `9429be5`，作为首版 `0.5.0` 文档真值。
- 节点清单与图 schema 冻结在 `data/weconduct-0.8.1/`。

## 本地质量门

```powershell
python -m pytest -q
python tools/validate_pages.py
python tools/validate_graph_examples.py
python -m mkdocs build --strict --site-dir site
git diff --check
```

发布工作流在 `docs` 分支执行同类测试、页面校验、图校验和严格构建，再由 GitHub Pages Actions 部署。

## 版本预留

`versions/weconduct.json` 和 `versions/weave.json` 已分别保存当前版本元数据，`switcher_enabled` 为 `false`。WeConduct 从 `1.0.0` 开始支持多版本时，可在不改变当前产品根 URL 的前提下启用切换器。

