param(
  [string]$Version = "0.6.4",
  [string]$OutputDir = "dist",
  [string]$Python = "python",
  [string]$FeedbackEndpoint = $env:CODEX_FEEDBACK_ENDPOINT,
  [string]$FeedbackTurnstileSiteKey = $env:CODEX_FEEDBACK_TURNSTILE_SITE_KEY
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourceManifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "app-manifest.json") -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($FeedbackEndpoint)) {
  $FeedbackEndpoint = [string]$SourceManifest.feedbackEndpoint
}
if ([string]::IsNullOrWhiteSpace($FeedbackTurnstileSiteKey)) {
  $FeedbackTurnstileSiteKey = [string]$SourceManifest.feedbackTurnstileSiteKey
}
$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must use semantic versioning, for example 0.4.0."
}

if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
  $OutputDir = Join-Path $ProjectRoot $OutputDir
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$BuildRoot = Join-Path $ProjectRoot "build\console-installer"

function Remove-SafeBuildDirectory {
  param([string]$Path)
  $full = [System.IO.Path]::GetFullPath($Path)
  $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
  if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove a directory outside the project: $full"
  }
  if (Test-Path -LiteralPath $full) {
    Remove-Item -LiteralPath $full -Recurse -Force
  }
}

function Resolve-InnoCompiler {
  $candidates = @(
    $env:INNO_SETUP_COMPILER,
    (Join-Path (Split-Path $ProjectRoot -Parent) ".tools\Inno Setup 7\ISCC.exe"),
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  ) | Where-Object { $_ }
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw "Inno Setup compiler was not found. Install Inno Setup 7 or set INNO_SETUP_COMPILER."
}

Remove-SafeBuildDirectory -Path $BuildRoot
New-Item -ItemType Directory -Force -Path $BuildRoot, $OutputDir | Out-Null

@(
  "CodexControlConsole-*.zip",
  "CodexControlConsole-*.apk",
  "CodexControlConsole-*.sha256",
  "CodexControlConsole-Setup-x64.exe",
  "update-manifest.json"
) | ForEach-Object {
  Get-ChildItem -LiteralPath $OutputDir -File -Filter $_ -ErrorAction SilentlyContinue |
    Remove-Item -Force
}

$ManifestPath = Join-Path $BuildRoot "app-manifest.json"
$Manifest = [ordered]@{
  name = "Codex Control Console"
  version = $Version
  repository = "tx74666/CodexControlConsole"
  channel = "stable"
  installMode = "installed"
  edition = "public"
  feedbackEndpoint = ([string]$FeedbackEndpoint).Trim()
  feedbackTurnstileSiteKey = ([string]$FeedbackTurnstileSiteKey).Trim()
}
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 5) + [Environment]::NewLine, $Utf8NoBom)

$PublicWallpaperFiles = @(
  "README.txt",
  "SOURCES.md",
  "blue-lake-boats.jpg",
  "calm-mountain-lake.jpg",
  "dragon-maid.jpg",
  "quiet-forest-aerial.jpg",
  "snow-water-mountains.jpg",
  "soft-mountain-sun.jpg",
  "wandering-witch.jpg"
)

$DataItems = @(
  @{ Source = $ManifestPath; Destination = "." },
  @{ Source = "index.html"; Destination = "." },
  @{ Source = "music.html"; Destination = "." },
  @{ Source = "workspace.html"; Destination = "." },
  @{ Source = "styles.css"; Destination = "." },
  @{ Source = "app.js"; Destination = "." },
  @{ Source = "README.md"; Destination = "." },
  @{ Source = "release-defaults.json"; Destination = "." },
  @{ Source = "github-coop.json"; Destination = "." },
  @{ Source = "site.webmanifest"; Destination = "." },
  @{ Source = "favicon.ico"; Destination = "." },
  @{ Source = "codex-resource-icon.ico"; Destination = "." },
  @{ Source = "codex-resource-icon-16.png"; Destination = "." },
  @{ Source = "codex-resource-icon-32.png"; Destination = "." },
  @{ Source = "codex-resource-icon-48.png"; Destination = "." },
  @{ Source = "codex-resource-icon-64.png"; Destination = "." },
  @{ Source = "codex-resource-icon-128.png"; Destination = "." },
  @{ Source = "codex-resource-icon-256.png"; Destination = "." },
  @{ Source = "codex-resource-icon-preview.png"; Destination = "." },
  @{ Source = "pc-console-icon.ico"; Destination = "." },
  @{ Source = "pc-console-icon.png"; Destination = "." },
  @{ Source = "pc-console-preview.png"; Destination = "." },
  @{ Source = "public-music"; Destination = "music" },
  @{ Source = "tools\NativeFileDrag.exe"; Destination = "tools" },
  @{ Source = "tools\NativeFileDrag.cs"; Destination = "tools" },
  @{ Source = "tools\blender_live_selection_bridge.py"; Destination = "tools" },
  @{ Source = "tools\DesktopLayout.ps1"; Destination = "tools" }
)

foreach ($wallpaper in $PublicWallpaperFiles) {
  $DataItems += @{ Source = "wallpapers\$wallpaper"; Destination = "wallpapers" }
}

$PyInstallerArgs = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--windowed",
  "--name", "Codex Console",
  "--icon", (Join-Path $ProjectRoot "pc-console-icon.ico"),
  "--distpath", (Join-Path $BuildRoot "dist"),
  "--workpath", (Join-Path $BuildRoot "work"),
  "--specpath", (Join-Path $BuildRoot "spec"),
  "--paths", $ProjectRoot,
  "--hidden-import", "tkinter",
  "--collect-all", "yt_dlp"
)

foreach ($item in $DataItems) {
  $source = if ([System.IO.Path]::IsPathRooted($item.Source)) { $item.Source } else { Join-Path $ProjectRoot $item.Source }
  if (Test-Path -LiteralPath $source) {
    $PyInstallerArgs += @("--add-data", "$source;$($item.Destination)")
  }
}
$PyInstallerArgs += (Join-Path $ProjectRoot "world_console.py")

& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$AppDir = Join-Path $BuildRoot "dist\Codex Console"
$AppExe = Join-Path $AppDir "Codex Console.exe"
if (-not (Test-Path -LiteralPath $AppExe)) {
  throw "Codex Console executable was not created."
}

$TargetInstaller = Join-Path $OutputDir "CodexControlConsole-Setup-x64.exe"
if (Test-Path -LiteralPath $TargetInstaller) {
  Remove-Item -LiteralPath $TargetInstaller -Force
}
$Iscc = Resolve-InnoCompiler
$Iss = Join-Path $ProjectRoot "installer\CodexControlConsole.iss"
& $Iscc "/DAppVersion=$Version" "/DSourceDir=$AppDir" "/DOutputDir=$OutputDir" $Iss
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $TargetInstaller)) {
  throw "Inno Setup failed to create $TargetInstaller."
}

Write-Host "Created $TargetInstaller"
