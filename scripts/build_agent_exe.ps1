# Build the standalone NetPilotAgent.exe (privileged core service).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m PyInstaller `
    --noconfirm --clean --onefile --noconsole --name NetPilotAgent `
    --icon "$root\assets\netpilot.ico" `
    --distpath "$root\build\dist-agent" --workpath "$root\build\work-agent" --specpath "$root\build" `
    "$root\agent_main.py"
Copy-Item "$root\build\dist-agent\NetPilotAgent.exe" "$root\NetPilotAgent.exe" -Force
Write-Output "Built $root\NetPilotAgent.exe"
