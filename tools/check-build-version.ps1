param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Require {
  param(
    [bool]$Condition,
    [string]$Message
  )
  if (-not $Condition) {
    throw $Message
  }
}

function Parse-PowerShellFile {
  param([string]$Path)
  $Tokens = $null
  $ParseErrors = $null
  $Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $Path,
    [ref]$Tokens,
    [ref]$ParseErrors
  )
  Require ($ParseErrors.Count -eq 0) "PowerShell parse failed for $Path`: $($ParseErrors -join '; ')"
  return $Ast
}

function Require-Failure {
  param(
    [scriptblock]$Action,
    [string]$ExpectedMessage
  )
  $Failed = $false
  try {
    $null = & $Action
  } catch {
    $Failed = $true
    Require $_.Exception.Message.Contains($ExpectedMessage) `
      "Failure did not explain '$ExpectedMessage': $($_.Exception.Message)"
  }
  Require $Failed "Expected failure containing '$ExpectedMessage'"
}

function Require-EmptyVersionDefault {
  param(
    [System.Management.Automation.Language.ScriptBlockAst]$Ast,
    [string]$ScriptName
  )
  $Parameters = @(
    $Ast.ParamBlock.Parameters |
      Where-Object { $_.Name.VariablePath.UserPath -eq "Version" }
  )
  Require ($Parameters.Count -eq 1) "$ScriptName must define one Version parameter"
  Require ($null -ne $Parameters[0].DefaultValue) "$ScriptName Version parameter has no default"
  Require ($Parameters[0].DefaultValue.Extent.Text -eq '""') `
    "$ScriptName Version parameter must default to an empty string"
}

$BuildPath = Join-Path $ProjectRoot "tools\build-windows.ps1"
$BuildSource = Get-Content -LiteralPath $BuildPath -Raw -Encoding UTF8
$BuildAst = Parse-PowerShellFile $BuildPath
$VersionFunction = $BuildAst.Find(
  {
    param($Node)
    $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $Node.Name -eq "Resolve-BuildVersion"
  },
  $true
)
Require ($null -ne $VersionFunction) "build-windows.ps1 is missing Resolve-BuildVersion"
Invoke-Expression $VersionFunction.Extent.Text
$BundleVersionFunction = $BuildAst.Find(
  {
    param($Node)
    $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $Node.Name -eq "Assert-BundledBuildVersion"
  },
  $true
)
Require ($null -ne $BundleVersionFunction) "build-windows.ps1 is missing Assert-BundledBuildVersion"
Invoke-Expression $BundleVersionFunction.Extent.Text
$UiVersionFunction = $BuildAst.Find(
  {
    param($Node)
    $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $Node.Name -eq "Assert-UiBuildVersion"
  },
  $true
)
Require ($null -ne $UiVersionFunction) "build-windows.ps1 is missing Assert-UiBuildVersion"
Invoke-Expression $UiVersionFunction.Extent.Text

$Manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "app-manifest.json") -Raw -Encoding UTF8 |
  ConvertFrom-Json
$ManifestVersion = ([string]$Manifest.version).Trim()
Require ($ManifestVersion -match '^\d+\.\d+\.\d+$') "app-manifest.json version is invalid"
Require ((Resolve-BuildVersion -Manifest $Manifest) -eq $ManifestVersion) `
  "blank build version did not resolve from app-manifest.json"
Require ((Resolve-BuildVersion -Manifest $Manifest -RequestedVersion "v$ManifestVersion") -eq $ManifestVersion) `
  "matching explicit build version was rejected"

$Mismatch = if ($ManifestVersion -eq "9.9.9") { "9.9.8" } else { "9.9.9" }
Require-Failure `
  { Resolve-BuildVersion -Manifest $Manifest -RequestedVersion $Mismatch } `
  "does not match app-manifest.json"
Require-Failure `
  { Resolve-BuildVersion -Manifest $Manifest -RequestedVersion "not-a-version" } `
  "Version must use semantic versioning"
Require-Failure `
  { Resolve-BuildVersion -Manifest ([pscustomobject]@{ version = "v1.2.3" }) } `
  "app-manifest.json version must use semantic versioning"
Assert-BundledBuildVersion `
  -Manifest ([pscustomobject]@{ version = $ManifestVersion }) `
  -ExpectedVersion $ManifestVersion
