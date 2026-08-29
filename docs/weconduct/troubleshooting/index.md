---
product: weconduct
version: 0.9.1
doc_id: weconduct:troubleshooting:index
---

# 故障排查

先按界面症状选择页面，不要只凭最后一条错误猜测根因。

- [项目无法创建、打开或恢复](project-and-startup.md)
- [节点图无法校验或编译](graph-validation.md)
- [标准运行或 Debug 异常](runtime-and-debug.md)
- [浏览器与网络节点失败](browser-and-network.md)
- [文件、Python 与 `.wcrun` 问题](files-python-and-packages.md)

## 通用排查顺序

1. 记录当前项目路径、会话 ID、节点 ID 和资源键。
2. 在诊断面板区分 `compilation`、`runtime`、`debug` 和安全权限来源。
3. 先修第一条 `error` 或 `fatal`，信息级 `*.completed` 不是失败。
4. 保存项目后重新校验；打包预检固定读取已保存项目。
5. 仍无法定位时，保留原始错误文本、操作顺序和最小项目。
