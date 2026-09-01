from __future__ import annotations

from importlib import import_module
from typing import Any


_PUBLIC_EXPORTS = {
    "CompilationWorkbenchService": (".compilation_workbench_service", "CompilationWorkbenchService"),
    "GraphDocumentRevisionConflictError": (".compilation_workbench_service", "GraphDocumentRevisionConflictError"),
    "build_conversion_report": (".legacy_webcontrol_converter", "build_conversion_report"),
    "convert_legacy_webcontrol_project": (".legacy_webcontrol_converter", "convert_legacy_webcontrol_project"),
    "RuntimeSessionStreamBroker": (".runtime_session_stream", "RuntimeSessionStreamBroker"),
    "HostOperationService": (".operations", "HostOperationService"),
    "OAuthInteractiveService": (".oauth_interactive", "OAuthInteractiveService"),
    "OAuthInteractiveError": (".oauth_interactive", "OAuthInteractiveError"),
    "OperationDescriptor": (".operations", "OperationDescriptor"),
    "OperationRegistry": (".operations", "OperationRegistry"),
    "OperationRegistryError": (".operations", "OperationRegistryError"),
    "UpdateService": (".update_service", "UpdateService"),
    "FileWorkspaceStateStore": (".workspace_state_store", "FileWorkspaceStateStore"),
    "InMemoryWorkspaceStateStore": (".workspace_state_store", "InMemoryWorkspaceStateStore"),
    "WorkspaceStateStore": (".workspace_state_store", "WorkspaceStateStore"),
}

__all__ = list(_PUBLIC_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name, attribute_name = _PUBLIC_EXPORTS.get(name, (None, None))
    if module_name is None or attribute_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
