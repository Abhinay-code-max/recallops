# Runs the backend test suite with the backend venv's python.
# Usage: powershell -File scripts/run_tests.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "venv python not found at $venvPython -- run: cd backend; python -m venv .venv; ./.venv/Scripts/pip install -r requirements.txt"
    exit 1
}

Push-Location (Join-Path $repoRoot "backend")
try {
    & $venvPython -m pytest -q
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
