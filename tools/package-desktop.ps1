param(
  [string]$Version = "0.1.0",
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
  $OutputDir = Join-Path $ProjectRoot $OutputDir
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$PackageName = "CodexControlConsole-$Version-windows"
$StageDir = Join-Path $OutputDir $PackageName
$ZipPath = Join-Path $OutputDir "CodexControlConsole-windows.zip"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if (-not $StageDir.StartsWith($OutputDir, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to stage outside the output directory."
}
if (Test-Path -LiteralPath $StageDir) {
  Remove-Item -LiteralPath $StageDir -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
  Remove-Item -LiteralPath $ZipPath -Force
}

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

$Items = @(
  "README.md",
  "index.html",
  "music.html",
  "workspace.html",
  "styles.css",
  "app.js",
  "world_console.py",
  "site.webmanifest",
  "favicon.ico",
  "codex-resource-icon.ico",
  "codex-resource-icon-16.png",
  "codex-resource-icon-32.png",
  "codex-resource-icon-48.png",
  "codex-resource-icon-64.png",
  "codex-resource-icon-128.png",
  "codex-resource-icon-256.png",
  "codex-resource-icon-preview.png",
  "pc-console.ico",
  "pc-console-icon.ico",
  "pc-console-icon.png",
  "pc-console-preview.png",
  "Start-ControlConsole.cmd",
  "Start-ControlConsole.vbs",
  "Start-ControlConsole-LAN.cmd",
  "Start-ControlConsole-LAN.vbs",
  "Start-WorldConsole.cmd",
  "Start-WorldConsole.vbs",
  "tools/NativeFileDrag.exe",
  "tools/NativeFileDrag.cs",
  "tools/blender_live_selection_bridge.py",
  "wallpapers/README.txt",
  "wallpapers/SOURCES.md"
)

foreach ($Item in $Items) {
  $Source = Join-Path $ProjectRoot $Item
  if (-not (Test-Path -LiteralPath $Source)) {
    Write-Warning "Skipping missing file: $Item"
    continue
  }
  $Target = Join-Path $StageDir $Item
  $TargetParent = Split-Path -Parent $Target
  New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
  Copy-Item -LiteralPath $Source -Destination $Target -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "cache") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "music") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "wallpapers") | Out-Null

@"
This folder is intentionally empty in the public release.

Put your local music files here or set CODEX_CONTROL_MUSIC_DIR to another folder.
"@ | Set-Content -LiteralPath (Join-Path $StageDir "music\README.txt") -Encoding UTF8

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
Write-Host "Desktop package: $ZipPath"
