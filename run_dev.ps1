# Convenience script for Windows dev runs.
# Usage:
#   .\run_dev.ps1

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
  $py = $venvPython
} else {
  $py = "python"
}

# Load .env if present (python-dotenv also loads it in __main__, but this helps tools).
if (Test-Path "${PSScriptRoot}\.env") {
  Write-Host "Using .env"
}

& $py -m fluencygpt

