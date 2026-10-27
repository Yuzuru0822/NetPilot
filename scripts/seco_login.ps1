param([string]$Username, [string]$Password)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
function Get-Root {
    $proc = Get-Process SecoClient -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $proc) { return $null }
    return [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
}
$root = Get-Root
if (-not $root) {
    Start-Process 'C:\Program Files (x86)\SecoClient\SecoClient.exe'
    Start-Sleep -Seconds 5
    $root = Get-Root
}
if (-not $root) { Write-Output '{"ok":false,"message":"SecoClient window not found"}'; exit 0 }
function Find-ById($id) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}
$login = Find-ById 'basewidget.basewidget.pb_login_SSL'
if ($login) {
    $u = Find-ById 'basewidget.basewidget.groupBox.stackedWidget.stackedWidgetPage1.le_username'
    $p = Find-ById 'basewidget.basewidget.groupBox.stackedWidget.stackedWidgetPage1.le_password'
    $save = Find-ById 'basewidget.basewidget.groupBox.stackedWidget.stackedWidgetPage1.cb_savePass'
    $auto = Find-ById 'basewidget.basewidget.groupBox.stackedWidget.stackedWidgetPage1.cb_autoLogin'
    if ($u) { $u.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Username) }
    if ($p) { $p.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Password) }
    foreach ($cb in @($save, $auto)) {
        if ($cb) {
            $toggle = $cb.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            if ($toggle.Current.ToggleState -ne 'On') { $toggle.Toggle() }
        }
    }
    $login.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Write-Output '{"ok":true,"message":"login submitted"}'
} else {
    $connect = Find-ById 'basewidget.groupBox.pb_connect'
    if ($connect) {
        $connect.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Write-Output '{"ok":true,"message":"connect clicked"}'
    } else {
        Write-Output '{"ok":true,"message":"already connected or busy"}'
    }
}
