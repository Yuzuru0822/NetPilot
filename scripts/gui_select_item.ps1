param([string]$ItemName)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process pythonw,NetPilot -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*NetPilot*' } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$item = $null
foreach ($el in $all) {
    if ($el.Current.Name -like "*$ItemName*") { $item = $el; break }
}
if (-not $item) { Write-Error "item $ItemName not found"; exit 1 }
Write-Output ("found: " + $item.Current.ControlType.ProgrammaticName + " Name='" + $item.Current.Name + "'")
$item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
Write-Output "selected $ItemName"
