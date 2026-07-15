---
product: weave
version: 0.5.0
stable: true
doc_id: weave:getting-started:install-and-update
---

# 安装与更新

> `0.5.0` 是当前文档锁定版本。Weave 尚未发布公开 Release 或可下载资产；以下文件名描述现有打包脚本的预期便携产物，不代表仓库中已经提供下载。

## 分发形态

Weave 0.5.0 的打包脚本预期生成两个用户会接触到的产物：

- `packaging\dist\Weave\Weave.exe`
- `packaging\dist\Weave-windows-x64.zip`

ZIP 包内容是便携目录，脚本还会在程序目录内准备空的 `plugins\` 文件夹。

## 首次安装

1. 解压 `Weave-windows-x64.zip` 到一个固定目录，例如 `D:\Tools\Weave\`。
2. 确认目录里至少有 `Weave.exe`，并保留同级 `plugins\` 文件夹。
3. 运行 `Weave.exe`。

首次启动后，Weave 会在 `Weave.exe` 同级创建 `.weave\`，其中包含：

- `settings.json`
- `workspace_registry.json`
- `workspaces\`
- `sessions\`

## 更新方式

Weave 0.5.0 没有内置自动更新。推荐按便携软件处理：

1. 退出正在运行的 Weave。
2. 备份旧目录中的 `.weave\` 和 `plugins\`。
3. 用新版本 ZIP 覆盖程序文件，或只替换 `Weave.exe` 与同版本附带文件。
4. 把原来的 `.weave\` 和 `plugins\` 放回同级目录。

## 单文件替换何时可行

以下情况通常可以直接替换 `Weave.exe`：

- 你确认新旧版本的数据目录结构没有变化。
- 你没有同时升级插件。
- 你只是在同一条 `0.5.x` 维护线上更新。

以下情况更适合整包替换：

- 你要同时更新插件。
- 你不确定旧目录里还有没有过期依赖文件。
- 你要从别的打包方式切换到当前 Wails 打包结果。

## 升级前后建议检查

- `Weave.exe` 能否正常启动。
- 原有工作区是否仍然出现在工作区列表。
- 设置页里主题、布局恢复和插件启用状态是否仍然正确。
- 如果使用插件，`plugins\` 下的目录是否仍然完整。
