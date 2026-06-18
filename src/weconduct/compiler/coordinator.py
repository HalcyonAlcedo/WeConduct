from json import JSONDecodeError
from typing import Protocol

from pydantic import ValidationError

from weconduct.contracts import CompilationOutcome, Diagnostic, DiagnosticCatalog

from .errors import CompilationAbortedError
from .stage_state import StageState


class StageHandler(Protocol):
    stage_name: str

    def run(self, state: StageState) -> None:
        ...


class CompilationPipelineCoordinator:
    def __init__(self, stages: list[StageHandler]) -> None:
        self._stages = stages

    def run(self, state: StageState) -> CompilationOutcome:
        try:
            for stage in self._stages:
                stage.run(state)
        except CompilationAbortedError:
            raise
        except (JSONDecodeError, ValidationError) as exc:
            state.diagnostics.append(
                Diagnostic(
                    diagnostic_id=f"{state.request.compilation_id}:parse-error",
                    stage="parse",
                    severity="fatal",
                    category="source.parse_error",
                    message="source text is not a valid document for the selected source kind",
                    object_ref=state.request.source.entry_document,
                    stage_extension={
                        "subject_ref": state.request.source.entry_document,
                        "action": "parsed source document",
                        "source_kind": state.request.source.kind,
                        "entry_document": state.request.source.entry_document,
                    },
                )
            )
            for item in state.summary.stage_outcomes:
                if item.stage == "parse":
                    item.status = "failed"
                    item.diagnostic_count = len(
                        [entry for entry in state.diagnostics if entry.stage == "parse"]
                    )
                    break
            raise CompilationAbortedError(
                outcome=CompilationOutcome(
                    graph_model=state.artifacts.get("graph_model"),
                    compilation_summary=state.summary,
                    diagnostic_catalog=DiagnosticCatalog(entries=state.diagnostics),
                ),
                status="failed",
            ) from exc
        except ValueError as exc:
            if str(exc) == "fatal validation failure":
                raise CompilationAbortedError(
                    outcome=CompilationOutcome(
                        graph_model=state.artifacts.get("graph_model"),
                        compilation_summary=state.summary,
                        diagnostic_catalog=DiagnosticCatalog(entries=state.diagnostics),
                    ),
                    status="failed",
                ) from exc
            raise

        return CompilationOutcome(
            graph_model=state.artifacts.get("graph_model"),
            compilation_summary=state.summary,
            diagnostic_catalog=DiagnosticCatalog(entries=state.diagnostics),
        )
