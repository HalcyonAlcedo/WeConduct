from dataclasses import dataclass, field
from typing import Any

from weconduct.contracts import CompilationRequest, CompilationSummary, Diagnostic


@dataclass
class StageState:
    request: CompilationRequest
    summary: CompilationSummary
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
