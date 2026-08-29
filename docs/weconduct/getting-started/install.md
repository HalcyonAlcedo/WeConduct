---
product: weconduct
version: 0.9.1
doc_id: weconduct:getting-started:install
---

# 安装 WeConduct 0.9.1

WeConduct 目前面向 Windows x64 系统，提供两种安装方式：便携包（解压即用）和安装包（标准安装程序）。两种方式都已内置了运行所需的所有组件，你不需要另外安装 Node.js 或 Python。

## 下载

前往 [WeConduct Releases](https://github.com/HalcyonAlcedo/WeConduct/releases/tag/0.9.1) 下载页面，你会看到两个文件：

- **`WeConduct-0.9.1-portable.zip`**：便携版，解压后直接运行，适合想快速试用、随身携带或多版本并存的场景。
- **`WeConduct-0.9.1-setup.exe`**：安装版，标准的 Windows 安装程序，会帮你创建快捷方式和卸载入口。

> 如果下载页面显示的文件名和上面不一样，请以页面上的实际文件名为准。

## 便携版怎么用

1. 把 ZIP 文件完整解压到一个有写入权限的目录，比如 `D:\Apps\WeConduct-0.9.1`。
2. 如果 ZIP 是通过浏览器下载的，建议先右键点击 ZIP 文件 → **属性**，勾选 **解除锁定**，然后再解压。这样可以避免 Windows 的安全标记导致程序被拦截。
3. 进入解压目录，双击运行 `WeConduct.exe`。
4. 看到程序主窗口和节点图画布，就说明启动成功了。

!!! tip "更新便携版"
    先关闭 WeConduct，再把新版本解压到一个新的目录。项目文件应该保存在独立的项目目录中，不要放在程序目录里直接覆盖。

## 安装版怎么用

1. 双击运行 `WeConduct-0.9.1-setup.exe`。
2. 按照安装向导选择安装位置，等待安装完成。
3. 从开始菜单、桌面快捷方式或安装目录启动 WeConduct。

安装版适合固定在一台电脑上长期使用；便携版适合需要灵活控制程序位置的场景。两者创建的项目格式完全一致，可以互相打开。

## 启动后应该看到什么

程序打开后，你应该看到：

- 主窗口，包含顶部命令栏
- 中间的节点图画布（可能显示为空或包含默认节点）
- 侧边的组件库面板

如果窗口一闪而过、没有出现，或者直接报错退出，可以记下你的 Windows 版本、安装方式和程序路径，然后查看[故障排查](../troubleshooting/index.md)。

## 下一步

安装成功后，就可以[创建你的第一个项目](first-project.md)了。
