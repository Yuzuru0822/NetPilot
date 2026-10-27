param([string]$ProcessName = 'pythonw', [string]$MainTitleMatch = 'NetPilot', [string]$WindowName = '', [int]$MaxDepth = 6)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process -Name $ProcessName | Where-Object { $_.MainWindowTitle -like "*$MainTitleMatch*" } | Select-Object -First 1
if (-not $proc) { Write-Error "process with main window $MainTitleMatch not found"; exit 1 }
$wcond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
$wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $wcond)
function Dump($el, $depth) {
    if ($depth -gt $MaxDepth) { return }
    $c = $el.Current
    $indent = ' ' * ($depth * 2)
    Write-Output ("{0}{1} Name='{2}' AutoId='{3}' Class='{4}' Offscreen={5}" -f $indent, $c.ControlType.ProgrammaticName, $c.Name, $c.AutomationId, $c.ClassName, $c.IsOffscreen)
    $children = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($ch in $children) { Dump $ch ($depth + 1) }
}
foreach ($w in $wins) {
    if ($WindowName -eq '' -or $w.Current.Name -like "*$WindowName*") {
        Write-Output ("=== top window: " + $w.Current.Name + " ===")
        Dump $w 0
    }
}
