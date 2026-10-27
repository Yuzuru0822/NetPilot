$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

# Adapter-based detection is authoritative: the SecoClient window can close
# while the tunnel stays up. Its adapter is TAP-Windows V9 (#1, "本地连接"),
# which gets a 192.168.220.x address when connected.
$ipconf = ipconfig /all | Out-String
$secoUp = $false
$secoIp = ''
$blocks = $ipconf -split "(\r?\n){2,}"
foreach ($block in $blocks) {
    if ($block -match 'TAP-Windows Adapter V9(?! #2)' -and $block -match '192\.168\.220\.(\d+)') {
        $secoUp = $true
        if ($block -match 'IPv4 Address[^:]*:\s*([\d.]+)') { $secoIp = $Matches[1] }
    }
}

$proc = Get-Process SecoClient | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$loginRequired = $false
if ($proc) {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'basewidget.basewidget.pb_login_SSL')
    $login = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    $loginRequired = $null -ne $login
}

if ($secoUp) { $state = 'connected' }
elseif ($loginRequired) { $state = 'login_required' }
elseif ($proc) { $state = 'disconnected' }
else { $state = 'not_running' }
Write-Output (@{ state = $state; ip = $secoIp } | ConvertTo-Json -Compress)
