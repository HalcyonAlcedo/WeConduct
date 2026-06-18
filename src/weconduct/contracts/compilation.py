from typing import Literal

from pydantic import BaseModel, Field

from .diagnostics import DiagnosticCatalog
from .graph import GraphModel

CompilationStage = Literal["parse", "bind", "validate", "normalize", "lower", "emit"]


class CompilationSource(BaseModel):
    kind: Literal[
        "graph_workspace",
        "native_flow",
        "webcontrol_main_flow",
        "webcontrol_blueprint",
    ]
    entry_document: str
    source_text: str


class CompilationOptions(BaseModel):
    stop_on_fatal: bool = True


class CompilationRequest(BaseModel):
    compilation_id: str
    source: CompilationSource
    options: CompilationOptions = Field(default_factory=CompilationOptions)


class StageOutcomeSummary(BaseModel):
    stage: CompilationStage
    status: Literal["pending", "succeeded", "failed", "skipped"] = "pending"
    diagnostic_count: int = 0


class CompilationSummary(BaseModel):
    compilation_id: str
    stage_outcomes: list[StageOutcomeSummary]
    duration_ms: int | None = None


class CompilationOutcome(BaseModel):
    graph_model: GraphModel | None
    compilation_summary: CompilationSummary
    diagnostic_catalog: DiagnosticCatalog


def create_initial_summary(compilation_id: str) -> CompilationSummary:
    return CompilationSummary(
        compilation_id=compilation_id,
        stage_outcomes=[
            StageOutcomeSummary(stage="parse"),
            StageOutcomeSummary(stage="bind"),
            StageOutcomeSummary(stage="validate"),
            StageOutcomeSummary(stage="normalize"),
            StageOutcomeSummary(stage="lower"),
            StageOutcomeSummary(stage="emit"),
        ],
    )
