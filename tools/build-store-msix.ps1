param(
  [string]$Version = "",
  [string]$OutputDir = "dist-store",
  [string]$Python = "python",
  [string]$IdentityFile = "",
  [string]$IdentityName = $env:CODEX_STORE_IDENTITY_NAME,
  [string]$Publisher = $env:CODEX_STORE_PUBLISHER,
  [string]$PublisherDisplayName = $env:CODEX_STORE_PUBLISHER_DISPLAY_NAME,
  [string]$ProductId = $env:CODEX_STORE_PRODUCT_ID,
  [string]$WorldProductId = $env:CODEX_WORLD_STORE_PRODUCT_ID,
  [switch]$StoreSubmission,
  [string]$FeedbackEndpoint = $env:CODEX_FEEDBACK_ENDPOINT,
  [string]$FeedbackTurnstileSiteKey = $env:CODEX_FEEDBACK_TURNSTILE_SITE_KEY
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = $Version.Trim()
if ([string]::IsNullOrWhiteSpace($Version)) {
  $SourceManifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "app-manifest.json") -Raw -Encoding UTF8 |
    ConvertFrom-Json
  $Version = [string]$SourceManifest.version
}
$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
  throw "Version must use semantic versioning, for example 1.0.2."
}
$PackageVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"

if (-not [string]::IsNullOrWhiteSpace($IdentityFile)) {
  $resolvedIdentity = Resolve-Path -LiteralPath $IdentityFile -ErrorAction Stop
  $identity = Get-Content -LiteralPath $resolvedIdentity -Raw -Encoding UTF8 | ConvertFrom-Json
  $IdentityName = [string]$identity.identityName
  $Publisher = [string]$identity.publisher
  $PublisherDisplayName = [string]$identity.publisherDisplayName
  $ProductId = [string]$identity.productId
  if ($identity.PSObject.Properties.Name -contains "worldProductId") {
    $WorldProductId = [string]$identity.worldProductId
  }
}

if ([string]::IsNullOrWhiteSpace($IdentityName)) {
  $IdentityName = "tx74666.CodexControlConsole.Dev"
}
if ([string]::IsNullOrWhiteSpace($Publisher)) {
  $Publisher = "CN=tx74666, OID.2.25.337204255706875845106508963978635774496=1"
}
if ([string]::IsNullOrWhiteSpace($PublisherDisplayName)) {
  $PublisherDisplayName = "tx74666"
}
$IdentityName = $IdentityName.Trim()
$Publisher = $Publisher.Trim()
$PublisherDisplayName = $PublisherDisplayName.Trim()
$ProductId = ([string]$ProductId).Trim()
$WorldProductId = ([string]$WorldProductId).Trim()

if ($StoreSubmission) {
  if ($IdentityName.EndsWith(".Dev", [System.StringComparison]::OrdinalIgnoreCase) -or
      $Publisher.Contains("OID.2.25.337204255706875845106508963978635774496")) {
    throw "Store submission blocked. Copy the exact package identity from Partner Center first."
  }
}

if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
  $OutputDir = Join-Path $ProjectRoot $OutputDir
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$BuildRoot = Join-Path $ProjectRoot "build\store-msix"
$StagingDir = Join-Path $BuildRoot "staging"

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

