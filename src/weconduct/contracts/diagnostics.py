from typing import Any, Literal

from pydantic import BaseModel, Field


class Diagnostic(BaseModel):
    diagnostic_id: str
    stage: Literal["parse", "bind", "validate", "normalize", "lower", "emit"]
    severity: Literal["info", "warning", "degraded", "error", "fatal"]
    category: str
    message: str
    object_ref: str | None = None
    trace_ref: str | None = None
    stage_extension: dict[str, Any] = Field(default_factory=dict)
    degraded_extension: dict[str, Any] | None = None


class DiagnosticCatalog(BaseModel):
    entries: list[Diagnostic] = Field(default_factory=list)


def create_empty_diagnostic_catalog() -> DiagnosticCatalog:
    return DiagnosticCatalog()
