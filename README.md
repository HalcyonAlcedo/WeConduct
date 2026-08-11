<p align="center">
  <img src="assets/icons/weconduct.png" alt="WeConduct" width="128" />
</p>

<h1 align="center">WeConduct</h1>

<p align="center">
  <strong>在画布上搭建自动化工作流，无需手写代码</strong>
</p>

<p align="center">
  <a href="https://github.com/HalcyonAlcedo/WeConduct/releases"><img src="https://img.shields.io/github/v/release/HalcyonAlcedo/WeConduct?include_prereleases&label=release" alt="GitHub release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/HalcyonAlcedo/WeConduct"><img src="https://img.shields.io/badge/platform-Windows%2010%2B-0078D6" alt="Platform: Windows"></a>
  <a href="https://halcyonalcedo.github.io/WeConduct/"><img src="https://img.shields.io/badge/docs-%F0%9F%93%96-brightgreen" alt="Documentation"></a>
</p>

---

## 它是什么

WeConduct 是一款**桌面端可视化自动化工具**。你不再需要写脚本——把任务拆成节点、在画布上连接它们、配置好参数，然后一键运行。

从浏览器自动化、网页数据抓取，到文件批量处理、Excel 报表生成，所有逻辑都用流程图表达。设计、运行、调试都在同一个窗口完成，所见即所得。

---

## 能做什么

### 🌐 浏览器自动化
操控浏览器完成网页操作——打开页面、填写表单、点击按钮、提取数据、截图存证。支持自动重试和容错处理，适合数据采集、表单填报、网页巡检等场景。

### 📡 API 请求与数据处理
发送 HTTP 请求调用接口、解析返回数据，结合 CSV/Excel 读写节点，轻松搭建数据采集→清洗→导出管线。

### 🐍 内嵌 Python 脚本
在流程中嵌入 Python 代码节点，处理复杂业务逻辑。拥有完整 Python 生态的访问能力，逻辑写在节点里、数据跟着流程走。

### 🔀 流程编排
- **条件分支** —— 根据数据结果走不同路径
- **循环** —— 遍历列表、翻页抓取、重试直到成功
- **子图** —— 将常用流程封装为可复用模块
- **错误处理** —— 失败自动重试或走降级分支

### 📦 工作流打包分发
将完整的项目——图、配置、资源——打包为单个 `.wcrun` 运行时文件。对方加载后即可运行，无需安装编辑器或了解内部结构。适合将成体系的自动化流程交付给他人使用。

### 🔌 供外部工具调用
WeConduct 提供外部 API 接口，允许第三方工具（如 AI 助手、CI 系统）读取项目、触发编译、执行工作流。所有操作需鉴权，安全可控。

---

## 内置节点一览

WeConduct 提供 **135+ 个内置节点**，按功能分为以下类别：

| 分类 | 能做什么 |
|------|----------|
| 🔀 流程控制 | 条件判断、循环遍历、子图调用、重试容错 |
| 🌐 浏览器操作 | 页面导航、元素交互、截图、JS 注入 |
| 📡 网络请求 | HTTP 请求、WebSocket 通信 |
| 📊 数据处理 | CSV/Excel 读写、变量运算、表达式求值 |
| 📁 文件操作 | 读文件、写文件、目录管理 |
| 🐍 Python 执行 | 嵌入 Python 代码处理自定义逻辑 |
| 🔧 兼容节点 | 旧版项目平滑升级 |

→ 完整节点索引：[halcyonalcedo.github.io/WeConduct](https://halcyonalcedo.github.io/WeConduct/)

---

## 快速开始

### 下载使用（推荐）

前往 [Releases](https://github.com/HalcyonAlcedo/WeConduct/releases) 下载最新版本：

| 分发形式 | 说明 |
|----------|------|
| **便携包 (zip)** | 解压即用，无需安装，适合快速试用或随身携带 |
| **安装包 (exe)** | 标准安装程序，创建桌面快捷方式和开始菜单入口 |

下载后运行即可，无需额外安装任何环境。

### 从源码构建

**环境要求：** Python ≥ 3.11、Node.js ≥ 18

```bash
# 1. 克隆仓库
git clone https://github.com/HalcyonAlcedo/WeConduct.git
cd WeConduct

# 2. 安装 Python 依赖
pip install -e .

# 3. 安装前端依赖
cd ui && npm install && cd ..

# 4. 开发模式启动
python -m weconduct.cli.main desktop-shell

# 5. 构建可执行文件（可选）
.\scripts\build_bundle.ps1
```

---

## 文档

完整的用户文档托管在 [halcyonalcedo.github.io/WeConduct](https://halcyonalcedo.github.io/WeConduct/)：

- **快速入门** — 安装指引、创建第一个工作流
- **核心概念** — 图、节点、端口、变量、子图
- **使用指南** — 编辑器操作、节点配置、运行与调试
- **内置节点参考** — 所有 135+ 个节点按功能分类的详细说明
- **示例项目** — 10 个可下载的示例工程
- **故障排查** — 常见问题与解决方案
- **参考** — 项目格式、变量语法、快捷键、安全权限

---

## 许可证

[MIT](LICENSE) © HalcyonAlcedo
