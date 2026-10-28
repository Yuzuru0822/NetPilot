param([string]$Value)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process pythonw,NetPilot -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*NetPilot*' } | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'QApplication.QInputDialog')
$dialog = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
if (-not $dialog) { Write-Error 'no QInputDialog open'; exit 1 }
$editCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, 'QLineEdit')
$edit = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Value)
$btnCond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, 'OK')
$ok = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
$ok.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Output "entered $Value and clicked OK"
