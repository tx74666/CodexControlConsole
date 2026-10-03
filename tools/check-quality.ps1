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
  "console_instance.py",
  "console_window_launcher.py",
  "desktop_layout.py",
  "document_library.py",
  "workspace_plan.py",
  "phone_companion.py",
  "phone_device_store.py",
  "phone_discovery.py",
  "phone_connection_qr.py",
  "transfer_store.py",
  "phone_offline.py",
  "device_library.py",
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
  "tools/check-console-instance.py",
  "tools/check-console-window-launcher.py",
  "tools/check-console-update.py",
  "tools/check-world-update.py",
  "tools/check-clean-uninstall.py",
  "tools/check-wallpaper-style.py",
  "tools/check-built-in-media-sync.py",
  "tools/check-blender-github-share.py",
  "tools/check-reference-views.py",
  "tools/check-download-map.py",
  "tools/check-desktop-layout.py",
  "tools/check-document-library.py",
  "tools/check-document-images.py",
  "tools/check-document-references.py",
  "tools/check-workspace-plan.py",
  "tools/check-phone-companion.py",
  "tools/check-phone-devices.py",
  "tools/check-phone-discovery.py",
  "tools/check-phone-connection-qr.py",
  "tools/check-transfer.py",
  "tools/check-phone-offline.py",
  "tools/test_device_library.py",
  "tools/check-external-app-launcher.py",
  "tools/check-http-boundary.py",
  "tools/check-runtime-state.py"
)

Push-Location $ProjectRoot
try {
  $RequiredFiles = @($PythonSources + $PythonChecks + @(
    "app.js",
    "reader.html",
    "document-reader.js",
    "document-reader.css",
    "phone-pairing.js",
    "phone-offline-export.js",
    "phone/index.html",
    "phone/app.js",
    "phone/store.js",
    "phone/styles.css",
    "phone/sw.js",
    "phone/connection-qr.js",
    "phone/vendor/jsQR.js",
    "phone/vendor/jsQR.LICENSE",
    "tools/check-connection-qr-ui.mjs",
    "phone/manifest.webmanifest",
    "tools/build-phone-static.py",
    "tools/check-phone-offline-ui.mjs",
    "mobile.html",
    "mobile.js",
    "mobile.css",
    "mobile.webmanifest",
    "tools/check-mobile-ui.mjs",
    "tools/check-document-reader.mjs",
    "tools/check-document-reader-page.mjs",
    "tools/check-document-images.mjs",
    "tools/check-document-inbox-ui.mjs",
    "tools/check-document-guide-ui.mjs",
    "tools/check-device-overview-ui.mjs",
    "tools/check-blender-documents-ui.mjs",
    "tools/check-workspace-plan-ui.mjs",
    "tools/check-workspace-plan-persistence-ui.mjs",
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

  if ($env:OS -eq "Windows_NT") {
    Invoke-QualityStep "Windows PowerShell sampler compatibility" {
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/Test-DeviceSnapshotCheckpoint.ps1
    }
  }

  Invoke-QualityStep "Application JavaScript syntax" { & $Node --check app.js }
  Invoke-QualityStep "Phone pairing JavaScript syntax" { & $Node --check phone-pairing.js }
  Invoke-QualityStep "Offline phone export JavaScript syntax" { & $Node --check phone-offline-export.js }
  Invoke-QualityStep "Offline phone JavaScript syntax" { & $Node --check phone/app.js }
  Invoke-QualityStep "Offline phone local storage syntax" { & $Node --check phone/store.js }
  Invoke-QualityStep "Offline phone service worker syntax" { & $Node --check phone/sw.js }
  Invoke-QualityStep "Phone QR scanner syntax" { & $Node --check phone/connection-qr.js }
  Invoke-QualityStep "Phone QR scanner behavior" { & $Node tools/check-connection-qr-ui.mjs }
  Invoke-QualityStep "Offline phone UI" { & $Node tools/check-phone-offline-ui.mjs }
  Invoke-QualityStep "Mobile JavaScript syntax" { & $Node --check mobile.js }
  Invoke-QualityStep "Mobile companion UI" { & $Node tools/check-mobile-ui.mjs }
  Invoke-QualityStep "Transfer JavaScript syntax" { & $Node --check transfer-panel.js }
  Invoke-QualityStep "Bidirectional transfer UI" { & $Node tools/check-transfer-ui.mjs }
  Invoke-QualityStep "Document reader JavaScript syntax" { & $Node --check document-reader.js }
  Invoke-QualityStep "Document reader opening" { & $Node tools/check-document-reader.mjs }
  Invoke-QualityStep "Document reader page behavior" { & $Node tools/check-document-reader-page.mjs }
  Invoke-QualityStep "Local document images and reader boundaries" { & $Node tools/check-document-images.mjs }
  Invoke-QualityStep "Document inbox categories and archive actions" { & $Node tools/check-document-inbox-ui.mjs }
  Invoke-QualityStep "Document library entry and curated highlights" { & $Node tools/check-document-guide-ui.mjs }
  Invoke-QualityStep "Device overview hardware and memory" { & $Node tools/check-device-overview-ui.mjs }
  Invoke-QualityStep "Blender document references and language pairing" { & $Node tools/check-blender-documents-ui.mjs }
  Invoke-QualityStep "Personal workspace plan migration" { & $Node tools/check-workspace-plan-ui.mjs }
  Invoke-QualityStep "Workspace plan persistence and phone source state" { & $Node tools/check-workspace-plan-persistence-ui.mjs }
  Invoke-QualityStep "UI regression script syntax" { & $Node --check tools/check-console-ui.mjs }
  Invoke-QualityStep "UI static contracts" { & $Node tools/check-console-ui.mjs --static-only }
  Invoke-QualityStep "Relaunch UI state" { & $Node tools/check-console-relaunch-ui.mjs }
  Invoke-QualityStep "Feedback Worker syntax" { & $Node --check services/feedback-relay/src/index.js }
  Invoke-QualityStep "Feedback Worker tests" { & $Node --test services/feedback-relay/test/feedback.test.js }
} finally {
  Pop-Location
}

Write-Host "PASS shared lightweight project quality checks"
