param([ValidateSet('connect', 'disconnect')][string]$Action)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
function Start-SecoClient {
    $candidates = @(
        'C:\Program Files (x86)\SecoClient\SecoClient.exe',
        'C:\Program Files\SecoClient\SecoClient.exe'
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { Start-Process $path; return $true }
    }
    $appPath = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\SecoClient.exe' -ErrorAction SilentlyContinue
    if ($appPath) {
        $exe = $appPath.'(default)'
        if ($exe -and (Test-Path $exe)) { Start-Process $exe; return $true }
    }
    return $false
}
$proc = Get-Process SecoClient | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
    if (-not (Start-SecoClient)) { Write-Output '{"ok":false,"message":"SecoClient.exe not found (not installed?)"}'; exit 0 }
    Start-Sleep -Seconds 4
    $proc = Get-Process SecoClient | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
}
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
function Find-ById($id) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}
$id = if ($Action -eq 'connect') { 'basewidget.groupBox.pb_connect' } else { 'basewidget.groupBox.pb_disConnect' }
$btn = Find-ById $id
if (-not $btn) { Write-Output '{"ok":false,"message":"button not found (login required?)"}'; exit 0 }
$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Output '{"ok":true,"message":"clicked"}'
