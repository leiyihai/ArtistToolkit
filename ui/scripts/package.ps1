# 组装可运行的 GPUI 版分发包。
#
#   powershell -File ui\scripts\package.ps1 [-Out dist-gpui] [-SkipBuild] [-WithModels]
#
# 产物目录结构(与 Electron 版并存,不动现有 dist/):
#   dist-gpui\
#     ArtistToolkit.exe            GPUI 前端(target\release)
#     ArtistToolkit-backend.exe    Python 后端(PyInstaller,内含 Rust 内核 .pyd)
#     models\                      可选:抠图模型(-WithModels 时复制,约 928MB)
#     tools\img2box\models\        天空盒预览的地面/展示模型
param(
    [string]$Out = (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'dist-gpui'),
    [switch]$SkipBuild,
    [switch]$WithModels
)

$ErrorActionPreference = 'Stop'
$ui = Split-Path $PSScriptRoot -Parent
$root = Split-Path $ui -Parent

if (-not $SkipBuild) {
    Write-Host '[1/3] cargo build --release…'
    cargo build --release --manifest-path (Join-Path $ui 'Cargo.toml')
    if ($LASTEXITCODE -ne 0) { throw 'release 构建失败' }
} else {
    Write-Host '[1/3] 跳过构建'
}

$exe = Join-Path $ui 'target\release\artist-toolkit-ui.exe'
$backend = Join-Path $root 'dist\ArtistToolkit-backend.exe'
if (-not (Test-Path $exe)) { throw "找不到 $exe,先运行 cargo build --release" }
if (-not (Test-Path $backend)) {
    throw "找不到 $backend,先运行: python -m PyInstaller --noconfirm --clean ArtistToolkit-backend.spec"
}

Write-Host "[2/3] 组装到 $Out"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item $exe (Join-Path $Out 'ArtistToolkit.exe') -Force
Copy-Item $backend $Out -Force

$viewerModels = Join-Path $root 'tools\img2box\models'
if (Test-Path $viewerModels) {
    $dest = Join-Path $Out 'tools\img2box\models'
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $viewerModels '*') $dest -Recurse -Force
}

if ($WithModels) {
    $model = Join-Path $root 'models\birefnet-general.onnx'
    if (Test-Path $model) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Out 'models') | Out-Null
        Copy-Item $model (Join-Path $Out 'models') -Force
    } else {
        Write-Warning '未找到 models\birefnet-general.onnx,跳过(首次抠图会自行下载)'
    }
}

Write-Host '[3/3] 完成'
Get-ChildItem $Out -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.onnx', '.glb' } |
    Select-Object @{ n = '文件'; e = { $_.FullName.Substring($Out.Length + 1) } },
                  @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
