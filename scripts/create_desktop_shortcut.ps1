$ErrorActionPreference = 'Stop'
$root = 'D:\NetPilot'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'NetPilot.lnk'
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$lnk.Arguments = Join-Path $root 'NetPilot.pyw'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = Join-Path $root '.venv\Scripts\pythonw.exe,0'
$lnk.Description = 'NetPilot 应用分流管家 - 按应用选择网络通道'
$lnk.Save()
Write-Output "shortcut created: $lnkPath"

$existing = Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*NetPilot*' } | Select-Object -First 1
if ($existing) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinFocus {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
    [WinFocus]::ShowWindow($existing.MainWindowHandle, 9) | Out-Null
    [WinFocus]::SetForegroundWindow($existing.MainWindowHandle) | Out-Null
    Write-Output 'NetPilot is already running; brought its window to the front.'
} else {
    Start-Process $lnkPath
    Write-Output 'NetPilot launched via the new desktop shortcut.'
}
