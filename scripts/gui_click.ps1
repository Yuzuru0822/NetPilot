param([string]$Name, [string]$TitleMatch = 'NetPilot', [string]$ControlType = 'Button')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$proc = Get-Process pythonw | Where-Object { $_.MainWindowTitle -like "*$TitleMatch*" } | Select-Object -First 1
if (-not $proc) { Write-Error "window $TitleMatch not found"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$target = $null
foreach ($el in $all) {
    if ($el.Current.Name -like "*$Name*" -and $el.Current.ControlType.ProgrammaticName -like "*$ControlType*" -and -not $el.Current.IsOffscreen) {
        $target = $el
        break
    }
}
if (-not $target) { Write-Error "control $Name ($ControlType) not found"; exit 1 }
try {
    $target.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
} catch {
    $target.SetFocus()
}
Write-Output ("clicked: " + $target.Current.Name)
