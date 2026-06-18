from dataclasses import dataclass

from weconduct.contracts import CompilationOutcome


@dataclass
class CompilationAbortedError(Exception):
    outcome: CompilationOutcome
    status: str = "failed"

    def __str__(self) -> str:
        return f"compilation aborted with status={self.status}"
