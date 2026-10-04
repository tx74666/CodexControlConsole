param(
  [string]$Version = "",
  [string]$OutputDir = "dist",
  [string]$Python = "python",
  [ValidateSet("All", "Application", "Installer")]
  [string]$Stage = "All",
  [ValidateSet("installed", "store")]
  [string]$InstallMode = "installed",
  [string]$StoreProductId = "",
  [string]$StoreWorldProductId = "",
  [string]$FeedbackEndpoint = $env:CODEX_FEEDBACK_ENDPOINT,
  [string]$FeedbackTurnstileSiteKey = $env:CODEX_FEEDBACK_TURNSTILE_SITE_KEY
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-BuildVersion {
  param(
    [Parameter(Mandatory = $true)]
    [object]$Manifest,
    [AllowEmptyString()]
    [string]$RequestedVersion = ""
  )

  $ManifestVersion = ([string]$Manifest.version).Trim()
  if ($ManifestVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "app-manifest.json version must use semantic versioning, for example 1.0.6."
  }

  $RequestedVersion = ([string]$RequestedVersion).Trim()
  if ([string]::IsNullOrWhiteSpace($RequestedVersion)) {
    return $ManifestVersion
  }
  if ($RequestedVersion.StartsWith("v", [System.StringComparison]::OrdinalIgnoreCase)) {
    $RequestedVersion = $RequestedVersion.Substring(1)
  }
  if ($RequestedVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must use semantic versioning, for example 1.0.6."
  }
  if ($RequestedVersion -ne $ManifestVersion) {
    throw "Requested version $RequestedVersion does not match app-manifest.json version $ManifestVersion."
  }
  return $ManifestVersion
}

function Assert-UiBuildVersion {
  param(
    [Parameter(Mandatory = $true)]
    [AllowEmptyString()]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion,
    [hashtable]$EntrySources = @{}
  )

  $UiVersions = [regex]::Matches($Source, '(?m)^\s*const consoleUiVersion = "(\d+\.\d+\.\d+)";\s*$')
  if ($UiVersions.Count -ne 1) {
    throw "app.js must declare exactly one semantic consoleUiVersion."
  }
  $UiVersion = $UiVersions[0].Groups[1].Value
  if ($UiVersion -ne $ExpectedVersion) {
    throw "app.js consoleUiVersion $UiVersion does not match app-manifest.json version $ExpectedVersion. Update the UI version before building the Application stage."
  }
  $CacheVersions = @()
  foreach ($EntryName in $EntrySources.Keys) {
    $EntrySource = [string]$EntrySources[$EntryName]
    $AppCacheVersion = [regex]::Match($EntrySource, 'app\.js\?v=([^"'']+)').Groups[1].Value
    $CssCacheVersion = [regex]::Match($EntrySource, 'styles\.css\?v=([^"'']+)').Groups[1].Value
    if (-not $AppCacheVersion -or -not $CssCacheVersion -or $AppCacheVersion -ne $CssCacheVersion) {
      throw "$EntryName must use the same nonempty CSS and app.js cache version."
    }
    if ($AppCacheVersion -notmatch ('(?:^|[^\d.])' + [regex]::Escape($ExpectedVersion) + '(?:$|[^\d.])')) {
      throw "$EntryName app.js cache version $AppCacheVersion does not include app-manifest.json version $ExpectedVersion."
    }
    $CacheVersions += $AppCacheVersion
  }
  if (@($CacheVersions | Select-Object -Unique).Count -gt 1) {
    throw "HTML entry points must share one CSS and app.js cache version."
  }
}

function Assert-BundledBuildVersion {
  param(
    [Parameter(Mandatory = $true)]
    [object]$Manifest,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion
  )

  $BundledVersion = ([string]$Manifest.version).Trim()
  if ($BundledVersion -ne $ExpectedVersion) {
    throw "Application bundle version $BundledVersion does not match app-manifest.json version $ExpectedVersion. Rebuild the Application stage."
  }
}

$SourceManifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "app-manifest.json") -Raw | ConvertFrom-Json
$Version = Resolve-BuildVersion -Manifest $SourceManifest -RequestedVersion $Version
if ([string]::IsNullOrWhiteSpace($FeedbackEndpoint)) {
  $FeedbackEndpoint = [string]$SourceManifest.feedbackEndpoint
}
if ([string]::IsNullOrWhiteSpace($FeedbackTurnstileSiteKey)) {
  $FeedbackTurnstileSiteKey = [string]$SourceManifest.feedbackTurnstileSiteKey
}
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
  $OutputDir = Join-Path $ProjectRoot $OutputDir
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$BuildRoot = Join-Path $ProjectRoot "build\console-installer"
$BuildApplication = $Stage -in @("All", "Application")
$BuildInstaller = $Stage -in @("All", "Installer")
if ($BuildApplication) {
  $UiSource = Get-Content -LiteralPath (Join-Path $ProjectRoot "app.js") -Raw -Encoding UTF8
  $UiEntrySources = @{}
  foreach ($EntryName in @("index.html", "music.html", "workspace.html")) {
    $UiEntrySources[$EntryName] = Get-Content -LiteralPath (Join-Path $ProjectRoot $EntryName) -Raw -Encoding UTF8
  }
  Assert-UiBuildVersion -Source $UiSource -ExpectedVersion $Version -EntrySources $UiEntrySources
}
if ($BuildInstaller -and $InstallMode -eq "store") {
  throw "Store application bundles must be packaged with tools/build-store-msix.ps1, not Inno Setup."
}

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

