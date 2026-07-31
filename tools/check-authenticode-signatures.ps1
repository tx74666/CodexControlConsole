param(
  [Parameter(Mandatory = $true)]
  [string]$Root,
  [string[]]$Extensions = @("exe", "dll", "pyd"),
  [string[]]$RequiredRelativePaths = @()
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($Root)
if (-not (Test-Path -LiteralPath $Root)) {
  throw "Signature root does not exist: $Root"
}

$extensionSet = @{}
foreach ($extension in $Extensions) {
  $extensionSet[$extension.TrimStart('.').ToLowerInvariant()] = $true
}

$files = @(
  Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
    $extensionSet.ContainsKey($_.Extension.TrimStart('.').ToLowerInvariant())
  }
)
if ($files.Count -eq 0) {
  throw "No PE files were found under $Root"
}

foreach ($relativePath in $RequiredRelativePaths) {
  $required = Join-Path $Root $relativePath
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
    throw "Required signed file is missing: $relativePath"
  }
}

$invalid = @()
foreach ($file in $files) {
  $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
  if ($signature.Status -ne "Valid") {
    $invalid += [pscustomobject]@{
      Path = $file.FullName.Substring($Root.Length).TrimStart('\')
      Status = $signature.Status
      Message = $signature.StatusMessage
    }
  }
}

if ($invalid.Count -gt 0) {
  $invalid | Format-Table -AutoSize | Out-String | Write-Host
  throw "$($invalid.Count) PE signature(s) are missing or invalid."
}

Write-Host "PASS $($files.Count) Authenticode signatures under $Root"
