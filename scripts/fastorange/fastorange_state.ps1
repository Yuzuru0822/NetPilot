# Read FastOrange VPN state: connect-button text (authoritative), server name, adapter status.
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$proc = Get-Process -Name FastOrange -ErrorAction Stop
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)

function Get-IdText([System.Windows.Automation.AutomationElement]$rootEl, [string]$id) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    $el = $rootEl.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($el) { return $el.Current.Name } else { return $null }
}

$btn   = Get-IdText $root "ConnectBtnText"
$server = Get-IdText $root "ServerNameText"

$csBtnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::AutomationIdProperty, "ChooseServerBtn")
$csBtn = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $csBtnCond)
$csEnabled = if ($csBtn) { $csBtn.Current.IsEnabled } else { $null }

Write-Output ("ConnectBtnText : '" + $btn + "'")
Write-Output ("ServerNameText : '" + $server + "'")
Write-Output ("ChooseServerBtn enabled: " + $csEnabled)

switch ($btn) {
    "断开连接"   { Write-Output "STATE: connected" }
    "连接"       { Write-Output "STATE: disconnected" }
    "正在连接..." { Write-Output "STATE: connecting" }
    default      { Write-Output ("STATE: unknown ('" + $btn + "')") }
}

# OS-level cross-check: the VPN adapter is 本地连接 2 (TAP-Windows Adapter V9 #2)
Write-Output "--- adapter check (本地连接 2) ---"
netsh interface show interface | Select-String "本地连接 2"
netsh interface ipv4 show addresses "本地连接 2" 2>$null | Select-String "IP Address|Subnet|DHCP"
