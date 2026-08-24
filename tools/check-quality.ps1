param(
  [string]$Python = "python",
  [string]$Node = "node"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
$PythonCandidates = @()
if ($PythonCommand) {
  $PythonCandidates += $PythonCommand.Source
}
$PythonCandidates += Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$ResolvedPython = $PythonCandidates |
  Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
  Select-Object -First 1
if (-not $ResolvedPython) {
  throw "Python was not found. Install Python or use the bundled Codex runtime."
}
$Python = $ResolvedPython

$NodeCommand = Get-Command $Node -ErrorAction SilentlyContinue
$NodeCandidates = @()
if ($NodeCommand) {
  $NodeCandidates += $NodeCommand.Source
}
$NodeCandidates += Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$ResolvedNode = $NodeCandidates |
  Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
  Select-Object -First 1
if (-not $ResolvedNode) {
  throw "Node.js was not found. Install Node.js or use the bundled Codex runtime."
}
$Node = $ResolvedNode

$PythonVersionText = (& $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0) {
  throw "Could not read the Python version from $Python."
}
$NodeVersionText = (& $Node --version).Trim().TrimStart("v")
if ($LASTEXITCODE -ne 0) {
  throw "Could not read the Node.js version from $Node."
}
$PythonVersion = [version]$PythonVersionText
$NodeVersion = [version]$NodeVersionText
if ($PythonVersion -lt [version]"3.12.0") {
  throw "Python 3.12 or newer is required; found $PythonVersionText at $Python."
}
if ($NodeVersion -lt [version]"22.0.0") {
  throw "Node.js 22 or newer is required; found $NodeVersionText at $Node."
}
Write-Host "Quality runtimes: Python $PythonVersionText; Node.js $NodeVersionText"

function Invoke-QualityStep {
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

$PythonSources = @(
  "app_uninstall.py",
  "blender_github_share.py",
  "console_update.py",
  "console_window_session.py",
  "desktop_layout.py",
  "download_map.py",
  "external_app_launcher.py",
  "feedback_service.py",
  "reference_views.py",
  "world_console.py",
  "world_update.py"
)

$PythonChecks = @(
  "tools/check-release-security.py",
  "tools/check-feedback.py",
  "tools/check-release-defaults.py",
  "tools/check-console-lifecycle.py",
  "tools/check-console-update.py",
  "tools/check-world-update.py",
  "tools/check-clean-uninstall.py",
  "tools/check-wallpaper-style.py",
  "tools/check-built-in-media-sync.py",
  "tools/check-blender-github-share.py",
  "tools/check-reference-views.py",
  "tools/check-download-map.py",
  "tools/check-desktop-layout.py",
  "tools/check-external-app-launcher.py",
  "tools/check-http-boundary.py",
  "tools/check-runtime-state.py"
)

Push-Location $ProjectRoot
try {
  $RequiredFiles = @($PythonSources + $PythonChecks + @(
    "app.js",
    "tools/check-build-version.ps1",
    "tools/check-console-ui.mjs",
    "services/feedback-relay/src/index.js",
    "services/feedback-relay/test/feedback.test.js"
  ))
  foreach ($relativePath in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $relativePath -PathType Leaf)) {
      throw "Required quality-check input is missing: $relativePath"
    }
  }

  Invoke-QualityStep "Python syntax" { & $Python -m py_compile @PythonSources @PythonChecks }
  Invoke-QualityStep "Build version contracts" { & ".\tools\check-build-version.ps1" }
  foreach ($check in $PythonChecks) {
    Invoke-QualityStep $check { & $Python $check }
  }

  Invoke-QualityStep "Application JavaScript syntax" { & $Node --check app.js }
  Invoke-QualityStep "UI regression script syntax" { & $Node --check tools/check-console-ui.mjs }
  Invoke-QualityStep "UI static contracts" { & $Node tools/check-console-ui.mjs --static-only }
  Invoke-QualityStep "Feedback Worker syntax" { & $Node --check services/feedback-relay/src/index.js }
  Invoke-QualityStep "Feedback Worker tests" { & $Node --test services/feedback-relay/test/feedback.test.js }
} finally {
  Pop-Location
}

Write-Host "PASS shared lightweight project quality checks"
