param(
  [string]$NodePath = "",
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
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
New-Item -ItemType Directory -Path $temporary | Out-Null
[System.IO.File]::WriteAllText(
  (Join-Path $temporary ".cache-migrated-v0.3"),
  "test`n",
  (New-Object System.Text.UTF8Encoding($false))
)
$stdout = Join-Path $temporary "server.out.log"
$stderr = Join-Path $temporary "server.err.log"
$previousData = $env:CODEX_CONTROL_DATA_DIR
$previousCloudProjects = $env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS
$process = $null

try {
  $env:CODEX_CONTROL_DATA_DIR = $temporary
  $env:CONSOLE_UI_ALLOW_CLOUD_PROJECTS = "true"
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
  Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
