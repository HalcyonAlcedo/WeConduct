param(
    [string]$SpecPath = "packaging/pyinstaller/weconduct_preview.spec"
)

$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    python -m PyInstaller $SpecPath --noconfirm --clean
}
finally {
    Pop-Location
}
