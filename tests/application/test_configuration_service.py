import json
from pathlib import Path

import pytest

from weconduct.application.configuration import (
    ConfigField,
    ConfigurationDomain,
    ConfigurationRegistry,
    ConfigurationService,
    HighRiskConfigurationChangeRequiredError,
    InMemoryConfigurationRepository,
)
from weconduct.application.compilation_workbench_service import CompilationWorkbenchService
from weconduct.application.configuration.builtin_registry import (
    build_builtin_configuration_registry,
)
from weconduct.application.configuration.migration import (
    migrate_graph_configuration,
    migrate_program_configuration,
)
from weconduct.application.configuration.program_repository import FileProgramConfigurationRepository
from weconduct.application.configuration.graph_repository import (
    FileGraphConfigurationRepository,
    WorkbenchGraphConfigurationRepository,
)
from weconduct.application.configuration.project_repository import (
    ProjectConfigurationRepository,
)


def build_service() -> ConfigurationService:
    registry = ConfigurationRegistry()
    registry.register_domain(
        ConfigurationDomain(
            scope="program",
            key="security",
            label="安全设置",
            order=10,
        )
    )
    registry.register_field(
        ConfigField(
            scope="program",
            domain="security",
            key="allow_file_access",
            field_type="boolean",
            default=False,
            consumer="runtime_execution_settings",
            risk_level="high",
        )
    )
    registry.register_domain(
        ConfigurationDomain(
            scope="program",
            key="python",
            label="Python 运行时设置",
            order=20,
        )
    )
    registry.register_field(
        ConfigField(
            scope="program",
            domain="python",
            key="blocked_import_modules",
            field_type="string_list",
            default=["os"],
            consumer="python_runtime_policy",
        )
    )
    return ConfigurationService(
        registry=registry,
        repositories={"program": InMemoryConfigurationRepository()},
    )


def test_preview_high_risk_replace_requires_confirmation() -> None:
    service = build_service()

    preview = service.preview(
        scope="program",
        operations=[
            {
                "op": "replace",
                "path": "/security/allow_file_access",
                "value": True,
            }
        ],
    )

    assert preview["confirmation_required"] is True
    assert preview["proposed_values"]["security"]["allow_file_access"] is True
    with pytest.raises(HighRiskConfigurationChangeRequiredError):
        service.apply(
            scope="program",
            operations=[
                {
                    "op": "replace",
                    "path": "/security/allow_file_access",
                    "value": True,
                }
            ],
        )


def test_builtin_external_api_configuration_requires_high_risk_confirmation() -> None:
    service = ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={"program": InMemoryConfigurationRepository()},
    )

    preview = service.preview(
        scope="program",
        operations=[
            {
                "op": "replace",
                "path": "/security/external_api_enabled",
                "value": True,
            }
        ],
    )

    assert preview["confirmation_required"] is True
    assert preview["high_risk_changes"] == [
        {
            "path": "/security/external_api_enabled",
            "from": False,
            "to": True,
        }
    ]


def test_apply_collection_add_and_remove_persists_only_registered_field() -> None:
    service = build_service()

    added = service.apply(
        scope="program",
        operations=[
            {
                "op": "add",
                "path": "/python/blocked_import_modules/-",
                "value": "socket",
            }
        ],
    )
    removed = service.apply(
        scope="program",
        operations=[
            {
                "op": "remove",
                "path": "/python/blocked_import_modules/0",
            }
        ],
    )

    assert added["values"]["python"]["blocked_import_modules"] == ["os", "socket"]
    assert removed["values"]["python"]["blocked_import_modules"] == ["socket"]


def test_apply_rejects_unknown_field_path() -> None:
    service = build_service()

    with pytest.raises(ValueError, match="configuration field not found"):
        service.apply(
            scope="program",
            operations=[
                {
                    "op": "replace",
                    "path": "/security/not_registered",
                    "value": True,
                }
            ],
        )


def test_registry_rejects_active_field_without_consumer() -> None:
    registry = ConfigurationRegistry()
    registry.register_domain(
        ConfigurationDomain(scope="program", key="ui", label="界面", order=10)
    )

    with pytest.raises(ValueError, match="active configuration field requires consumer"):
        registry.register_field(
            ConfigField(
                scope="program",
                domain="ui",
                key="theme",
                field_type="string",
                default="light",
            )
        )


