---
product: weconduct
version: 0.8.1
doc_id: weconduct:reference:known-limitations:0.8.1
---

# WeConduct 0.8.1 已知限制

- **执行历史**：只保存标准运行和 Debug 会话摘要，不是完整节点事件、诊断或变量快照归档。
- **项目身份字段**：项目设置面板显示 `description`、`version`、`author`、`tags`，但 0.8.1 加载和保存链路只处理 `name`。
- **资源导入、导出**：后端存在相关能力，但资源管理面板没有用户入口。
- **嵌入资源开关**：`include_embedded_resources` 存在于配置，但项目设置面板没有独立控件。
- **快捷键**：帮助窗口显示 `Ctrl+O` / `Ctrl+N`，全局处理器未注册；`Ctrl+S` 只提示使用菜单保存。
- **文件允许根**：restricted 模式不会自动加入用户 `Documents`，默认动态根包含项目、工作区、状态目录和 `Downloads`。
- **外部绑定**：0.8.1 只支持把路径字符串绑定到 `initial_variable` 目标。
- **资源详情页导航**：节点详情通过聚合页和搜索进入，不在左侧导航中平铺 126 项。

这些限制描述当前版本，不代表后续版本承诺。遇到与本页不同的行为时，先确认程序版本和项目迁移状态。

