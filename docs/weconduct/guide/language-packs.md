---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:language-packs
---

# 语言包：安装与制作

WeConduct 界面默认使用简体中文。其他语言通过**外部语言包**提供——语言包不随程序打包，而是放在程序的数据目录里，运行时加载。任何人都可以据此翻译、分发语言包，无需改动或重新打包程序。

## 界面语言 vs 资源语言

首选项 → 常规 里有**两个**独立的语言设置，分开配置、互不影响：

| 设置 | 作用范围 | 说明 |
| --- | --- | --- |
| **界面语言** | 主界面框架 | 菜单、按钮、对话框、状态栏、面板标题等程序外壳文案 |
| **资源语言** | 各模块 / 节点内容 | 节点图里节点的内容、资源显示名等 |

你可以「英文界面 + 中文资源」，也可以反过来。缺少对应翻译时，各自回落到内置简体中文，不会出现空白或裸 key。

## 下载语言包

当前 Docs 仓库暂未随 WeConduct 0.9.1 发布官方 `en-US` 语言包。历史 0.8.2
语言包仍作为制作参考保留，不能视为 0.9.1 的官方语言包：

- [下载历史 0.8.2 en-US.zip](../../downloads/weconduct/0.8.2/en-US.zip)

该下载包基于 WeConduct 0.8.2。使用 0.9.1 时，建议先确认语言包覆盖的键与当前
程序资源一致；缺少的键会回落到内置简体中文。解压后得到一个 `en-US/` 文件夹。

## 安装步骤

1. 打开 **首选项 → 常规 → 数据目录 →「打开数据目录」按钮**，系统文件管理器会定位到数据目录。
2. 进入其中的 `languages/` 子目录（若不存在会在打开时自动创建）。
3. 把解压得到的 `en-US` 文件夹整个放进 `languages/`，最终结构：

    ```
    <数据目录>/languages/
    └── en-US/
        ├── manifest.json
        ├── framework.commandBar.json
        ├── framework.statusBar.json
        ├── …（其他 framework.*.json）
        └── nodegraph.base.json
    ```

4. 回到 **首选项 → 常规**，在「界面语言」「资源语言」下拉里选择 `English (US)`。切换即时生效。

> 若下拉里某个语言标注「未安装」，表示曾选过但当前数据目录下找不到对应包——重新放入即可，或改选其他语言。

## 数据目录位置

- 打包版（桌面）：`%LOCALAPPDATA%\WeConduct\languages\`
- 最简单：用首选项里的「打开数据目录」按钮直达，不用手动拼路径。

## 制作语言包

### 目录与 manifest.json

一个 locale = 一个文件夹，内含 `manifest.json` 与若干翻译 json：

```json
{
  "locale": "en-US",
  "display_name": "English (US)",
  "author": "你的名字",
  "version": "1.0.0",
  "description": "简介"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `locale` | 建议 | 语言标识，也是首选项里保存的值。缺失时回落为文件夹名。 |
| `display_name` | 建议 | 下拉里显示的名字。缺失时回落为文件夹名。 |
| `version` | 否 | **语言包自身**的版本，由你维护，与程序版本无关。 |
| `author` / `description` | 否 | 元信息。 |

### 按模块拆分 + 路径即命名空间

翻译内容按模块拆进多个 json 文件。**文件的相对路径决定它的命名空间**——目录分隔符和文件名里的点都会引入层级：

| 文件 | 命名空间前缀 |
| --- | --- |
| `framework.commandBar.json` | `framework.commandBar.` |
| `framework.statusBar.json` | `framework.statusBar.` |
| `nodegraph.base.json` | `nodegraph.base.` |
| `nodegraph/execution.json` | `nodegraph.execution.`（子目录等价写法） |

文件内部**只写该前缀以下的子树，不重复前缀**。例如 `framework.commandBar.json`：

```json
{
  "menu": { "file": "File", "edit": "Edit" },
  "toast": { "created": "Created" }
}
```

会被读成 `framework.commandBar.menu.file` = `"File"`。这样「框架一个模块一个文件、节点每类一个文件」，便于分工维护。官方 `en-US` 包即按此拆成 20+ 个 `framework.*.json` + `nodegraph.base.json`，是最完整的参考模板——直接改词即可做出新语言。

### 只需翻译你想覆盖的键

程序里每处文案都带一个**内置简体中文兜底**：

- 提供了某个 key → 显示你的翻译；
- 没提供 / 整个包缺失 / json 损坏 → 自动回落到内置中文（绝不显示裸 key）。

因此可以**增量翻译**：先译菜单，其余留空，缺的部分自动显示中文。带占位符的文案（如 `Compile #{n}`）要保留 `{n}` 占位不动。

## 常见问题

- **改了语言包但没生效？** 确认文件夹在 `languages/` 下且含 `manifest.json`；回首选项重新选一次语言。
- **下拉里没有我的语言？** 检查 `manifest.json` 是否为合法 JSON、`locale` 是否填写。
- **部分文案还是中文？** 该 key 未翻译或 json 有误——补上对应键即可，这是设计上的安全回落。
- **界面变了但节点内容没变（或反之）？** 界面语言与资源语言是两个设置，分别检查。
