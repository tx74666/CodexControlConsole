param(
  [string]$Version = "1.0.2",
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "build-windows.ps1") -Version $Version -OutputDir $OutputDir
