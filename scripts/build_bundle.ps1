param(
    [string]$SpecPath = "packaging/pyinstaller/weconduct_preview.spec"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$uiRoot = Join-Path $projectRoot "ui"

Push-Location $projectRoot
try {
    Push-Location $uiRoot
    try {
        npm run build
    }
    finally {
        Pop-Location
    }

    python -m PyInstaller $SpecPath --noconfirm --clean
}
finally {
    Pop-Location
}
