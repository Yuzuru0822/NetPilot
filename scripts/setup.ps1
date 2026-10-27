# One-shot setup after cloning: venv + dependencies + sing-box core.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Write-Output 'Creating virtual environment (Python 3.12 required)...'
& py -3.12 -m venv (Join-Path $root '.venv')
& (Join-Path $root '.venv\Scripts\python.exe') -m pip install --no-cache-dir -r (Join-Path $root 'requirements.txt')
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'download_core.ps1')
Write-Output 'Setup complete. Double-click 启动NetPilot.bat, then start the core service in the GUI.'
