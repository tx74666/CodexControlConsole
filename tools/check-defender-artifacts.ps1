param(
  [Parameter(Mandatory = $true)]
  [string[]]$Files
)

$ErrorActionPreference = "Stop"
$defenderCandidates = @(
  (Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"),
  (Get-ChildItem "C:\ProgramData\Microsoft\Windows Defender\Platform" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" })
)
$Defender = $defenderCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Defender) {
  throw "Microsoft Defender command line scanner was not found."
}

$status = Get-MpComputerStatus
if (-not $status.AntivirusEnabled) {
  throw "Microsoft Defender Antivirus is not enabled on the release runner."
}

& $Defender -SignatureUpdate -MMPC
if ($LASTEXITCODE -ne 0) {
  throw "Microsoft Defender signatures could not be updated."
}

$status = Get-MpComputerStatus
Write-Host "Microsoft Defender definitions: $($status.AntivirusSignatureVersion)"

foreach ($file in $Files) {
  $resolved = (Resolve-Path -LiteralPath $file).Path
  Write-Host "Scanning $resolved"
  & $Defender -Scan -ScanType 3 -File $resolved -DisableRemediation
  if ($LASTEXITCODE -ne 0) {
    throw "Microsoft Defender rejected $resolved with exit code $LASTEXITCODE."
  }
}

Write-Host "PASS Microsoft Defender accepted $($Files.Count) release artifact(s)"
