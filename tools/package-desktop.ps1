param(
  [string]$Version = "0.5.3",
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "build-windows.ps1") -Version $Version -OutputDir $OutputDir
