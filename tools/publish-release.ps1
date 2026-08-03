param(
  [string]$Version = "",
  [switch]$CheckConnection,
  [switch]$SkipChecks,
  [switch]$DirectGitHub,
  [switch]$SkipLocalInstall,
  [ValidateRange(1, 12)]
  [int]$RetryCount = 6,
  [ValidateRange(1, 60)]
  [int]$RetryDelaySeconds = 4,
  [ValidateRange(1, 60)]
  [int]$ReleaseTimeoutMinutes = 20
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Invoke-GitWithRetry {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $lastMessage = ""
  for ($attempt = 1; $attempt -le $RetryCount; $attempt += 1) {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "Continue"
      $output = & git -c http.version=HTTP/1.1 @Arguments 2>&1
      $exitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $previousErrorActionPreference
    }
    $lastMessage = ($output | Out-String).Trim()
    if ($exitCode -eq 0) {
      if ($lastMessage) { Write-Host $lastMessage }
      return
    }

    if ($attempt -lt $RetryCount) {
      Write-Warning "GitHub connection failed ($attempt/$RetryCount). Retrying in $RetryDelaySeconds seconds."
      Start-Sleep -Seconds $RetryDelaySeconds
    }
  }

  throw "git $($Arguments -join ' ') failed after $RetryCount attempts.`n$lastMessage"
}

function Invoke-CheckedCommand {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [scriptblock]$Command
  )

  Write-Host "== $Name =="
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE."
  }
}

function Remove-DirectOutput {
  param([Parameter(Mandatory = $true)][string]$Path)

  $full = [System.IO.Path]::GetFullPath($Path)
  $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
  if (
    -not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not ([System.IO.Path]::GetFileName($full)).StartsWith("dist-direct-", [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "Refusing to remove an unexpected direct-release directory: $full"
  }
  if (Test-Path -LiteralPath $full) {
    Remove-Item -LiteralPath $full -Recurse -Force
  }
}

git config http.version HTTP/1.1

if ($CheckConnection) {
  Invoke-GitWithRetry -Arguments @("ls-remote", "origin", "HEAD")
  Write-Host "GitHub connection is ready. No files were uploaded."
  exit 0
}

$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version is required and must use semantic versioning, for example 1.0.2."
}

$Tag = "v$Version"
$Manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "app-manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Manifest.version -ne $Version) {
  throw "app-manifest.json is $($Manifest.version), not $Version."
}

$Branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $Branch -ne "main") {
  throw "Release publishing must run from the main branch. Current branch: $Branch"
}

