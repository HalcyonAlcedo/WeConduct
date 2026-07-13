from __future__ import annotations

from copy import deepcopy
from typing import Callable


class ProjectConfigurationRepository:
    """Bridges registered project configuration fields to the bound project document."""

    def __init__(self, get_document: Callable[[], dict], update_document: Callable[[dict], None]) -> None:
        self._get_document = get_document
        self._update_document = update_document

    def load(self) -> dict:
        document = self._get_document()
        identity = document.get("project_identity") if isinstance(document.get("project_identity"), dict) else {}
        debug = document.get("debug_profile") if isinstance(document.get("debug_profile"), dict) else {}
        packaging = document.get("packaging") if isinstance(document.get("packaging"), dict) else {}
        policy = document.get("resource_policy") if isinstance(document.get("resource_policy"), dict) else {}
        python_profile = document.get("python_runtime_profile") if isinstance(document.get("python_runtime_profile"), dict) else {}
        return {
            "identity": {key: deepcopy(identity.get(key)) for key in ("name", "description", "version", "author", "tags") if key in identity},
            "debug": {"history_retention_limit": deepcopy(debug.get("history_retention_limit"))} if "history_retention_limit" in debug else {},
            "resources": {"external_resources": deepcopy(document.get("external_resources", [])), "embedded_resources": deepcopy(policy.get("embedded_resources", []))},
            "packaging": {key: deepcopy(packaging.get(key)) for key in ("default_output_name", "include_embedded_resources") if key in packaging},
            "python_profile": {
                key: deepcopy(python_profile.get(key))
                for key in (
                    "runtime_enabled", "python_version_spec", "interpreter_strategy",
                    "custom_python_path", "cache_location_mode", "project_cache_mode",
                    "requirements_source_mode", "requirements_inline", "requirements_file_path",
                    "lock_file_path", "index_strategy", "custom_index_url",
                    "auto_prepare_on_run", "package_embed_mode",
                )
                if key in python_profile
            },
        }

    def save(self, values: dict) -> None:
        document = self._get_document()
        identity = document.setdefault("project_identity", {})
        debug = document.setdefault("debug_profile", {})
        packaging = document.setdefault("packaging", {})
        policy = document.setdefault("resource_policy", {})
        python_profile = document.setdefault("python_runtime_profile", {})
        identity.update(deepcopy(values.get("identity", {})))
        debug.update(deepcopy(values.get("debug", {})))
        resources = values.get("resources", {})
        if isinstance(resources, dict):
            if "external_resources" in resources:
                document["external_resources"] = deepcopy(resources["external_resources"])
            if "embedded_resources" in resources:
                policy["embedded_resources"] = deepcopy(resources["embedded_resources"])
        packaging.update(deepcopy(values.get("packaging", {})))
        python_profile.update(deepcopy(values.get("python_profile", {})))
        document.pop("runtime_defaults", None)
        self._update_document(document)
