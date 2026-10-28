param([Parameter(Mandatory = $true)][string]$ZipPath)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Write-Output "Applying update from $ZipPath to $root"

# 1. Stop GUI and gracefully stop the agent (which also stops the core and
# removes the /1 routes). We are elevated, so hard kills work as fallback.
Get-Process NetPilot -ErrorAction SilentlyContinue | Stop-Process -Force
try {
    $token = (Get-Content (Join-Path $root 'data\agent.token') -Raw).Trim()
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:19090/shutdown' `
        -Headers @{ 'X-NetPilot-Token' = $token } -TimeoutSec 10 | Out-Null
} catch { }
Start-Sleep -Seconds 3
Get-Process NetPilotAgent, sing-box -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
$gw = '172.19.0.2'
route delete 0.0.0.0 mask 128.0.0.0 $gw 2>$null | Out-Null
route delete 128.0.0.0 mask 128.0.0.0 $gw 2>$null | Out-Null

# 2. Extract the new package, preserving user data (rules, token) and logs.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
$count = 0
foreach ($entry in $zip.Entries) {
    $rel = $entry.FullName
    if ($rel.StartsWith('NetPilot/')) { $rel = $rel.Substring('NetPilot/'.Length) }
    if (-not $rel -or $rel.EndsWith('/')) { continue }
    $rel = $rel -replace '/', '\'
    if ($rel -match '^(data|logs)\\') { continue }
    $dest = Join-Path $root $rel
    $dir = Split-Path -Parent $dest
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
    $count++
}
$zip.Dispose()
Write-Output "extracted $count files"

# 3. Restart agent and core, then the GUI.
$agent = Join-Path $root 'NetPilotAgent.exe'
if (Test-Path $agent) { Start-Process $agent -WorkingDirectory $root }
$token = (Get-Content (Join-Path $root 'data\agent.token') -Raw).Trim()
$ready = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:19090/status' `
            -Headers @{ 'X-NetPilot-Token' = $token } -TimeoutSec 3
        $ready = $true
        break
    } catch { }
}
if (-not $ready) {
    & (Join-Path $root 'scripts\start_agent.ps1')
    Start-Sleep -Seconds 6
}
try {
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:19090/start' `
        -Headers @{ 'X-NetPilot-Token' = $token } -TimeoutSec 30 | Out-Null
} catch { }
Start-Process (Join-Path $root 'NetPilot.exe') -WorkingDirectory $root
Write-Output 'update applied, NetPilot restarted'