function Resolve-CSharpCompiler {
  $candidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw "The Windows C# compiler was not found. NativeFileDrag.exe must be built from source."
}

if ($BuildApplication) {
  Remove-SafeBuildDirectory -Path $BuildRoot
} elseif (-not (Test-Path -LiteralPath $BuildRoot)) {
  throw "Application build output is missing. Run the Application stage before Installer."
}
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

if ($BuildApplication) {
  $ManifestPath = Join-Path $BuildRoot "app-manifest.json"
  $Manifest = [ordered]@{
    name = "Codex Control Console"
    version = $Version
    repository = "tx74666/CodexControlConsole"
    channel = "stable"
    installMode = $InstallMode
    edition = "public"
    feedbackEndpoint = ([string]$FeedbackEndpoint).Trim()
    feedbackTurnstileSiteKey = ([string]$FeedbackTurnstileSiteKey).Trim()
  }
  if ($InstallMode -eq "store" -and -not [string]::IsNullOrWhiteSpace($StoreProductId)) {
    $Manifest.storeProductId = $StoreProductId.Trim()
  }
  if ($InstallMode -eq "store" -and -not [string]::IsNullOrWhiteSpace($StoreWorldProductId)) {
    $Manifest.worldStoreProductId = $StoreWorldProductId.Trim()
  }
  $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 5) + [Environment]::NewLine, $Utf8NoBom)

  $GeneratedToolsDir = Join-Path $BuildRoot "generated-tools"
  New-Item -ItemType Directory -Force -Path $GeneratedToolsDir | Out-Null
  $NativeFileDragSource = Join-Path $ProjectRoot "tools\NativeFileDrag.cs"
  $NativeFileDragExe = Join-Path $GeneratedToolsDir "NativeFileDrag.exe"
  $CSharpCompiler = Resolve-CSharpCompiler
  & $CSharpCompiler `
    /nologo `
    /target:winexe `
    /platform:x64 `
    /optimize+ `
    /reference:System.dll `
    /reference:System.Drawing.dll `
    /reference:System.Windows.Forms.dll `
    "/out:$NativeFileDragExe" `
    $NativeFileDragSource
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $NativeFileDragExe)) {
    throw "NativeFileDrag.exe could not be compiled from source."
  }

  $PublicWallpaperFiles = @(
  "README.txt",
  "SOURCES.md",
  "blue-lake-boats.jpg",
  "calm-mountain-lake.jpg",
  "quiet-forest-aerial.jpg",
  "snow-water-mountains.jpg",
  "soft-mountain-sun.jpg"
)
  if ($InstallMode -ne "store") {
    $PublicWallpaperFiles += @("dragon-maid.jpg", "wandering-witch.jpg")
  }

  $DataItems = @(
  @{ Source = $ManifestPath; Destination = "." },
  @{ Source = "index.html"; Destination = "." },
  @{ Source = "music.html"; Destination = "." },
  @{ Source = "workspace.html"; Destination = "." },
  @{ Source = "reader.html"; Destination = "." },
  @{ Source = "document-reader.js"; Destination = "." },
  @{ Source = "document-reader.css"; Destination = "." },
  @{ Source = "mobile.html"; Destination = "." },
  @{ Source = "mobile.js"; Destination = "." },
  @{ Source = "mobile-dialogue.js"; Destination = "." },
  @{ Source = "mobile-dialogue.css"; Destination = "." },
  @{ Source = "mobile-handoff.js"; Destination = "." },
  @{ Source = "mobile.css"; Destination = "." },
  @{ Source = "transfer-panel.js"; Destination = "." },
  @{ Source = "transfer-panel.css"; Destination = "." },
  @{ Source = "workflow-panel.js"; Destination = "." },
  @{ Source = "workflow-panel.css"; Destination = "." },
  @{ Source = "incubator-panel.js"; Destination = "." },
  @{ Source = "incubator-panel.css"; Destination = "." },
  @{ Source = "conversations-panel.js"; Destination = "." },
  @{ Source = "conversations-panel.css"; Destination = "." },
  @{ Source = "mobile.webmanifest"; Destination = "." },
  @{ Source = "phone\phone-icon-180.png"; Destination = "phone" },
  @{ Source = "phone\phone-icon-192.png"; Destination = "phone" },
  @{ Source = "phone\phone-icon-512.png"; Destination = "phone" },
  @{ Source = "phone-pairing.js"; Destination = "." },
  @{ Source = "phone-offline-export.js"; Destination = "." },
  @{ Source = "styles.css"; Destination = "." },
  @{ Source = "app.js"; Destination = "." },
  @{ Source = "README.md"; Destination = "." },
  @{ Source = "release-defaults.json"; Destination = "." },
  @{ Source = "music-loudness.json"; Destination = "." },
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
  @{ Source = $NativeFileDragExe; Destination = "tools" },
  @{ Source = "tools\NativeFileDrag.cs"; Destination = "tools" },
  @{ Source = "tools\blender_live_selection_bridge.py"; Destination = "tools" },
  @{ Source = "tools\DesktopLayout.ps1"; Destination = "tools" },
  @{ Source = "tools\Collect-DeviceSnapshot.ps1"; Destination = "tools" }
)

  if ($InstallMode -ne "store") {
    $DataItems += @{ Source = "public-music"; Destination = "music" }
  }

  foreach ($wallpaper in $PublicWallpaperFiles) {
    $DataItems += @{ Source = "wallpapers\$wallpaper"; Destination = "wallpapers" }
  }

  $PyInstallerArgs = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--noupx",
  "--onedir",
  "--windowed",
  "--name", "Codex Console",
  "--icon", (Join-Path $ProjectRoot "pc-console-icon.ico"),
  "--distpath", (Join-Path $BuildRoot "dist"),
  "--workpath", (Join-Path $BuildRoot "work"),
  "--specpath", (Join-Path $BuildRoot "spec"),
  "--paths", $ProjectRoot,
  "--collect-submodules", "zeroconf",
  "--collect-submodules", "ifaddr",
  "--exclude-module", "tkinter"
)

  if ($InstallMode -eq "store") {
    $PyInstallerArgs += @("--exclude-module", "yt_dlp")
  }

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
}

$AppDir = Join-Path $BuildRoot "dist\Codex Console"
$AppExe = Join-Path $AppDir "Codex Console.exe"
if (-not (Test-Path -LiteralPath $AppExe)) {
  throw "Codex Console executable was not created."
}
$BundledManifestPath = Join-Path $AppDir "_internal\app-manifest.json"
if (-not (Test-Path -LiteralPath $BundledManifestPath -PathType Leaf)) {
  throw "Application bundle manifest is missing: $BundledManifestPath"
}
$BundledManifest = Get-Content -LiteralPath $BundledManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-BundledBuildVersion -Manifest $BundledManifest -ExpectedVersion $Version

if (-not $BuildInstaller) {
  Write-Host "Created application bundle $AppDir"
  exit 0
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
