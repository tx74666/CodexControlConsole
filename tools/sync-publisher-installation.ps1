<#
.SYNOPSIS
Synchronizes the publisher's local Codex Console installation with a verified GitHub Release.

.DESCRIPTION
Downloads the exact Windows Setup asset for a Codex Console release, verifies the SHA-256
digest reported by GitHub, records the release in per-user publisher state, installs it
silently, and verifies the installed application manifest. The downloaded Setup is always
removed before the script exits.

.PARAMETER Version
Semantic release version, with or without a leading "v".

.PARAMETER Repository
GitHub repository in owner/name form.

.PARAMETER TargetCommit
Optional full commit SHA that the release tag must resolve to.

.EXAMPLE
.\tools\sync-publisher-installation.ps1 -Version 1.0.6 -TargetCommit 0123456789abcdef0123456789abcdef01234567
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Version,
  [string]$Repository = "tx74666/CodexControlConsole",
  [string]$TargetCommit = ""
)

$ErrorActionPreference = "Stop"
$SetupAssetName = "CodexControlConsole-Setup-x64.exe"
$PublisherStateLimit = 32
$MaxSetupBytes = 1500L * 1024L * 1024L
$GitHubHeaders = @{
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "CodexConsolePublisherSync"
}
$DownloadHeaders = @{
  Accept = "application/octet-stream"
  "User-Agent" = "CodexConsolePublisherSync"
}

function Add-GitHubAuthorization {
  $previousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $raw = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($exitCode -ne 0) {
    return
  }
  foreach ($line in @($raw)) {
    if ([string]$line -match '^password=(.+)$') {
      $GitHubHeaders.Authorization = "Bearer $($matches[1])"
      return
    }
  }
}

Add-GitHubAuthorization

function Invoke-GitHubApi {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Uri
  )

  return Invoke-RestMethod -Headers $GitHubHeaders -Uri $Uri -TimeoutSec 30
}

function Resolve-GitHubTagCommit {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryName,
    [Parameter(Mandatory = $true)]
    [string]$Tag
  )

  $encodedTag = [Uri]::EscapeDataString($Tag)
  $reference = Invoke-GitHubApi -Uri "https://api.github.com/repos/$RepositoryName/git/ref/tags/$encodedTag"
  $gitObject = $reference.object
  for ($depth = 0; $depth -lt 8; $depth += 1) {
    $objectType = [string]$gitObject.type
    $objectSha = ([string]$gitObject.sha).Trim().ToLowerInvariant()
    if ($objectSha -notmatch '^[0-9a-f]{40}$') {
      throw "GitHub returned an invalid object for tag $Tag."
    }
    if ($objectType -eq "commit") {
      return $objectSha
    }
    if ($objectType -ne "tag") {
      throw "GitHub tag $Tag resolves to unsupported object type '$objectType'."
    }
    $annotatedTag = Invoke-GitHubApi -Uri "https://api.github.com/repos/$RepositoryName/git/tags/$objectSha"
    $gitObject = $annotatedTag.object
  }

  throw "GitHub tag $Tag contains too many nested annotated tags."
}

function Read-JsonObject {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Description
  )

  try {
    $payload = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
  } catch {
    throw "$Description is not valid JSON: $Path"
  }
  if ($null -eq $payload -or $payload -is [System.Array] -or $payload -is [string]) {
    throw "$Description must contain a JSON object: $Path"
  }
  return $payload
}