def test_builtin_registry_exposes_only_active_fields_with_consumers() -> None:
    registry = build_builtin_configuration_registry()

    program_fields = registry.fields_for_scope("program")
    graph_fields = registry.fields_for_scope("graph")

    assert registry.get_field(
        scope="program",
        domain="workspace",
        key="recent_project_limit",
    ).consumer == "CompilationWorkbenchService._get_recent_project_limit"
    assert registry.get_field(
        scope="graph",
        domain="entrypoint_runtime",
        key="browser_config",
    ).consumer == "flow.start.node_config"
    assert {
        field.key
        for field in registry.fields_for_scope("graph")
        if field.domain == "editor_preferences"
    } == {
        "save_conflict_policy",
        "snap_to_grid",
        "grid_enabled",
        "show_node_id_on_node",
        "show_disabled_resource_badge",
        "auto_open_node_on_drop",
        "confirm_delete_node",
        "show_inline_config_summary",
        "edge_line_style",
    }
    assert registry.get_field(
        scope="project",
        domain="python_profile",
        key="runtime_enabled",
    ).consumer == "CompilationWorkbenchService.project_python_runtime"
    project_fields = registry.fields_for_scope("project")
    assert all(
        config_field.consumer
        for config_field in [*program_fields, *project_fields, *graph_fields]
    )
    with pytest.raises(ValueError, match="configuration field not found"):
        registry.get_field(
            scope="program",
            domain="compile",
            key="emit_runtime_plan",
        )


def test_schema_groups_registered_fields_by_domain() -> None:
    service = build_service()

    schema = service.get_schema(scope="program")

    assert schema == {
        "scope": "program",
        "domains": [
            {
                "key": "security",
                "label": "安全设置",
                "order": 10,
                "fields": [
                    {
                        "key": "allow_file_access",
                        "type": "boolean",
                        "default": False,
                        "risk_level": "high",
                        "status": "active",
                        "editable": True,
                    }
                ],
            },
            {
                "key": "python",
                "label": "Python 运行时设置",
                "order": 20,
                "fields": [
                    {
                        "key": "blocked_import_modules",
                        "type": "string_list",
                        "default": ["os"],
                        "risk_level": "normal",
                        "status": "active",
                        "editable": True,
                    }
                ],
            },
        ],
    }


def test_program_configuration_migration_converts_legacy_file_once(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "preferences_file_version": 1,
                "program_settings": {
                    "default_window_size": {"width": 1280, "height": 720},
                    "recent_project_limit": 5,
                    "theme": "dark",
                },
                "security_settings": {"allow_file_access": True},
            }
        ),
        encoding="utf-8",
    )
    repository = FileProgramConfigurationRepository(preferences_path)

    first = migrate_program_configuration(
        repository=repository,
        registry=build_builtin_configuration_registry(),
    )
    second = migrate_program_configuration(
        repository=repository,
        registry=build_builtin_configuration_registry(),
    )

    assert first["status"] == "migrated"
    assert first["diagnostics"] == []
    assert second["status"] == "already_current"
    assert preferences_path.with_suffix(".json.0.8.0.bak").exists() is True
    assert repository.load() == {
        "ui": {
            "default_window_size": {"width": 1280, "height": 720},
            "resource_language": "zh-CN",
            "theme": "dark",
            "language": "zh-CN",
            "font_scale": 1.0,
        },
        "workspace": {
            "default_project_directory": None,
            "recent_project_limit": 5,
            "preferences_auto_save": True,
        },
        "security": {
            "confirm_high_risk_actions": True,
            "allow_external_programs": False,
            "allow_file_access": True,
            "file_access_require_absolute_path": False,
            "allow_browser_executor": False,
            "allow_browser_screenshots": True,
            "allow_cookie_manipulation": True,
            "allow_browser_storage_manipulation": True,
            "allow_browser_uploads": True,
            "allow_browser_downloads": False,
            "allow_new_browser_windows": True,
            "allow_local_network_access": False,
            "allow_remote_network_access": False,
            "allow_python_execution": False,
            "allow_js_injection": False,
            "allow_js_evaluation": False,
            "show_security_warnings_in_runtime": True,
            "log_security_events": True,
            "file_access_scope": "restricted",
            "file_access_allowed_roots": [],
            "file_access_blocked_roots": [],
            "file_access_allowed_extensions": [],
            "file_access_blocked_extensions": [],
        },
        "python_defaults": {
            "python_executable_path": None,
            "timeout_seconds": 60,
            "capture_stdout_stderr": True,
            "sandbox_mode": "restricted",
            "variable_apply_mode": "staged",
            "blocked_import_modules": ["ctypes", "importlib", "multiprocessing", "os", "socket", "subprocess"],
            "default_python_version_spec": ">=3.11",
            "default_cache_location_mode": "software_cache",
            "default_project_cache_mode": "full_venv",
            "default_requirements_source_mode": "inline",
            "default_package_embed_mode": "wheelhouse_rebuild",
        },
        "updates": {"check_updates_on_startup": False},
    }


