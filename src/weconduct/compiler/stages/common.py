from weconduct.contracts import Diagnostic


def mark_stage(state, stage_name: str, status: str) -> None:
    for item in state.summary.stage_outcomes:
        if item.stage == stage_name:
            item.status = status
            item.diagnostic_count = len([entry for entry in state.diagnostics if entry.stage == stage_name])
            break


def append_stage_diagnostic(
    state,
    *,
    diagnostic_id: str,
    stage: str,
    severity: str,
    category: str,
    message: str,
    stage_extension: dict,
    object_ref: str | None = None,
    trace_ref: str | None = None,
) -> None:
    state.diagnostics.append(
        Diagnostic(
            diagnostic_id=diagnostic_id,
            stage=stage,
            severity=severity,
            category=category,
            message=message,
            object_ref=object_ref,
            trace_ref=trace_ref,
            stage_extension=stage_extension,
        )
    )
