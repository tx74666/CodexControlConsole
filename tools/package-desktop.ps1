param(
  [string]$Version = "0.3.1",
  [string]$OutputDir = "dist",
  [ValidateSet("all", "developer", "lite")]
  [string]$Edition = "all"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
  $OutputDir = Join-Path $ProjectRoot $OutputDir
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$Items = @(
  "README.md",
  "index.html",
  "music.html",
  "workspace.html",
  "styles.css",
  "app.js",
  "world_console.py",
  "blender_github_share.py",
  "github-coop.json",
  "console_update.py",
  "app-manifest.json",
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
  "Start-ControlConsole-Lite.cmd",
  "Start-ControlConsole-Lite.vbs",
  "Start-ControlConsole-LAN-Lite.cmd",
  "Start-ControlConsole-LAN-Lite.vbs",
  "Start-WorldConsole.cmd",
  "Start-WorldConsole.vbs",
  "tools/NativeFileDrag.exe",
  "tools/NativeFileDrag.cs",
  "tools/blender_live_selection_bridge.py",
  "tools/apply_update.py",
  "wallpapers/README.txt",
  "wallpapers/SOURCES.md"
)

function Copy-StageItem {
  param(
    [string]$Item,
    [string]$StageDir
  )

  $Source = Join-Path $ProjectRoot $Item
  if (-not (Test-Path -LiteralPath $Source)) {
    Write-Warning "Skipping missing file: $Item"
    return
  }
  $Target = Join-Path $StageDir $Item
  $TargetParent = Split-Path -Parent $Target
  New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
  Copy-Item -LiteralPath $Source -Destination $Target -Force
}

function New-DesktopPackage {
  param(
    [ValidateSet("developer", "lite")]
    [string]$PackageEdition
  )

  $IsLite = $PackageEdition -eq "lite"
  $PackageName = if ($IsLite) { "CodexControlConsole-$Version-lite-windows" } else { "CodexControlConsole-$Version-windows" }
  $StageDir = Join-Path $OutputDir $PackageName
  $ZipPath = Join-Path $OutputDir ($(if ($IsLite) { "CodexControlConsole-lite-windows.zip" } else { "CodexControlConsole-windows.zip" }))
  $AliasZipPath = if ($IsLite) { $null } else { Join-Path $OutputDir "CodexControlConsole-developer-windows.zip" }

  if (-not $StageDir.StartsWith($OutputDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to stage outside the output directory."
  }
  if (Test-Path -LiteralPath $StageDir) {
    Remove-Item -LiteralPath $StageDir -Recurse -Force
  }
  if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
  }
  if ($AliasZipPath -and (Test-Path -LiteralPath $AliasZipPath)) {
    Remove-Item -LiteralPath $AliasZipPath -Force
  }

  New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

  foreach ($Item in $Items) {
    Copy-StageItem -Item $Item -StageDir $StageDir
  }

  if ($IsLite) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "Start-ControlConsole-Lite.cmd") -Destination (Join-Path $StageDir "Start-ControlConsole.cmd") -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "Start-ControlConsole-Lite.vbs") -Destination (Join-Path $StageDir "Start-ControlConsole.vbs") -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "Start-ControlConsole-LAN-Lite.cmd") -Destination (Join-Path $StageDir "Start-ControlConsole-LAN.cmd") -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "Start-ControlConsole-LAN-Lite.vbs") -Destination (Join-Path $StageDir "Start-ControlConsole-LAN.vbs") -Force
  }

  $ManifestPath = Join-Path $StageDir "app-manifest.json"
  $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
  $Manifest.version = $Version.TrimStart("v")
  $Manifest.installMode = "portable"
  $Manifest.edition = $PackageEdition
  $ManifestJson = $Manifest | ConvertTo-Json -Depth 8
  $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($ManifestPath, $ManifestJson + [Environment]::NewLine, $Utf8NoBom)

  New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "cache") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "music") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "wallpapers") | Out-Null

  @"
This folder is intentionally empty in the public release.

Use Add in the Music panel for per-user files under LOCALAPPDATA.
To share one library between users, put music here or set CODEX_CONTROL_MUSIC_DIR.
"@ | Set-Content -LiteralPath (Join-Path $StageDir "music\README.txt") -Encoding UTF8

  $EditionLabel = if ($IsLite) { "Lite edition: Wallpaper and Music only." } else { "Developer edition: all console modules enabled." }
  $EditionLabel | Set-Content -LiteralPath (Join-Path $StageDir "EDITION.txt") -Encoding UTF8

  Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
  Write-Host "Desktop package: $ZipPath"

  if ($AliasZipPath) {
    Copy-Item -LiteralPath $ZipPath -Destination $AliasZipPath -Force
    Write-Host "Desktop package alias: $AliasZipPath"
  }
}

$EditionsToBuild = if ($Edition -eq "all") { @("developer", "lite") } else { @($Edition) }
foreach ($PackageEdition in $EditionsToBuild) {
  New-DesktopPackage -PackageEdition $PackageEdition
}
