# NetPilot Autostart installer (run once as administrator).
# Registers the privileged agent to start at logon; no UAC prompt afterwards.
$taskName = 'NetPilot Agent'
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '-m app.agent' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force
Write-Output "Scheduled task '$taskName' registered. Agent will start at logon."
