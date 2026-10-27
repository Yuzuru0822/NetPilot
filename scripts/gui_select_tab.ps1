param([string]$TabName = '实时连接', [string]$TitleMatch = 'NetPilot')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process pythonw | Where-Object { $_.MainWindowTitle -like "*$TitleMatch*" } | Select-Object -First 1
if (-not $proc) { Write-Error "NetPilot window not found"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $TabName)
$tab = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if (-not $tab) { Write-Error "tab $TabName not found"; exit 1 }
$tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
Write-Output "selected $TabName"
