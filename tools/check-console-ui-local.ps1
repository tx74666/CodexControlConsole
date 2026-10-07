param(
  [string]$NodePath = "",
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = @(
  (Get-Command $Python -ErrorAction SilentlyContinue).Source,
  (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (-not $PythonPath) {
  throw "Python was not found. Install Python or use the bundled Codex runtime."
}
$Python = $PythonPath

if (-not $NodePath) {
  $NodePath = @(
    (Get-Command node -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $NodePath) {
  throw "Node.js was not found."
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()

$temporary = Join-Path $env:TEMP ("codex-console-ui-" + [guid]::NewGuid().ToString("N"))
$desktopLayoutData = Join-Path $temporary "CodexControlConsole\desktop-layout"
$desktopLayoutCurrent = Join-Path $desktopLayoutData "plans\desktop-layout-current.json"
$desktopLayoutStartup = Join-Path $temporary "Startup\RestoreDesktopLayout.vbs"
$desktopLayoutHelper = Join-Path $temporary "DesktopLayout-Test.ps1"
$desktopLayoutHelperSource = @'
param(
  [ValidateSet("save", "restore", "list")]
  [string]$Action = "list",
  [string]$Path = ""
)

$ErrorActionPreference = "Stop"
if ($Action -ne "save") {
  throw "The isolated UI test helper only supports read-only desktop capture."
}
$parent = Split-Path -Parent $Path
if ($parent) {
  New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$layout = [ordered]@{
  SavedAt = (Get-Date).ToUniversalTime().ToString("o")
  ComputerName = "UI-TEST-PC"
  UserName = "ui-test"
  IconSize = 48
  Screens = @()
  Icons = @([ordered]@{ Name = "UI Test Icon"; X = 20; Y = 30 })
}
$layout | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding UTF8
Write-Output $Path
'@
$stdout = Join-Path $temporary "server.out.log"
$stderr = Join-Path $temporary "server.err.log"
$previousData = $env:CODEX_CONTROL_DATA_DIR
$previousCloudProjects = $env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS
$previousDesktopLayoutData = $env:CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR
$previousDesktopLayoutCurrent = $env:CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT
$previousDesktopLayoutScript = $env:CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT
$previousDesktopLayoutStartup = $env:CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE
$process = $null

try {
  New-Item -ItemType Directory -Path $temporary | Out-Null
  [System.IO.File]::WriteAllText(
    (Join-Path $temporary ".cache-migrated-v0.3"),
    "test`n",
    (New-Object System.Text.UTF8Encoding($false))
  )
  [System.IO.File]::WriteAllText(
    $desktopLayoutHelper,
    $desktopLayoutHelperSource,
    (New-Object System.Text.UTF8Encoding($false))
  )

  & $Python (Join-Path $PSScriptRoot "check-download-map.py")
  if ($LASTEXITCODE -ne 0) {
    throw "Download Map checks failed with exit code $LASTEXITCODE."
  }

  & $Python (Join-Path $PSScriptRoot "check-external-app-launcher.py")
  if ($LASTEXITCODE -ne 0) {
    throw "External app launcher checks failed with exit code $LASTEXITCODE."
  }

  $env:CODEX_CONTROL_DATA_DIR = $temporary
  $env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS = "true"
  $env:CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR = $desktopLayoutData
  $env:CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT = $desktopLayoutCurrent
  $env:CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT = $desktopLayoutHelper
  $env:CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE = $desktopLayoutStartup
  $process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("world_console.py", "--host", "127.0.0.1", "--port", [string]$port, "--no-browser") `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

  $ready = $false
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
    try {
      Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/console/config" -TimeoutSec 2 | Out-Null
      $ready = $true
      break
    } catch {
      Start-Sleep -Milliseconds 100
    }
  }
  if (-not $ready) {
    $details = (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue).Trim()
    throw "The isolated Console UI service did not start. $details"
  }

  $desktopLayoutStatus = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/console/desktop-layout" -TimeoutSec 5
  if ([System.IO.Path]::GetFullPath([string]$desktopLayoutStatus.dataDirectory) -ne [System.IO.Path]::GetFullPath($desktopLayoutData)) {
    throw "The Console UI check is not using its isolated desktop-layout data directory."
  }
  if ([System.IO.Path]::GetFullPath([string]$desktopLayoutStatus.tool.path) -ne [System.IO.Path]::GetFullPath($desktopLayoutHelper)) {
    throw "The Console UI check is not using its non-destructive desktop-layout helper."
  }
  if ([System.IO.Path]::GetFullPath([string]$desktopLayoutStatus.startup.path) -ne [System.IO.Path]::GetFullPath($desktopLayoutStartup)) {
    throw "The Console UI check is not using its isolated desktop-layout startup path."
  }

  & $NodePath (Join-Path $PSScriptRoot "check-console-ui.mjs") "http://127.0.0.1:$port/"
  if ($LASTEXITCODE -ne 0) {
    throw "Console UI checks failed with exit code $LASTEXITCODE."
  }
} finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    [void]$process.WaitForExit(5000)
  }
  if ($null -eq $previousData) { Remove-Item Env:CODEX_CONTROL_DATA_DIR -ErrorAction SilentlyContinue }
  else { $env:CODEX_CONTROL_DATA_DIR = $previousData }
  if ($null -eq $previousCloudProjects) { Remove-Item Env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS -ErrorAction SilentlyContinue }
  else { $env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS = $previousCloudProjects }
  if ($null -eq $previousDesktopLayoutData) { Remove-Item Env:CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR -ErrorAction SilentlyContinue }
  else { $env:CODEX_CONTROL_DESKTOP_LAYOUT_DATA_DIR = $previousDesktopLayoutData }
  if ($null -eq $previousDesktopLayoutCurrent) { Remove-Item Env:CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT -ErrorAction SilentlyContinue }
  else { $env:CODEX_CONTROL_DESKTOP_LAYOUT_CURRENT = $previousDesktopLayoutCurrent }
  if ($null -eq $previousDesktopLayoutScript) { Remove-Item Env:CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT -ErrorAction SilentlyContinue }
  else { $env:CODEX_CONTROL_DESKTOP_LAYOUT_SCRIPT = $previousDesktopLayoutScript }
  if ($null -eq $previousDesktopLayoutStartup) { Remove-Item Env:CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE -ErrorAction SilentlyContinue }
  else { $env:CODEX_CONTROL_DESKTOP_LAYOUT_STARTUP_FILE = $previousDesktopLayoutStartup }
  $resolvedTemporary = [System.IO.Path]::GetFullPath($temporary)
  $resolvedTempRoot = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')
  if ([System.IO.Path]::GetDirectoryName($resolvedTemporary) -ne $resolvedTempRoot -or
      [System.IO.Path]::GetFileName($resolvedTemporary) -notmatch '^codex-console-ui-[a-f0-9]{32}$') {
    throw "The isolated UI cleanup target escaped its temporary directory."
  }
  Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force -ErrorAction SilentlyContinue
}
