# Convenience script for Windows test runs.
# Usage:
#   .\run_tests.ps1

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  $py = $venvPython
} else {
  $py = "python"
}

$env:PYTHONPATH = "${PSScriptRoot}\src"

& $py -m pytest -q
