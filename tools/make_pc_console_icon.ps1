$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$assets = @(
  @{ Source = "codex-resource-icon.ico"; Destination = "pc-console-icon.ico" },
  @{ Source = "codex-resource-icon-256.png"; Destination = "pc-console-icon.png" },
  @{ Source = "codex-resource-icon-32.png"; Destination = "pc-console-preview.png" }
)

foreach ($asset in $assets) {
  $source = Join-Path $projectRoot $asset.Source
  $destination = Join-Path $projectRoot $asset.Destination
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Classic Codex icon asset is missing: $source"
  }
  Copy-Item -LiteralPath $source -Destination $destination -Force
}

[pscustomobject]@{
  Icon = Join-Path $projectRoot "pc-console-icon.ico"
  Preview = Join-Path $projectRoot "pc-console-icon.png"
}
