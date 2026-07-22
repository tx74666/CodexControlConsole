param(
  [string]$Version = "0.6.0",
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "build-windows.ps1") -Version $Version -OutputDir $OutputDir
