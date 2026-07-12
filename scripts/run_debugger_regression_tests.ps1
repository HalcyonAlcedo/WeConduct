[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot

$testGroups = @(
    @(
        'tests/application/test_debugger_regression_flow.py',
        'tests/application/test_debug_controller.py',
        'tests/application/test_execution_core.py',
        'tests/application/test_debug_session_history.py',
        'tests/application/test_graph_runtime_projection.py'
    ),
    @(
        'tests/application/test_compilation_workbench_service.py',
        'tests/api/test_api_host.py'
    )
)

Push-Location $repoRoot
try {
    foreach ($group in $testGroups) {
        Write-Host ("[debugger-regression] pytest " + ($group -join ' ')) -ForegroundColor Cyan
        & python -m pytest @group -q
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed with exit code $LASTEXITCODE"
        }
    }
}
finally {
    Pop-Location
}
