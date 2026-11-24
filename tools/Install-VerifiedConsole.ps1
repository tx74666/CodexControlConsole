#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+$')][string]$Tag,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$Sha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$PublisherThumbprint,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -notin @('AMD64','x86') -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { throw 'Windows x64 required.' }
$name = 'CodexControlConsole-Setup-x64.exe'
$url = "https://github.com/tx74666/CodexControlConsole/releases/download/$Tag/$name"
$dir = Join-Path ([IO.Path]::GetTempPath()) ('ConsoleBootstrap-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dir | Out-Null
try {
    $file = Join-Path $dir $name
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $file
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $Sha256) { throw 'Release SHA-256 mismatch.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -ne $PublisherThumbprint) { throw 'Untrusted release publisher.' }
    if ($Install) {
        $process = Start-Process -FilePath $file -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Setup failed: $($process.ExitCode)" }
        Write-Output 'Setup exited successfully; application health verification remains required.'
    } else { Write-Output 'Release verified; no installation performed.' }
} finally {
    Remove-Item -LiteralPath $dir -Recurse -Force
}