Require-Failure `
  { Assert-BundledBuildVersion -Manifest ([pscustomobject]@{ version = $Mismatch }) -ExpectedVersion $ManifestVersion } `
  "Application bundle version $Mismatch does not match app-manifest.json version $ManifestVersion"

$UiSource = Get-Content -LiteralPath (Join-Path $ProjectRoot "app.js") -Raw -Encoding UTF8
$UiEntrySources = @{}
foreach ($EntryName in @("index.html", "music.html", "workspace.html")) {
  $UiEntrySources[$EntryName] = Get-Content -LiteralPath (Join-Path $ProjectRoot $EntryName) -Raw -Encoding UTF8
}
Assert-UiBuildVersion -Source $UiSource -ExpectedVersion $ManifestVersion -EntrySources $UiEntrySources
Require-Failure `
  { Assert-UiBuildVersion -Source ('const consoleUiVersion = "' + $Mismatch + '";') -ExpectedVersion $ManifestVersion } `
  "does not match app-manifest.json"
foreach ($InvalidSource in @('', 'const consoleUiVersion = "invalid";', ($UiSource + "`n" + $UiSource))) {
  Require-Failure `
    { Assert-UiBuildVersion -Source $InvalidSource -ExpectedVersion $ManifestVersion } `
    "must declare exactly one semantic consoleUiVersion"
}
$LegacyCacheFixture = @{
  'index.html' = '<link href="styles.css?v=console-connect-1.0.29-work-20261004"><script src="app.js?v=console-connect-1.0.29-work-20261004"></script>'
}
Require-Failure `
  { Assert-UiBuildVersion -Source 'const consoleUiVersion = "1.0.30";' -ExpectedVersion '1.0.30' -EntrySources $LegacyCacheFixture } `
  "does not include app-manifest.json version 1.0.30"
$MismatchCacheFixture = @{
  'index.html' = '<link href="styles.css?v=console-connect-1.0.30-a"><script src="app.js?v=console-connect-1.0.30-b"></script>'
}
Require-Failure `
  { Assert-UiBuildVersion -Source 'const consoleUiVersion = "1.0.30";' -ExpectedVersion '1.0.30' -EntrySources $MismatchCacheFixture } `
  "must use the same nonempty CSS and app.js cache version"
$UiGuardCall = $BuildAst.Find(
  { param($Node) $Node -is [System.Management.Automation.Language.CommandAst] -and $Node.GetCommandName() -eq 'Assert-UiBuildVersion' },
  $true
)
$RemoveBuildCall = $BuildAst.Find(
  { param($Node) $Node -is [System.Management.Automation.Language.CommandAst] -and $Node.GetCommandName() -eq 'Remove-SafeBuildDirectory' },
  $true
)
Require ($null -ne $UiGuardCall -and $null -ne $RemoveBuildCall -and
  $UiGuardCall.Extent.StartOffset -lt $RemoveBuildCall.Extent.StartOffset) `
  "UI version preflight must reject drift before removing the existing Application build"

Require-EmptyVersionDefault $BuildAst "build-windows.ps1"
Require ($BuildSource.Contains('"/DAppVersion=$Version"')) `
  "build-windows.ps1 does not pass the resolved version to Inno Setup"

$PackagePath = Join-Path $ProjectRoot "tools\package-desktop.ps1"
$PackageSource = Get-Content -LiteralPath $PackagePath -Raw -Encoding UTF8
$PackageAst = Parse-PowerShellFile $PackagePath
Require-EmptyVersionDefault $PackageAst "package-desktop.ps1"
Require ($PackageSource.Contains('-Version $Version')) `
  "package-desktop.ps1 does not forward an explicit version for mismatch validation"

$InstallerSource = Get-Content -LiteralPath (Join-Path $ProjectRoot "installer\CodexControlConsole.iss") -Raw -Encoding UTF8
Require ($InstallerSource -match '(?m)^\s*#ifndef\s+AppVersion\s*$') `
  "Inno Setup does not check for AppVersion"
Require ($InstallerSource -match '(?m)^\s*#error\s+AppVersion\b') `
  "Inno Setup does not fail when /DAppVersion is missing"
Require ($InstallerSource -notmatch '(?m)^\s*#define\s+AppVersion\b') `
  "Inno Setup still has a fallback AppVersion"

Write-Host "PASS app-manifest.json is the single Windows build-version source"
