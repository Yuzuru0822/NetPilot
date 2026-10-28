# Build the standalone NetPilot.exe (requires: pip install pyinstaller pillow).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m PyInstaller `
    --noconfirm --clean --onefile --windowed --name NetPilot `
    --icon "$root\assets\netpilot.ico" `
    --distpath "$root\build\dist" --workpath "$root\build\work" --specpath "$root\build" `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtWebEngineQuick `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia `
    "$root\NetPilot.pyw"
Copy-Item "$root\build\dist\NetPilot.exe" "$root\NetPilot.exe" -Force
Write-Output "Built $root\NetPilot.exe"
