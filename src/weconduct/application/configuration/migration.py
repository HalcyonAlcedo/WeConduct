from __future__ import annotations

from copy import deepcopy

from .program_repository import FileProgramConfigurationRepository
from .graph_repository import FileGraphConfigurationRepository
from .registry import ConfigurationRegistry


LEGACY_PROGRAM_SECTION_DOMAINS = {
    "program_settings": ("ui", "workspace", "updates"),
    "security_settings": ("security",),
    "python_runtime_settings": ("python_defaults",),
}


def migrate_program_configuration(
    *,
    repository: FileProgramConfigurationRepository,
    registry: ConfigurationRegistry,
) -> dict:
    if repository.is_current():
        values = repository.load()
        if _replace_legacy_response_limit_defaults(values):
            repository.save(values)
            return {
                "status": "migrated_response_limits",
                "diagnostics": [
                    {
                        "category": "configuration.migration.response_limits_defaults",
                        "path": "/network_defaults/response_limits",
                        "severity": "info",
                    }
                ],
            }
        return {"status": "already_current", "diagnostics": []}
    if not repository.path.exists():
        return {"status": "not_required", "diagnostics": []}

    legacy_payload = repository.read_legacy_payload()
    values = _build_default_values(registry=registry, scope="program")
    diagnostics: list[dict] = []
    for legacy_section, domains in LEGACY_PROGRAM_SECTION_DOMAINS.items():
        section_values = legacy_payload.get(legacy_section)
        if not isinstance(section_values, dict):
            continue
        for key, value in section_values.items():
            target_domain = _find_target_domain(
                registry=registry,
                scope="program",
                domains=domains,
                key=key,
            )
            if target_domain is None:
                diagnostics.append(
                    {
                        "category": "configuration.migration.unregistered_field",
                        "path": f"/{legacy_section}/{key}",
                        "severity": "info",
                    }
                )
                continue
            values[target_domain][key] = deepcopy(value)
    repository.backup_legacy_file()
    repository.save(values)
    return {"status": "migrated", "diagnostics": diagnostics}


def migrate_graph_configuration(
    *,
    repository: FileGraphConfigurationRepository,
    registry: ConfigurationRegistry,
    legacy_preferences: dict,
) -> dict:
    if repository.is_current():
        return {"status": "already_current", "diagnostics": []}
    graph_settings = legacy_preferences.get("graph_settings")
    if not repository.path.exists() and not isinstance(graph_settings, dict):
        return {"status": "not_required", "diagnostics": []}
    values = _build_default_values(registry=registry, scope="graph")
    if isinstance(graph_settings, dict):
        policy = graph_settings.get("save_conflict_policy")
        if policy in {"prefer_current_graph", "strict"}:
            values["editor_preferences"]["save_conflict_policy"] = policy
    repository.save(values)
    return {"status": "migrated", "diagnostics": []}


def _build_default_values(*, registry: ConfigurationRegistry, scope: str) -> dict:
    values: dict[str, dict] = {}
    for config_field in registry.fields_for_scope(scope):
        values.setdefault(config_field.domain, {})[config_field.key] = deepcopy(
            config_field.default
        )
    return values


def _replace_legacy_response_limit_defaults(values: dict) -> bool:
    network_defaults = values.get("network_defaults")
    if not isinstance(network_defaults, dict):
        return False
    response_limits = network_defaults.get("response_limits")
    if not isinstance(response_limits, dict):
        return False
    if (
        response_limits.get("max_bytes") != 0
        or response_limits.get("max_in_memory_bytes") != 0
    ):
        return False
    response_limits["max_bytes"] = None
    response_limits["max_in_memory_bytes"] = None
    return True


def _find_target_domain(
    *,
    registry: ConfigurationRegistry,
    scope: str,
    domains: tuple[str, ...],
    key: str,
) -> str | None:
    for domain in domains:
        try:
            registry.get_field(scope=scope, domain=domain, key=key)
        except ValueError:
            continue
        return domain
    return None