function Resolve-WindowsSdkTool {
  param([string]$Name)
  $sdkRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
  $candidate = Get-ChildItem -LiteralPath $sdkRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object { try { [version]$_.Name } catch { [version]"0.0" } } -Descending |
    ForEach-Object { Join-Path $_.FullName "x64\$Name" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
  if (-not $candidate) {
    throw "$Name was not found in the Windows SDK."
  }
  return (Resolve-Path -LiteralPath $candidate).Path
}

Remove-SafeBuildDirectory -Path $BuildRoot
New-Item -ItemType Directory -Force -Path $StagingDir, $OutputDir | Out-Null

& (Join-Path $PSScriptRoot "build-windows.ps1") `
  -Version $Version `
  -OutputDir $OutputDir `
  -Python $Python `
  -Stage Application `
  -InstallMode store `
  -StoreProductId $ProductId `
  -StoreWorldProductId $WorldProductId `
  -FeedbackEndpoint $FeedbackEndpoint `
  -FeedbackTurnstileSiteKey $FeedbackTurnstileSiteKey
if ($LASTEXITCODE -ne 0) {
  throw "Store application build failed with exit code $LASTEXITCODE."
}

$ApplicationDir = Join-Path $ProjectRoot "build\console-installer\dist\Codex Console"
Copy-Item -Path (Join-Path $ApplicationDir "*") -Destination $StagingDir -Recurse -Force

# Store policy requires redistribution rights for every bundled sound and image.
# The desktop/GitHub build keeps its existing media; the Store package carries only
# the five wallpapers with documented Unsplash sources and lets users import music.
$BundledMusicDir = Join-Path $StagingDir "_internal\music"
if (Test-Path -LiteralPath $BundledMusicDir) {
  Remove-Item -LiteralPath $BundledMusicDir -Recurse -Force
  New-Item -ItemType Directory -Path $BundledMusicDir | Out-Null
}
$BundledWallpapersDir = Join-Path $StagingDir "_internal\wallpapers"
foreach ($RestrictedWallpaper in @("dragon-maid.jpg", "wandering-witch.jpg")) {
  Remove-Item -LiteralPath (Join-Path $BundledWallpapersDir $RestrictedWallpaper) -Force -ErrorAction SilentlyContinue
}

$AssetsDir = Join-Path $StagingDir "Assets"
$ListingAssetsDir = Join-Path $OutputDir "listing-assets"
& $Python (Join-Path $PSScriptRoot "generate-store-assets.py") `
  --source (Join-Path $ProjectRoot "pc-console-icon.png") `
  --output $AssetsDir `
  --listing-output $ListingAssetsDir
if ($LASTEXITCODE -ne 0) {
  throw "Store visual asset generation failed with exit code $LASTEXITCODE."
}

$ManifestTemplate = Join-Path $ProjectRoot "store\AppxManifest.template.xml"
[xml]$Manifest = Get-Content -LiteralPath $ManifestTemplate -Raw -Encoding UTF8
$Manifest.Package.Identity.Name = $IdentityName
$Manifest.Package.Identity.Publisher = $Publisher
$Manifest.Package.Identity.Version = $PackageVersion
$Manifest.Package.Properties.DisplayName = "Codex Console"
$Manifest.Package.Properties.PublisherDisplayName = $PublisherDisplayName
$Namespace = New-Object System.Xml.XmlNamespaceManager($Manifest.NameTable)
$Namespace.AddNamespace("f", "http://schemas.microsoft.com/appx/manifest/foundation/windows10")
$Namespace.AddNamespace("uap", "http://schemas.microsoft.com/appx/manifest/uap/windows10")
$VisualElements = $Manifest.SelectSingleNode("/f:Package/f:Applications/f:Application/uap:VisualElements", $Namespace)
$VisualElements.SetAttribute("DisplayName", "Codex Console")

$ManifestPath = Join-Path $StagingDir "AppxManifest.xml"
$Settings = New-Object System.Xml.XmlWriterSettings
$Settings.Encoding = New-Object System.Text.UTF8Encoding($false)
$Settings.Indent = $true
$Writer = [System.Xml.XmlWriter]::Create($ManifestPath, $Settings)
try {
  $Manifest.Save($Writer)
} finally {
  $Writer.Dispose()
}

$MakeAppx = Resolve-WindowsSdkTool -Name "makeappx.exe"
$MsixPath = Join-Path $OutputDir "CodexConsole-$Version-x64.msix"
$UploadPath = Join-Path $OutputDir "CodexConsole-$Version-x64.msixupload"
Remove-Item -LiteralPath $MsixPath, $UploadPath -Force -ErrorAction SilentlyContinue
& $MakeAppx pack /o /d $StagingDir /p $MsixPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $MsixPath)) {
  throw "MakeAppx failed to create the Store package."
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$UploadArchive = [System.IO.Compression.ZipFile]::Open($UploadPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
  [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
    $UploadArchive,
    $MsixPath,
    (Split-Path -Leaf $MsixPath),
    [System.IO.Compression.CompressionLevel]::NoCompression
  ) | Out-Null
} finally {
  $UploadArchive.Dispose()
}

& $Python (Join-Path $PSScriptRoot "check-store-msix.py") `
  --staging-dir $StagingDir `
  --msix $MsixPath `
  --msixupload $UploadPath `
  --listing-assets-dir $ListingAssetsDir `
  --identity-name $IdentityName `
  --publisher $Publisher `
  --package-version $PackageVersion `
  "--product-id=$ProductId"
if ($LASTEXITCODE -ne 0) {
  throw "Store package verification failed with exit code $LASTEXITCODE."
}

$MsixHash = Get-FileHash -LiteralPath $MsixPath -Algorithm SHA256
$UploadHash = Get-FileHash -LiteralPath $UploadPath -Algorithm SHA256
Write-Host "Created $MsixPath"
Write-Host "SHA256 $($MsixHash.Hash)"
Write-Host "Created $UploadPath"
Write-Host "SHA256 $($UploadHash.Hash)"
