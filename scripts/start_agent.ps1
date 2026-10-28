$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'NetPilotAgent.exe'
if (Test-Path $exe) {
    Start-Process -FilePath $exe -WorkingDirectory $root -Verb RunAs
} else {
    $pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path $pyw)) { $pyw = Join-Path $root '.venv\Scripts\python.exe' }
    Start-Process -FilePath $pyw -ArgumentList '-m','app.agent' -WorkingDirectory $root -Verb RunAs
}
Write-Output "elevation requested"
