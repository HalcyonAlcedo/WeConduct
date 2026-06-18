from weconduct.contracts import CompilationOutcome, CompilationRequest, create_initial_summary

from .coordinator import CompilationPipelineCoordinator
from .stage_state import StageState
from .stages import BindStage, EmitStage, LowerStage, NormalizeStage, ParseStage, ValidateStage


class CompilerFacade:
    def __init__(self) -> None:
        self._coordinator = CompilationPipelineCoordinator(
            [
                ParseStage(),
                BindStage(),
                ValidateStage(),
                NormalizeStage(),
                LowerStage(),
                EmitStage(),
            ]
        )

    def compile(self, request: CompilationRequest) -> CompilationOutcome:
        state = StageState(request=request, summary=create_initial_summary(request.compilation_id))
        return self._coordinator.run(state)
