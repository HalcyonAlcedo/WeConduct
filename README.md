# WeConduct

一款桌面端可视化编程工具，通过直观的节点图编辑器帮助你构建自动化工作流。设计、编译、运行 —— 无需手写代码。

## 它能做什么

WeConduct 将复杂的自动化任务转化为可视化流程图。你不再需要写脚本，只需在画布上连接节点、配置每一步，然后一键运行。适合需要自动化重复性工作的场景：数据处理管线、文件操作、网页自动化、自定义业务逻辑等。

**核心能力：**
- **可视化编辑器** — 拖拽、连接、配置节点即可设计工作流
- **编译引擎** — 验证图结构并将其转换为可执行代码（parse → bind → validate → normalize → lower → emit）
- **运行时执行器** — 运行已编译的工作流并实时推送进度
- **桌面应用** — 原生窗口体验，无需打开浏览器
- **项目管理** — 保存、版本管理、分享整个工作流项目
- **组件库** — 可复用的构建块（用户组件、子图、自定义节点图）
- **批量回归测试** — 一次性运行多个项目，端到端验证

## 安装

### 使用发布包

前往 [Releases](https://github.com/HalcyonAlcedo/weconduct/releases) 页面下载最新版本，提供两种分发形式：

- **便携包（zip）** — 解压即用，无需安装，适合快速试用或放入 U 盘携带
- **安装包（exe）** — 标准安装程序，自动创建桌面快捷方式和开始菜单入口

下载后运行即可，无需额外安装 Python 或 Node.js。

### 从源码构建

**环境要求：**

| 依赖 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |

**构建步骤：**

```bash
# 1. 克隆仓库
git clone https://github.com/HalcyonAlcedo/weconduct.git
cd weconduct

# 2. 安装 Python 依赖
pip install -e .

# 3. 安装前端依赖
cd ui
npm install
cd ..

# 4. 开发模式运行
python -m weconduct.cli.main desktop-shell

# 5. 构建独立可执行文件（可选）
.\scripts\build_bundle.ps1
```

`build_bundle.ps1` 会自动完成前端构建和 PyInstaller 打包，最终产物生成在 `dist/` 目录下。

## 项目结构

```
weconduct/
├── src/weconduct/     # Python 后端（编译器、运行时、API、桌面壳）
├── ui/                # Vue 3 前端（可视化编辑器）
├── tests/             # 测试套件
├── packaging/          # PyInstaller 打包配置
└── scripts/           # 构建脚本
```

## 许可证

[MIT](LICENSE)
