from .common import append_stage_diagnostic, mark_stage


class ValidateStage:
    stage_name = "validate"

    def run(self, state) -> None:
        bound = state.artifacts["bound_source"]
        bound_edges = state.artifacts.get("bound_edges", [])
        raw_source = state.artifacts.get("raw_source", {})
        source_kind = raw_source.get("source_meta", {}).get("source_kind")
        subject_ref = state.request.source.entry_document
        object_ref = state.request.source.entry_document
        trace_ref = None

        if bound:
            subject_ref = bound[0]["node_id"]
            object_ref = bound[0]["node_id"]
            trace_ref = bound[0].get("trace_ref")
        elif source_kind == "graph_workspace":
            subject_ref = raw_source.get("graph_model_id", state.request.source.entry_document)
            object_ref = subject_ref

        if not bound:
            append_stage_diagnostic(
                state,
                diagnostic_id="validate-empty-source",
                stage="validate",
                severity="fatal",
                category="source.empty",
                message="native source must contain at least one node",
                stage_extension={
                    "subject_ref": subject_ref,
                    "action": "validated bound source",
                    "rule": "source.non_empty",
                    "result": "failed",
                },
                object_ref=object_ref,
            )
            mark_stage(state, self.stage_name, "failed")
            raise ValueError("fatal validation failure")

        state.artifacts["validated_source"] = bound
        state.artifacts["validated_edges"] = bound_edges
        append_stage_diagnostic(
            state,
            diagnostic_id=f"{state.request.compilation_id}:validate",
            stage="validate",
            severity="info",
            category="validate.completed",
            message="validated bound source",
            stage_extension={
                "subject_ref": subject_ref,
                "action": "validated bound source",
                "rule": "source.non_empty",
                "result": "passed",
                "source_ref": {
                    "source_kind": source_kind,
                    "entry_document": state.request.source.entry_document,
                    "node_id": subject_ref,
                    "trace_ref": trace_ref,
                },
            },
            object_ref=object_ref,
            trace_ref=trace_ref,
        )
        mark_stage(state, self.stage_name, "succeeded")