$TrackedChanges = (& git status --porcelain --untracked-files=no | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read Git status." }
if ($TrackedChanges) {
  throw "Tracked changes are not committed:`n$TrackedChanges"
}

Invoke-CheckedCommand "Capture release defaults" { python tools\capture-release-defaults.py }
$ReleaseDefaultsStatus = (& git status --porcelain -- release-defaults.json | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect release-defaults.json." }
if ($ReleaseDefaultsStatus) {
  & git add -- release-defaults.json
  if ($LASTEXITCODE -ne 0) { throw "Unable to stage release-defaults.json." }
  & git commit -m "Capture release defaults for $Tag" -- release-defaults.json
  if ($LASTEXITCODE -ne 0) { throw "Unable to commit release-defaults.json." }
}

if (-not $SkipChecks) {
  $NodePath = @(
    (Get-Command node -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  if (-not $NodePath) {
    throw "Node.js was not found. Install Node.js or use the bundled Codex runtime."
  }

  Invoke-CheckedCommand "Python syntax" { python -m py_compile world_console.py blender_github_share.py console_window_session.py console_update.py world_update.py tools\capture-release-defaults.py tools\check-release-defaults.py tools\check-built-in-media-sync.py tools\check-blender-github-share.py tools\check-console-lifecycle.py tools\check-package-footprint.py tools\check-release-security.py }
  Invoke-CheckedCommand "Release security" { python tools\check-release-security.py }
  Invoke-CheckedCommand "Release defaults" { python tools\check-release-defaults.py }
  Invoke-CheckedCommand "Built-in media sync" { python tools\check-built-in-media-sync.py }
  Invoke-CheckedCommand "Feedback service" { python tools\check-feedback.py }
  Invoke-CheckedCommand "Console lifecycle" { python tools\check-console-lifecycle.py }
  Invoke-CheckedCommand "Console updater" { python tools\check-console-update.py }
  Invoke-CheckedCommand "World updater" { python tools\check-world-update.py }
  Invoke-CheckedCommand "Clean uninstall" { python tools\check-clean-uninstall.py }
  Invoke-CheckedCommand "Wallpaper style" { python tools\check-wallpaper-style.py }
  Invoke-CheckedCommand "Blender GitHub share" { python tools\check-blender-github-share.py }
  Invoke-CheckedCommand "Console UI" {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\check-console-ui-local.ps1 -NodePath $NodePath
  }
  Invoke-CheckedCommand "Feedback relay" { & $NodePath --test services\feedback-relay\test\feedback.test.js }
}

$DirectOutputDir = Join-Path $ProjectRoot "dist-direct-$Version"
$DirectInstaller = Join-Path $DirectOutputDir "CodexControlConsole-Setup-x64.exe"
$DefenderDefinition = ""
if ($DirectGitHub) {
  Remove-DirectOutput -Path $DirectOutputDir
  Invoke-CheckedCommand "Build direct GitHub candidate" {
    & (Join-Path $PSScriptRoot "build-windows.ps1") `
      -Version $Version `
      -OutputDir $DirectOutputDir `
      -Stage All
  }
  Invoke-CheckedCommand "Verify packaged resources" { python tools\check-package-resources.py }
  Invoke-CheckedCommand "Verify clean install and media" { python tools\check-clean-install-media.py }
  Invoke-CheckedCommand "Verify lean package and startup" { python tools\check-package-footprint.py }
  Invoke-CheckedCommand "Defender scan direct release" {
    & (Join-Path $PSScriptRoot "check-defender-artifacts.ps1") -Files @(
      "build\console-installer\dist\Codex Console\Codex Console.exe",
      "build\console-installer\dist\Codex Console\_internal\tools\NativeFileDrag.exe",
      $DirectInstaller
    )
  }
  $DefenderDefinition = [string](Get-MpComputerStatus).AntivirusSignatureVersion
  if (-not $DefenderDefinition) {
    throw "Microsoft Defender definition version could not be read."
  }
}

$Head = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $Head) { throw "Unable to resolve HEAD." }

Invoke-GitWithRetry -Arguments @("push", "origin", "main")

if ($DirectGitHub) {
  $DirectPublisher = Join-Path $PSScriptRoot "publish-direct-github.ps1"
  try {
    & $DirectPublisher `
      -Version $Version `
      -InstallerPath $DirectInstaller `
      -DefenderDefinition $DefenderDefinition `
      -TargetCommitish $Head `
      -SkipLocalInstall:$SkipLocalInstall
    if ($LASTEXITCODE -ne 0) {
      throw "Direct GitHub publishing failed with exit code $LASTEXITCODE."
    }
    Remove-DirectOutput -Path $DirectOutputDir
  } catch {
    Write-Warning "The verified candidate remains at $DirectInstaller for diagnosis."
    throw
  }
  exit 0
}

$previousErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = "Continue"
  $ExistingTagCommit = (& git rev-list -n 1 $Tag 2>$null | Out-String).Trim()
  $ExistingTagExitCode = $LASTEXITCODE
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}
if ($ExistingTagExitCode -ne 0) { $ExistingTagCommit = "" }
if ($ExistingTagCommit -and $ExistingTagCommit -ne $Head) {
  throw "$Tag already points to $ExistingTagCommit instead of $Head."
}
if (-not $ExistingTagCommit) {
  & git tag -a $Tag -m "Codex Console $Tag"
  if ($LASTEXITCODE -ne 0) { throw "Unable to create $Tag." }
}

Invoke-GitWithRetry -Arguments @("push", "origin", "refs/tags/$Tag")

$ReleaseApi = "https://api.github.com/repos/tx74666/CodexControlConsole/releases/tags/$Tag"
$Deadline = (Get-Date).AddMinutes($ReleaseTimeoutMinutes)
$Headers = @{
  Accept = "application/vnd.github+json"
  "User-Agent" = "Codex-Console-Release"
}

while ((Get-Date) -lt $Deadline) {
  try {
    $Release = Invoke-RestMethod -Uri $ReleaseApi -Headers $Headers -TimeoutSec 20
    $Assets = @($Release.assets)
    if ($Assets.Count -ne 1 -or $Assets[0].name -ne "CodexControlConsole-Setup-x64.exe") {
      throw "Release exists but does not contain exactly one Windows x64 Setup."
    }
    Write-Host "Release ready: $($Release.html_url)"
    Write-Host "Download: $($Assets[0].browser_download_url)"
    exit 0
  } catch {
    Write-Host "Waiting for GitHub Actions to publish $Tag..."
    Start-Sleep -Seconds 15
  }
}

throw "Timed out waiting for $Tag. Check https://github.com/tx74666/CodexControlConsole/actions"
