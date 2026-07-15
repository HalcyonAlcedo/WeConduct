---
product: weave
version: 0.5.0
stable: true
doc_id: weave:getting-started:install-and-update
---

# 安装与更新

Weave 0.5.0 面向 Windows。下载地址：[GitHub Releases](https://github.com/HalcyonAlcedo/Weave/releases)。

## 安装

1. 从 Releases 页面下载 `Weave-windows-x64.zip`。
2. 解压到一个固定目录，例如 `D:\Tools\Weave\`。
3. 确认目录里有 `Weave.exe` 和 `plugins\` 文件夹。
4. 运行 `Weave.exe`。

首次启动后，Weave 会在程序同级目录创建 `.weave\`，用于存放设置、工作区、会话等数据。

## 更新

Weave 0.5.0 没有内置自动更新，更新步骤：

1. 退出正在运行的 Weave。
2. 备份旧目录中的 `.weave\` 和 `plugins\`（如果你自己装了插件）。
3. 用新版本 ZIP 覆盖程序目录。
4. 将备份的 `.weave\` 和 `plugins\` 放回原位。

## 升级后检查

- `Weave.exe` 能否正常启动。
- 原有工作区是否仍然显示在工作区列表中。
- 设置页中的主题、布局恢复和插件启用状态是否正确。
- 如果使用插件，`plugins\` 下的目录是否完整。