function Write-JsonAtomically {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [object]$Payload
  )

  $directory = [IO.Path]::GetDirectoryName($Path)
  [IO.Directory]::CreateDirectory($directory) | Out-Null
  $temporary = Join-Path $directory (".publisher-state.{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
  $backup = Join-Path $directory (".publisher-state.{0}.backup.tmp" -f [Guid]::NewGuid().ToString("N"))
  try {
    $json = ($Payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($temporary, $json, $encoding)
    if ([IO.File]::Exists($Path)) {
      [IO.File]::Replace($temporary, $Path, $backup)
      [IO.File]::Delete($backup)
    } else {
      [IO.File]::Move($temporary, $Path)
    }
  } finally {
    if ([IO.File]::Exists($temporary)) {
      [IO.File]::Delete($temporary)
    }
    if ([IO.File]::Exists($backup)) {
      [IO.File]::Delete($backup)
    }
  }
}

function Read-PublisherState {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$InstallationId
  )

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return [ordered]@{
      schema = 1
      installationId = $InstallationId
      releases = @()
    }
  }

  $state = Read-JsonObject -Path $Path -Description "Publisher state"
  if ([int]$state.schema -ne 1) {
    throw "Publisher state uses an unsupported schema: $($state.schema)"
  }
  if ([string]$state.installationId -ne $InstallationId) {
    throw "Publisher state belongs to a different Codex Console installation."
  }
  return [ordered]@{
    schema = 1
    installationId = $InstallationId
    releases = @($state.releases)
  }
}

function Set-PublisherReleaseRecord {
  param(
    [Parameter(Mandatory = $true)]
    [object]$State,
    [Parameter(Mandatory = $true)]
    [string]$InstallationId,
    [Parameter(Mandatory = $true)]
    [string]$RepositoryName,
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseVersion,
    [Parameter(Mandatory = $true)]
    [string]$Commit,
    [Parameter(Mandatory = $true)]
    [string]$VerifiedAt,
    [Parameter(Mandatory = $true)]
    [bool]$LocalInstallSynchronized
  )

  $record = [ordered]@{
    installationId = $InstallationId
    repository = $RepositoryName
    tag = $Tag
    version = $ReleaseVersion
    commit = $Commit
    verifiedAt = $VerifiedAt
    localInstallSynchronized = $LocalInstallSynchronized
  }
  if ($LocalInstallSynchronized) {
    $record.synchronizedAt = [DateTime]::UtcNow.ToString("o")
  }

  $otherRecords = @($State.releases | Where-Object {
    -not (
      [string]$_.repository -ieq $RepositoryName -and
      [string]$_.tag -ieq $Tag
    )
  })
  $records = @($record) + $otherRecords
  if ($records.Count -gt $PublisherStateLimit) {
    $records = @($records[0..($PublisherStateLimit - 1)])
  }
  return [ordered]@{
    schema = 1
    installationId = $InstallationId
    releases = $records
  }
}

function Get-InstalledDirectory {
  $directory = ""
  try {
    $directory = [string](Get-ItemPropertyValue -LiteralPath "HKCU:\Software\Codex\Codex Console" -Name InstallPath)
  } catch {
    $directory = ""
  }
  if ([string]::IsNullOrWhiteSpace($directory)) {
    $directory = Join-Path $env:LOCALAPPDATA "Programs\Codex Console"
  }
  return [IO.Path]::GetFullPath($directory)
}

function Get-RunningInstalledProcesses {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Executable
  )

  $expected = [IO.Path]::GetFullPath($Executable)
  return @(Get-Process -Name "Codex Console" -ErrorAction SilentlyContinue | Where-Object {
    try {
      $_.Path -and [IO.Path]::GetFullPath($_.Path) -ieq $expected
    } catch {
      $false
    }
  })
}

$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must use semantic versioning, for example 1.0.6."
}
$Repository = $Repository.Trim().Trim("/")
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
  throw "Repository must use GitHub owner/name form."
}
$TargetCommit = $TargetCommit.Trim().ToLowerInvariant()
if ($TargetCommit -and $TargetCommit -notmatch '^[0-9a-f]{40}$') {
  throw "TargetCommit must be a full 40-character Git commit SHA."
}
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
  throw "LOCALAPPDATA is unavailable."
}

