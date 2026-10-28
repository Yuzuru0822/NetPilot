# Idempotent disconnect: if connected, click the button (shows 断开连接) and poll to a terminal state.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$proc = Get-Process -Name FastOrange -ErrorAction Stop
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)

function Get-State([System.Windows.Automation.AutomationElement]$rootEl) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ConnectBtnText")
    $tb = $rootEl.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($tb) { return $tb.Current.Name } else { return $null }
}

$state = Get-State $root
Write-Output ("state before: '" + $state + "'")

if ($state -eq "连接") { Write-Output "RESULT: already disconnected"; exit 0 }

if ($state -eq "断开连接") {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ConnectBtnText")
    $tb = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    $el = $tb
    $invoked = $false
    while ($el -ne $null) {
        try {
            $p = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
            if ($p -ne $null) { $p.Invoke(); $invoked = $true; break }
        } catch { }  # TextBlock has no InvokePattern; walk up to the parent Button
        $el = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($el)
    }
    if (-not $invoked) { throw "no invokable ancestor of ConnectBtnText found" }
    Write-Output "clicked disconnect"
}

$last = ""
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    $state = Get-State $root
    if ($state -ne $last) { Write-Output ("t+" + (($i+1)*3) + "s: '" + $state + "'"); $last = $state }
    if ($state -eq "连接")     { Write-Output "RESULT: disconnected"; exit 0 }
    if ($state -eq "断开连接") { Write-Output "RESULT: still connected (button unchanged)"; exit 2 }
}
Write-Output ("RESULT: timeout, last state '" + $state + "'")
exit 3
