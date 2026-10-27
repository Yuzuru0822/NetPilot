# Emergency network restore: remove NetPilot /1 routes and stop sing-box.
$gateway = '172.19.0.2'
route delete 0.0.0.0 mask 128.0.0.0 $gateway
route delete 128.0.0.0 mask 128.0.0.0 $gateway
Get-Process sing-box -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Output "NetPilot routes removed; sing-box stopped."
