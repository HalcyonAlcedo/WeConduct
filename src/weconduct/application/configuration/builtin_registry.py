from __future__ import annotations

from .registry import ConfigurationRegistry
from .schema import ConfigField, ConfigurationDomain


def build_builtin_configuration_registry() -> ConfigurationRegistry:
    registry = ConfigurationRegistry()
    _register_program_domains(registry)
    _register_program_fields(registry)
    _register_project_domains(registry)
    _register_project_fields(registry)
    _register_graph_domains(registry)
    _register_graph_fields(registry)
    return registry


def _register_program_domains(registry: ConfigurationRegistry) -> None:
    for key, label, order in (
        ("ui", "程序设置", 10),
        ("workspace", "工作区设置", 20),
        ("security", "安全设置", 30),
        ("python_defaults", "Python 运行时设置", 40),
        ("updates", "更新设置", 50),
    ):
        registry.register_domain(
            ConfigurationDomain(scope="program", key=key, label=label, order=order)
        )


def _register_program_fields(registry: ConfigurationRegistry) -> None:
    _register_fields(
        registry,
        scope="program",
        domain="ui",
        consumer="desktop_shell.launcher",
        field_consumers={
            "theme": "themeStore.applyTheme",
            "language": "main.ts.i18n.locale",
            "font_scale": "styles.tokens.fontScale",
        },
        fields=(
            ("default_window_size", "object", {"width": 1440, "height": 900}),
            # Resource language is a free-form string for the same reason as
            # `language` below: it selects an external, runtime-loaded pack
            # (drives per-module/node-graph content + backend display_name_i18n),
            # so any on-disk locale must validate. Independent of the UI language.
            ("resource_language", "string", "zh-CN"),
            ("theme", "enum", "system", ("light", "dark", "system")),
            # UI locale is a free-form string, not a fixed enum: language packs
            # are external (loaded from the program's languages/ dir at runtime),
            # so any on-disk locale must validate. "zh-CN" is the built-in source
            # locale (hardcoded Chinese fallback) and needs no pack. The UI
            # resolves availability at runtime and degrades to the source locale.
            ("language", "string", "zh-CN"),
            ("font_scale", "float", 1.0),
        ),
    )
    _register_fields(
        registry,
        scope="program",
        domain="workspace",
        consumer="CompilationWorkbenchService",
        field_consumers={
            "default_project_directory": "CompilationWorkbenchService._get_default_project_directory",
            "recent_project_limit": "CompilationWorkbenchService._get_recent_project_limit",
            "preferences_auto_save": "PreferencesPanel.auto_save",
        },
        fields=(
            ("default_project_directory", "nullable_string", None),
            ("recent_project_limit", "integer", 10),
            ("preferences_auto_save", "boolean", True),
        ),
    )
    security_boolean_defaults = (
        ("confirm_high_risk_actions", True),
        ("allow_external_programs", False),
        ("allow_file_access", False),
        ("file_access_require_absolute_path", False),
        ("allow_browser_executor", False),
        ("allow_browser_screenshots", True),
        ("allow_cookie_manipulation", True),
        ("allow_browser_storage_manipulation", True),
        ("allow_browser_uploads", True),
        ("allow_browser_downloads", False),
        ("allow_new_browser_windows", True),
        ("allow_local_network_access", False),
        ("allow_remote_network_access", False),
        ("allow_python_execution", False),
        ("allow_js_injection", False),
        ("allow_js_evaluation", False),
        ("show_security_warnings_in_runtime", True),
        ("log_security_events", True),
    )
    _register_fields(
        registry,
        scope="program",
        domain="security",
        consumer="CompilationWorkbenchService._build_runtime_execution_settings",
        fields=tuple(
            (key, "boolean", default) for key, default in security_boolean_defaults
        ),
    )
    _register_fields(
        registry,
        scope="program",
        domain="security",
        consumer="CompilationWorkbenchService._build_runtime_execution_settings",
        fields=(
            ("file_access_scope", "enum", "restricted", ("restricted", "custom_roots", "allow_all")),
            ("file_access_allowed_roots", "string_list", []),
            ("file_access_blocked_roots", "string_list", []),
            ("file_access_allowed_extensions", "string_list", []),
            ("file_access_blocked_extensions", "string_list", []),
        ),
    )
    _register_fields(
        registry,
        scope="program",
        domain="python_defaults",
        consumer="CompilationWorkbenchService._build_runtime_execution_settings",
        fields=(
            ("python_executable_path", "nullable_string", None),
            ("timeout_seconds", "integer", 60),
            ("capture_stdout_stderr", "boolean", True),
            ("sandbox_mode", "enum", "restricted", ("restricted",)),
            ("variable_apply_mode", "enum", "staged", ("staged", "immediate")),
            (
                "blocked_import_modules",
                "string_list",
                ["ctypes", "importlib", "multiprocessing", "os", "socket", "subprocess"],
            ),
        ),
    )
    _register_fields(
        registry,
        scope="program",
        domain="python_defaults",
        consumer="CompilationWorkbenchService._build_default_project_python_runtime_profile",
        fields=(
            ("default_python_version_spec", "string", ">=3.11"),
            ("default_cache_location_mode", "enum", "software_cache", ("software_cache", "project_cache")),
            ("default_project_cache_mode", "enum", "full_venv", ("full_venv", "wheelhouse_rebuild")),
            ("default_requirements_source_mode", "enum", "inline", ("inline", "requirements_txt", "lock_file")),
            (
                "default_package_embed_mode",
                "enum",
                "wheelhouse_rebuild",
                ("none", "wheelhouse_rebuild", "full_venv"),
            ),
        ),
    )
    _register_fields(
        registry,
        scope="program",
        domain="updates",
        consumer="App.vue.onMounted",
        fields=(("check_updates_on_startup", "boolean", False),),
    )


