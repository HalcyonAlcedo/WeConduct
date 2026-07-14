---
product: weconduct
version: 0.8.1
doc_id: weconduct:getting-started:install
---

# 安装 WeConduct 0.8.1

WeConduct 0.8.1 面向 Windows x64，发布页提供便携包和安装包。两种分发都已包含运行所需的前端与 Python 运行环境，不要求另装 Node.js 或 Python。

## 下载

从 [WeConduct Releases](https://github.com/HalcyonAlcedo/WeConduct/releases/tag/0.8.1) 获取以下文件之一：

- `WeConduct-0.8.1-portable.zip`：解压后直接运行，适合试用、移动目录或保留多个版本。
- `WeConduct-0.8.1-setup.exe`：标准安装程序，创建卸载入口和系统快捷方式。

文件名来自 0.8.1 发布工作流的产物规则。若发布页显示的文件名不同，以发布页实际资产为准。

## 使用便携包

1. 将 ZIP 完整解压到可写目录，例如 `D:\Apps\WeConduct-0.8.1`。
2. 不要直接在压缩包预览窗口中运行程序。
3. 启动解压目录中的 `WeConduct.exe`。
4. Windows 首次提示来源确认时，核对发布来源后再继续。

更新便携版时，先关闭 WeConduct，再解压新版本到新目录。项目文件应保存在独立项目目录，不要放进程序目录后直接覆盖。

## 使用安装包

1. 运行 `WeConduct-0.8.1-setup.exe`。
2. 按安装向导选择目录并完成安装。
3. 从开始菜单、桌面快捷方式或安装目录启动 WeConduct。

安装版适合固定在一台电脑上使用；便携版适合需要明确控制程序目录的场景。两者打开和保存的项目格式一致。

## 首次启动检查

程序打开后应显示主窗口、顶部命令栏和节点图工作区。若窗口没有出现或立即退出，记录 Windows 版本、安装方式、程序目录和启动时间，再查看[故障排查](../troubleshooting/index.md)。

下一步：[创建第一个项目](first-project.md)。
