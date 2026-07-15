---
product: weconduct
version: 0.8.1
doc_id: weconduct:troubleshooting:files-python-and-packages
---

# 文件、Python 与 `.wcrun` 问题

## 文件访问被拒绝

常见错误：

```text
file.access_denied
file.path_required
```

开启 `allow_file_access`，并确认路径位于项目目录、工作区目录、状态目录、用户 `Downloads` 或 `custom_roots`。0.8.1 不会自动允许用户 `Documents`。

## Python 节点提示运行时未启用

原始错误可能是：

```text
python.run requires project python runtime to be enabled
project python runtime is disabled
```

在项目设置启用 `runtime_enabled`，保存后执行健康检查和准备。`python.run` 还需要 `allow_python_execution`；导入阻止列表和执行超时仍然生效。

## `.wcrun` 预检通过但目标机器不能运行

预检只检查已保存图诊断和必需外部资源绑定。Python runtime、安全权限、包内条目和目标环境兼容性在检查、加载和运行就绪阶段判断。

## 包加载提示安全需求阻断

诊断类别可包含：

```text
package.security.requirement_blocked
```

逐项核对 `setting_field`。一键放行会修改程序级配置，不只影响当前包；不可信包不要直接放行全部能力。

## 外部资源仍未就绪

0.8.1 的外部绑定值会解析为绝对路径，绑定目标只支持 `initial_variable`。输入真实路径字符串后重新检查运行就绪状态。

