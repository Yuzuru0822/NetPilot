# Remove the NetPilot Agent autostart scheduled task.
Unregister-ScheduledTask -TaskName 'NetPilot Agent' -Confirm:$false
Write-Output "Scheduled task 'NetPilot Agent' removed."
