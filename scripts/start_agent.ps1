$root = 'D:\NetPilot'
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = Join-Path $root '.venv\Scripts\python.exe' }
Start-Process -FilePath $pyw -ArgumentList '-m','app.agent' -WorkingDirectory $root -Verb RunAs
Write-Output "elevation requested"
