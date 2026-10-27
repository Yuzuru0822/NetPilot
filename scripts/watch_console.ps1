Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinEnum {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@
$seen = @{}
for ($i = 0; $i -lt 16; $i++) {
    $titles = New-Object System.Collections.Generic.List[string]
    $cb = [WinEnum+EnumWindowsProc]{ param($h, $l)
        $cls = New-Object System.Text.StringBuilder 256
        [WinEnum]::GetClassName($h, $cls, 256) | Out-Null
        if ($cls.ToString() -eq 'ConsoleWindowClass' -and [WinEnum]::IsWindowVisible($h)) {
            $t = New-Object System.Text.StringBuilder 512
            [WinEnum]::GetWindowText($h, $t, 512) | Out-Null
            $titles.Add($t.ToString()) | Out-Null
        }
        return $true
    }
    [WinEnum]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    foreach ($t in $titles) { $seen[$t] = $true }
    Start-Sleep -Seconds 1
}
Write-Output "console windows seen during 16s watch:"
$seen.Keys | ForEach-Object { Write-Output "  [$_]" }
Write-Output ("total distinct: " + $seen.Count)
