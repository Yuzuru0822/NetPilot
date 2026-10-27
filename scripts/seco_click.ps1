param([ValidateSet('connect', 'disconnect')][string]$Action)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process SecoClient | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
    Start-Process 'C:\Program Files (x86)\SecoClient\SecoClient.exe'
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
