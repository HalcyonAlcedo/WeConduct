import json
import re

from pydantic import BaseModel, ConfigDict, Field


class LegacyAutomationStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    step_id: str | None = None
    action: str


class LegacyWebControlMainFlow(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_info: dict = Field(default_factory=dict)
    program_config: dict = Field(default_factory=dict)
    browser_config: dict = Field(default_factory=dict)
    global_config: dict = Field(default_factory=dict)
    dialog_config: dict = Field(default_factory=dict)
    debug_config: dict = Field(default_factory=dict)
    initial_variables: dict = Field(default_factory=dict)
    automation_steps: list[LegacyAutomationStep] = Field(default_factory=list)

    def build_root_metadata(self) -> dict:
        return {
            "source_kind": "webcontrol_main_flow",
            "project_info": dict(self.project_info),
            "program_config": dict(self.program_config),
            "browser_config": dict(self.browser_config),
            "global_config": dict(self.global_config),
            "dialog_config": dict(self.dialog_config),
            "debug_config": dict(self.debug_config),
            "initial_variables": dict(self.initial_variables),
        }


def parse_legacy_webcontrol_main_flow(source_text: str) -> LegacyWebControlMainFlow:
    payload = json.loads(source_text)
    return LegacyWebControlMainFlow.model_validate(payload)


class LegacyWebControlBlueprint(BaseModel):
    model_config = ConfigDict(extra="allow")

    blueprint_info: dict = Field(default_factory=dict)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    automation_steps: list[LegacyAutomationStep] = Field(default_factory=list)

    def build_root_metadata(self) -> dict:
        return {
            "source_kind": "webcontrol_blueprint",
            "blueprint_info": dict(self.blueprint_info),
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
        }


def parse_legacy_webcontrol_blueprint(source_text: str) -> LegacyWebControlBlueprint:
    payload = json.loads(source_text)
    return LegacyWebControlBlueprint.model_validate(payload)


def build_legacy_webcontrol_blueprint_custom_node_graph_seed(
    source_text: str,
    *,
    fallback_name: str,
) -> dict:
    document = parse_legacy_webcontrol_blueprint(source_text)
    blueprint_info = dict(document.blueprint_info)
    blueprint_id = blueprint_info.get("id") if isinstance(blueprint_info.get("id"), str) else None
    blueprint_name = (
        blueprint_info.get("name") if isinstance(blueprint_info.get("name"), str) else None
    )
    display_name = (blueprint_name or blueprint_id or fallback_name or "Imported Blueprint").strip()
    resource_slug_source = blueprint_id or display_name or fallback_name or "imported-blueprint"
    resource_slug = _slugify_legacy_blueprint_identifier(resource_slug_source)
    compatibility_aliases = [blueprint_id.strip()] if isinstance(blueprint_id, str) and blueprint_id.strip() else []
    return {
        "resource_id": f"custom_node_graph:{resource_slug}",
        "resource_type": "custom_node_graph",
        "display_name": display_name,
        "resource_key": f"custom_node_graph:{resource_slug}",
        "enabled": True,
        "origin": "project",
        "description": "Imported from legacy WebControl blueprint.",
        "implementation_kind": "project_component",
        "compatibility_aliases": compatibility_aliases,
        "input_schema": dict(document.input_schema),
        "output_schema": dict(document.output_schema),
    }


def _slugify_legacy_blueprint_identifier(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip("-._")
    return normalized or "imported-blueprint"
