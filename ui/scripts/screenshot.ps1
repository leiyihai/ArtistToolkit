# 启动 GPUI 应用 → 置顶 → 截屏 → 退出。用于验证界面改动的渲染结果。
# 用法: powershell -File ui\scripts\screenshot.ps1 [-Out E:\ArtistToolkit\ui\_shot.png] [-Wait 8]
param(
    [string]$Exe = (Join-Path $PSScriptRoot '..\target\debug\artist-toolkit-ui.exe'),
    [string]$Out = (Join-Path $PSScriptRoot '..\_shot.png'),
    [int]$Wait = 8,
    [switch]$ReportChildren
)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WindowTools {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
"@

$process = Start-Process -FilePath $Exe -PassThru
Start-Sleep -Seconds $Wait
$process.Refresh()
$handle = $process.MainWindowHandle
if ($handle -eq [IntPtr]::Zero) { Write-Error '窗口没起来(进程可能已崩溃)'; exit 1 }

[WindowTools]::ShowWindow($handle, 9) | Out-Null            # SW_RESTORE
[WindowTools]::SetWindowPos($handle, [IntPtr](-1), 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null  # TOPMOST,不改变大小/位置
[WindowTools]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Seconds 2

if ($ReportChildren) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id)" |
        Select-Object Name, ProcessId, ExecutablePath | Format-Table -AutoSize | Out-String | Write-Output
}

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

if (-not $process.HasExited) { $process.Kill() }
Write-Output "saved $Out ($($bounds.Width)x$($bounds.Height))"