def _register_project_domains(registry: ConfigurationRegistry) -> None:
    for key, label, order in (
        ("identity", "项目设置", 10),
        ("debug", "调试设置", 20),
        ("resources", "资源设置", 30),
        ("packaging", "打包设置", 40),
        ("python_profile", "项目 Python 运行时", 50),
    ):
        registry.register_domain(
            ConfigurationDomain(scope="project", key=key, label=label, order=order)
        )


def _register_project_fields(registry: ConfigurationRegistry) -> None:
    _register_fields(
        registry,
        scope="project",
        domain="identity",
        consumer="CompilationWorkbenchService.project_metadata",
        fields=(
            ("name", "string", "WeConduct Workspace"),
            ("description", "string", ""),
            ("version", "string", "0.1.0"),
            ("author", "string", ""),
            ("tags", "string_list", []),
        ),
    )
    _register_fields(
        registry,
        scope="project",
        domain="debug",
        consumer="DebugSessionHistoryStore",
        fields=(("history_retention_limit", "integer", 10),),
    )
    _register_fields(
        registry,
        scope="project",
        domain="resources",
        consumer="CompilationWorkbenchService.package_resources",
        fields=(
            ("external_resources", "object", []),
            ("embedded_resources", "string_list", []),
        ),
    )
    _register_fields(
        registry,
        scope="project",
        domain="packaging",
        consumer="CompilationWorkbenchService.build_project_package",
        fields=(
            ("default_output_name", "string", "weconduct-project.wcrun"),
            ("include_embedded_resources", "boolean", True),
        ),
    )
    _register_fields(
        registry,
        scope="project",
        domain="python_profile",
        consumer="CompilationWorkbenchService.project_python_runtime",
        fields=(
            ("runtime_enabled", "boolean", False),
            ("python_version_spec", "string", "3.13"),
            ("interpreter_strategy", "enum", "bundled", ("bundled", "system", "custom_path")),
            ("custom_python_path", "nullable_string", None),
            ("cache_location_mode", "enum", "software_cache", ("software_cache", "project_cache")),
            ("project_cache_mode", "enum", "wheelhouse_rebuild", ("full_venv", "wheelhouse_rebuild")),
            ("requirements_source_mode", "enum", "inline", ("inline", "requirements_txt", "lock_file")),
            ("requirements_inline", "string_list", []),
            ("requirements_file_path", "nullable_string", None),
            ("lock_file_path", "nullable_string", None),
            ("index_strategy", "enum", "default", ("default", "custom")),
            ("custom_index_url", "nullable_string", None),
            ("auto_prepare_on_run", "boolean", True),
            ("package_embed_mode", "enum", "wheelhouse_rebuild", ("none", "wheelhouse_rebuild", "full_venv")),
        ),
    )


def _register_graph_domains(registry: ConfigurationRegistry) -> None:
    registry.register_domain(
        ConfigurationDomain(
            scope="graph",
            key="editor_preferences",
            label="节点图设置",
            order=10,
        )
    )
    registry.register_domain(
        ConfigurationDomain(
            scope="graph",
            key="entrypoint_runtime",
            label="运行默认值",
            order=20,
        )
    )


def _register_graph_fields(registry: ConfigurationRegistry) -> None:
    _register_fields(
        registry,
        scope="graph",
        domain="editor_preferences",
        consumer="CompilationWorkbenchService._get_graph_save_conflict_policy",
        field_consumers={
            "snap_to_grid": "VueFlowGraph.snapToGrid",
            "grid_enabled": "VueFlowGraph.Background",
            "show_node_id_on_node": "BaseNode.nodeId",
            "show_disabled_resource_badge": "BaseNode.disabledBadge",
            "auto_open_node_on_drop": "VueFlowGraph.onDrop",
            "confirm_delete_node": "VueFlowGraph/App.deleteNode",
            "show_inline_config_summary": "BaseNode.configSections",
            "edge_line_style": "graphStore.toVueFlow.edgeType",
        },
        fields=(
            ("save_conflict_policy", "enum", "prefer_current_graph", ("prefer_current_graph", "strict")),
            ("snap_to_grid", "boolean", True),
            ("grid_enabled", "boolean", True),
            ("show_node_id_on_node", "boolean", True),
            ("show_disabled_resource_badge", "boolean", True),
            ("auto_open_node_on_drop", "boolean", True),
            ("confirm_delete_node", "boolean", True),
            ("show_inline_config_summary", "boolean", True),
            ("edge_line_style", "enum", "smoothstep", ("smoothstep", "straight", "bezier")),
        ),
    )
    _register_fields(
        registry,
        scope="graph",
        domain="entrypoint_runtime",
        consumer="flow.start.node_config",
        fields=(
            ("initial_variables", "object", {}),
            ("browser_config", "object", {"headless": True, "slow_mo_ms": 0}),
        ),
    )


def _register_fields(
    registry: ConfigurationRegistry,
    *,
    scope: str,
    domain: str,
    consumer: str,
    fields: tuple,
    field_consumers: dict[str, str] | None = None,
) -> None:
    for order, raw_field in enumerate(fields, start=1):
        key, field_type, default, *options = raw_field
        registry.register_field(
            ConfigField(
                scope=scope,
                domain=domain,
                key=key,
                field_type=field_type,
                default=default,
                consumer=(field_consumers or {}).get(key, consumer),
                order=order,
                options=tuple(options[0]) if options else (),
            )
        )