def test_configuration_migration_does_not_write_defaults_without_legacy_files(
    tmp_path: Path,
) -> None:
    registry = build_builtin_configuration_registry()
    program_repository = FileProgramConfigurationRepository(tmp_path / "preferences.json")
    graph_repository = FileGraphConfigurationRepository(tmp_path / "graph-preferences.json")

    program_result = migrate_program_configuration(
        repository=program_repository,
        registry=registry,
    )
    graph_result = migrate_graph_configuration(
        repository=graph_repository,
        registry=registry,
        legacy_preferences={},
    )

    assert program_result == {"status": "not_required", "diagnostics": []}
    assert graph_result == {"status": "not_required", "diagnostics": []}
    assert program_repository.path.exists() is False
    assert graph_repository.path.exists() is False


def test_program_configuration_reaches_workbench_consumer_without_legacy_projection() -> None:
    configuration_service = ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={
            "program": InMemoryConfigurationRepository(),
            "graph": InMemoryConfigurationRepository(),
            "project": InMemoryConfigurationRepository(),
        },
    )
    configuration_service.apply(
        scope="program",
        operations=[
            {
                "op": "replace",
                "path": "/security/allow_file_access",
                "value": True,
            }
        ],
        confirm_high_risk=True,
    )
    service = CompilationWorkbenchService(configuration_service=configuration_service)

    assert service._build_runtime_execution_settings()["allow_file_access"] is True
    assert service._get_recent_project_limit() == 10


def test_graph_save_conflict_policy_is_registered_and_patchable() -> None:
    service = ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={"graph": InMemoryConfigurationRepository()},
    )

    updated = service.apply(
        scope="graph",
        operations=[
                {
                    "op": "replace",
                    "path": "/editor_preferences/save_conflict_policy",
                    "value": "strict",
            }
        ],
    )

    assert updated["values"]["editor_preferences"]["save_conflict_policy"] == "strict"
    assert service.get_schema(scope="graph")["domains"][0]["key"] == "editor_preferences"


def test_graph_save_conflict_policy_reaches_workbench_consumer() -> None:
    configuration_service = ConfigurationService(
        registry=build_builtin_configuration_registry(),
        repositories={
            "program": InMemoryConfigurationRepository(),
            "graph": InMemoryConfigurationRepository(),
        },
    )
    configuration_service.apply(
        scope="graph",
        operations=[
            {
                "op": "replace",
                "path": "/editor_preferences/save_conflict_policy",
                "value": "strict",
            }
        ],
    )
    service = CompilationWorkbenchService(
        configuration_service=configuration_service,
    )

    assert service._get_graph_save_conflict_policy() == "strict"


def test_project_repository_maps_python_profile_without_overwriting_runtime_status() -> None:
    document = {
        "project_identity": {"name": "demo"},
        "python_runtime_profile": {
            "runtime_enabled": False,
            "python_version_spec": "3.13",
            "last_health_status": "ready",
        },
    }

    repository = ProjectConfigurationRepository(
        lambda: document,
        lambda updated: document.update(updated),
    )

    loaded = repository.load()
    loaded["python_profile"]["runtime_enabled"] = True
    repository.save(loaded)

    assert loaded["python_profile"]["python_version_spec"] == "3.13"
    assert document["python_runtime_profile"]["runtime_enabled"] is True
    assert document["python_runtime_profile"]["last_health_status"] == "ready"


def test_graph_repository_combines_editor_preferences_with_flow_start_runtime() -> None:
    editor_repository = InMemoryConfigurationRepository(
        {"editor_preferences": {"save_conflict_policy": "strict"}}
    )
    runtime_defaults = {
        "initial_variables": {"username": "before"},
        "browser_config": {"headless": True},
    }
    updates: list[dict] = []
    repository = WorkbenchGraphConfigurationRepository(
        editor_repository=editor_repository,
        get_entrypoint_runtime=lambda: runtime_defaults,
        update_entrypoint_runtime=lambda values: updates.append(values),
    )

    loaded = repository.load()
    repository.save(
        {
            "editor_preferences": {"save_conflict_policy": "prefer_current_graph"},
            "entrypoint_runtime": {
                "initial_variables": {"username": "after"},
                "browser_config": {"headless": False},
            },
        }
    )

    assert loaded == {
        "editor_preferences": {"save_conflict_policy": "strict"},
        "entrypoint_runtime": runtime_defaults,
    }
    assert editor_repository.load() == {
        "editor_preferences": {"save_conflict_policy": "prefer_current_graph"}
    }
    assert updates == [
        {
            "initial_variables": {"username": "after"},
            "browser_config": {"headless": False},
        }
    ]
