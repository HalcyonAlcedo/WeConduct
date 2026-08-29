---
product: weconduct
version: 0.9.1
doc_id: weconduct:guide:webcontrol-conversion
---

# 转换 WebControl 项目

选择 **文件 → 转换 WebControl** 打开转换窗口。转换会生成新的 WeConduct 项目，不会原地修改旧文件。

## 输入

- **主流程文件**（`source_path`）：必填，支持 YAML（`.yaml` / `.yml`）或 JSON 主流程。0.9.1 的转换器不解析 XML。
- **蓝图文件**（`blueprint_paths`）：可选，可逐个添加。
- **蓝图目录**：可选，扫描目录内蓝图。
- **输出项目路径**：必填 `.weconduct.json`。
- **覆盖已有输出**：默认关闭。

还可选择转换后自动打开、保留 legacy 元信息和写出报告。

## 转换结果

主流程会生成 `flow.start` 和按原步骤顺序连接的可编辑节点。蓝图会转换为项目资源。启用报告后，输出项目的 `.data` 目录包含 `conversion-report.json`，记录源类型、节点/边数量、导入蓝图、生成资源、warning 和 error。

保留 legacy 元信息时，节点配置包含 `legacy_webcontrol_step`，用于追溯原 `source_path`、步骤编号、action 和原声明；它不是新节点的运行参数。

## 不支持与需人工检查的内容

- 主流程 action 不在 `LEGACY_ACTION_MAPPINGS` 时，转换会失败并指出不支持的 action。
- 非对象步骤、缺少 action、无效 YAML/JSON 会失败；XML 不在支持范围内。
- 蓝图导入失败或重复时会记录 warning，并跳过该蓝图。
- 旧项目的程序、浏览器、对话框和 Debug 配置会保留为根元信息，但不保证自动等价为 0.9.1 的全部项目设置。
- 选择器、文件路径、外部依赖和安全权限需要在生成项目中人工复核。

转换后先查看报告和 **输出 → 诊断**，再保存并试运行生成项目。