$Tag = "v$Version"
$releaseUri = "https://api.github.com/repos/$Repository/releases/tags/$Tag"
$release = Invoke-GitHubApi -Uri $releaseUri
if ([string]$release.tag_name -cne $Tag -or [bool]$release.draft) {
  throw "GitHub did not return the published release $Tag."
}

$assets = @($release.assets | Where-Object { [string]$_.name -ceq $SetupAssetName })
if ($assets.Count -ne 1) {
  throw "Release $Tag must contain exactly one $SetupAssetName asset."
}
$asset = $assets[0]
if (
  [string]$asset.state -ne "uploaded" -or
  [int64]$asset.size -le 0 -or
  [int64]$asset.size -gt $MaxSetupBytes
) {
  throw "Release asset $SetupAssetName is incomplete."
}
$assetDigest = ([string]$asset.digest).Trim().ToLowerInvariant()
if ($assetDigest -notmatch '^sha256:([0-9a-f]{64})$') {
  throw "GitHub did not provide a valid SHA-256 digest for $SetupAssetName."
}
$expectedSha256 = $matches[1]
$assetUrl = ([string]$asset.browser_download_url).Trim()
try {
  $assetUri = [Uri]$assetUrl
} catch {
  throw "GitHub returned an invalid download URL for $SetupAssetName."
}
$expectedPathPrefix = "/$Repository/releases/download/$Tag/"
if (
  $assetUri.Scheme -cne "https" -or
  $assetUri.Host -ine "github.com" -or
  -not $assetUri.AbsolutePath.StartsWith($expectedPathPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
  throw "GitHub returned an unexpected download URL for $SetupAssetName."
}

$resolvedCommit = Resolve-GitHubTagCommit -RepositoryName $Repository -Tag $Tag
if ($TargetCommit -and $resolvedCommit -ne $TargetCommit) {
  throw "Release tag $Tag resolves to $resolvedCommit instead of $TargetCommit."
}
if (-not $TargetCommit) {
  $TargetCommit = $resolvedCommit
}

$userDataDirectory = Join-Path $env:LOCALAPPDATA "CodexControlConsole"
$installationStatePath = Join-Path $userDataDirectory "cache\installation.json"
if (-not (Test-Path -LiteralPath $installationStatePath -PathType Leaf)) {
  throw "Codex Console installation state was not found: $installationStatePath"
}
$installationState = Read-JsonObject -Path $installationStatePath -Description "Codex Console installation state"
$installationId = ([string]$installationState.installationId).Trim()
$parsedInstallationId = [Guid]::Empty
if (-not [Guid]::TryParse($installationId, [ref]$parsedInstallationId)) {
  throw "Codex Console installation state has no valid installationId."
}

$publisherStatePath = Join-Path $userDataDirectory "publisher-state.json"
$verifiedAt = [DateTime]::UtcNow.ToString("o")
$downloadPath = Join-Path ([IO.Path]::GetTempPath()) ("CodexConsole-publisher-sync-{0}.exe" -f [Guid]::NewGuid().ToString("N"))
$originalProgressPreference = $ProgressPreference
$wasRunning = $false
$restartCompleted = $false
$operationError = $null
$cleanupErrors = @()

try {
  $ProgressPreference = "SilentlyContinue"
  Invoke-WebRequest -Headers $DownloadHeaders -Uri $assetUrl -OutFile $downloadPath -TimeoutSec 1800
  $downloadedSetup = Get-Item -LiteralPath $downloadPath
  if ([int64]$downloadedSetup.Length -ne [int64]$asset.size) {
    throw "The downloaded Setup size does not match GitHub's asset metadata."
  }
  $actualSha256 = (Get-FileHash -LiteralPath $downloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actualSha256 -ne $expectedSha256) {
    throw "The downloaded Setup SHA-256 does not match GitHub's digest."
  }

  $publisherState = Read-PublisherState -Path $publisherStatePath -InstallationId $installationId
  $publisherState = Set-PublisherReleaseRecord `
    -State $publisherState `
    -InstallationId $installationId `
    -RepositoryName $Repository `
    -Tag $Tag `
    -ReleaseVersion $Version `
    -Commit $TargetCommit `
    -VerifiedAt $verifiedAt `
    -LocalInstallSynchronized $false
  Write-JsonAtomically -Path $publisherStatePath -Payload $publisherState

  $installedDirectoryBefore = Get-InstalledDirectory
  $installedExecutableBefore = Join-Path $installedDirectoryBefore "Codex Console.exe"
  $wasRunning = (Get-RunningInstalledProcesses -Executable $installedExecutableBefore).Count -gt 0

  $installArguments = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/FORCECLOSEAPPLICATIONS"
  )
  $install = Start-Process -FilePath $downloadPath -ArgumentList $installArguments -Wait -PassThru
  if ($install.ExitCode -ne 0) {
    throw "Codex Console Setup failed with exit code $($install.ExitCode)."
  }

  $installedDirectory = Get-InstalledDirectory
  $installedManifestPath = Join-Path $installedDirectory "_internal\app-manifest.json"
  if (-not (Test-Path -LiteralPath $installedManifestPath -PathType Leaf)) {
    throw "The installed Codex Console manifest was not found after synchronization."
  }
  $installedManifest = Read-JsonObject -Path $installedManifestPath -Description "Installed Codex Console manifest"
  if ([string]$installedManifest.version -ne $Version) {
    throw "The installed Codex Console version is $($installedManifest.version), not $Version."
  }
  if ([string]$installedManifest.repository -ine $Repository) {
    throw "The installed Codex Console manifest belongs to a different repository."
  }

  $publisherState = Read-PublisherState -Path $publisherStatePath -InstallationId $installationId
  $publisherState = Set-PublisherReleaseRecord `
    -State $publisherState `
    -InstallationId $installationId `
    -RepositoryName $Repository `
    -Tag $Tag `
    -ReleaseVersion $Version `
    -Commit $TargetCommit `
    -VerifiedAt $verifiedAt `
    -LocalInstallSynchronized $true
  Write-JsonAtomically -Path $publisherStatePath -Payload $publisherState

  if ($wasRunning) {
    $installedExecutable = Join-Path $installedDirectory "Codex Console.exe"
    if (-not (Test-Path -LiteralPath $installedExecutable -PathType Leaf)) {
      throw "The synchronized Codex Console executable was not found."
    }
    Start-Process -FilePath $installedExecutable | Out-Null
    $restartCompleted = $true
  }

  Write-Host "Publisher installation synchronized to $Tag."
  Write-Host "Release: $($release.html_url)"
  Write-Host "Commit: $TargetCommit"
  Write-Host "SHA-256: $actualSha256"
} catch {
  $operationError = $_
} finally {
  $ProgressPreference = $originalProgressPreference
  if ($wasRunning -and -not $restartCompleted) {
    try {
      $restoreDirectory = Get-InstalledDirectory
      $restoreExecutable = Join-Path $restoreDirectory "Codex Console.exe"
      if (
        (Test-Path -LiteralPath $restoreExecutable -PathType Leaf) -and
        (Get-RunningInstalledProcesses -Executable $restoreExecutable).Count -eq 0
      ) {
        Start-Process -FilePath $restoreExecutable | Out-Null
      }
    } catch {
      $cleanupErrors += "Could not restore the previously running Codex Console: $($_.Exception.Message)"
    }
  }
  try {
    if (Test-Path -LiteralPath $downloadPath) {
      Remove-Item -LiteralPath $downloadPath -Force
    }
  } catch {
    $cleanupErrors += "Could not remove the temporary Setup: $($_.Exception.Message)"
  }
}

if ($operationError) {
  if ($cleanupErrors.Count) {
    throw "$($operationError.Exception.Message) Cleanup also failed: $($cleanupErrors -join '; ')"
  }
  throw $operationError
}
if ($cleanupErrors.Count) {
  throw ($cleanupErrors -join "; ")
}
