# Runs the backend test suite with the backend venv's python.
# Usage: powershell -File scripts/run_tests.ps1            (offline tests only, default)
#        powershell -File scripts/run_tests.ps1 -Live       (everything, incl. real Hindsight/Groq calls)

param(
    [switch]$Live
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "venv python not found at $venvPython -- run: cd backend; python -m venv .venv; ./.venv/Scripts/pip install -r requirements.txt"
    exit 1
}

Push-Location (Join-Path $repoRoot "backend")
try {
    if ($Live) {
        & $venvPython -m pytest -q
    } else {
        & $venvPython -m pytest -q -m "not live"
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
