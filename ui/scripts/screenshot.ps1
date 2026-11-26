# 启动 GPUI 应用 → 移到副屏 → 置顶 → 截该屏(可裁剪窗口)→ 退出。
# 默认在非主屏上操作,避免打断主屏工作。
# 用法: powershell -File ui\scripts\screenshot.ps1 [-Out _shot.png] [-Wait 8] [-Monitor 1] [-Crop]
param(
    [string]$Exe = (Join-Path $PSScriptRoot '..\target\debug\artist-toolkit-ui.exe'),
    [string]$Out = (Join-Path $PSScriptRoot '..\_shot.png'),
    [int]$Wait = 8,
    [int]$Monitor = -1,
    [switch]$Crop,
    [int]$Inset = 10,
    [switch]$ReportChildren,
    [switch]$Attach
)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct WinRect { public int Left, Top, Right, Bottom; }`npublic struct WinPoint { public int X, Y; }
public class WindowTools {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out WinRect rect);`n    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out WinRect rect);`n    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref WinPoint point);
}
"@

# 选屏:显式指定 → 否则用第一块非主屏 → 兜底主屏
$screens = [System.Windows.Forms.Screen]::AllScreens
if ($Monitor -ge 0 -and $Monitor -lt $screens.Count) {
    $screen = $screens[$Monitor]
} else {
    $screen = $screens | Where-Object { -not $_.Primary } | Select-Object -First 1
    if (-not $screen) { $screen = [System.Windows.Forms.Screen]::PrimaryScreen }
}

if ($Attach) {
    $process = Get-Process | Where-Object { $_.MainWindowTitle -eq 'Artist Toolkit' } | Select-Object -First 1
    if (-not $process) { Write-Error '没有正在运行的 Artist Toolkit 窗口'; exit 1 }
} else {
    # 让应用直接开在目标屏,避免在主屏闪一下
    $env:ATK_UI_WINDOW_POS = "{0},{1},{2},{3}" -f ($screen.WorkingArea.X + 40), ($screen.WorkingArea.Y + 20), 1264, 861
    # debug 构建是 console 子系统,隐藏它的控制台窗口
    $process = Start-Process -FilePath $Exe -PassThru -WindowStyle Hidden
}

# 等窗口出现,然后立刻挪到副屏(减少主屏上的闪现)
$handle = [IntPtr]::Zero
$deadline = (Get-Date).AddSeconds([Math]::Max($Wait, 10))
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) { Write-Error '进程已退出(可能崩溃)'; exit 1 }
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) { $handle = $process.MainWindowHandle; break }
}
if ($handle -eq [IntPtr]::Zero) { Write-Error '窗口没起来'; exit 1 }

$area = $screen.WorkingArea
$width = [Math]::Min(1264 + 2 * $Inset, $area.Width - 80)
$height = [Math]::Min(861 + 2 * $Inset, $area.Height - 60)
$x = $area.X + [int](($area.Width - $width) / 2)
$y = $area.Y + [int](($area.Height - $height) / 2)
[WindowTools]::ShowWindow($handle, 9) | Out-Null
[WindowTools]::SetWindowPos($handle, [IntPtr](-1), $x, $y, $width, $height, 0x0040) | Out-Null  # TOPMOST + SHOWWINDOW
[WindowTools]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Seconds $Wait

if ($ReportChildren) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id)" |
        Select-Object Name, ProcessId, ExecutablePath | Format-Table -AutoSize | Out-String | Write-Output
}

$region = $screen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($region.Width, $region.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($region.Location, [System.Drawing.Point]::Empty, $region.Size)

if ($Crop) {
    $rect = New-Object WinRect
    if ([WindowTools]::GetWindowRect($handle, [ref]$rect)) {
        $cropX = [Math]::Max(0, $rect.Left - $region.X + $Inset)
        $cropY = [Math]::Max(0, $rect.Top - $region.Y + $Inset)
        $cropW = [Math]::Min($rect.Right - $rect.Left - 2 * $Inset, $region.Width - $cropX)
        $cropH = [Math]::Min($rect.Bottom - $rect.Top - 2 * $Inset, $region.Height - $cropY)
        if ($cropW -gt 0 -and $cropH -gt 0) {
            $cropped = $bitmap.Clone((New-Object System.Drawing.Rectangle($cropX, $cropY, $cropW, $cropH)),
                                     $bitmap.PixelFormat)
            $bitmap.Dispose()
            $bitmap = $cropped
        }
    }
}

$finalWidth = $bitmap.Width
$finalHeight = $bitmap.Height
$bitmap.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

if (-not $Attach -and -not $process.HasExited) { $process.Kill() }
Write-Output "saved $Out (${finalWidth}x${finalHeight}) on $($screen.DeviceName)"
