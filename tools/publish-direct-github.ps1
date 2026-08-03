param(
  [Parameter(Mandatory = $true)]
  [string]$Version,
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [Parameter(Mandatory = $true)]
  [string]$DefenderDefinition,
  [string]$Repository = "tx74666/CodexControlConsole",
  [string]$TargetCommitish = "",
  [switch]$Prerelease,
  [switch]$SkipLocalInstall,
  [ValidateRange(1, 5)]
  [int]$UploadAttempts = 3
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must use semantic versioning, for example 1.0.2."
}
$Tag = "v$Version"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$Installer = Get-Item -LiteralPath $InstallerPath
if ($Installer.Name -ne "CodexControlConsole-Setup-x64.exe") {
  throw "The direct release must contain only CodexControlConsole-Setup-x64.exe."
}
if (-not $TargetCommitish) {
  $TargetCommitish = (& git rev-parse HEAD).Trim()
}
if ($LASTEXITCODE -ne 0 -or $TargetCommitish -notmatch '^[0-9a-f]{40}$') {
  throw "TargetCommitish must be a full Git commit SHA."
}

function Get-GitHubCredential {
  $manager = @(
    (Get-Command git-credential-manager.exe -ErrorAction SilentlyContinue).Source,
    "C:\Program Files\Git\mingw64\bin\git-credential-manager.exe"
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  if (-not $manager) {
    throw "Git Credential Manager was not found. Sign in to GitHub through Git first."
  }

  $start = New-Object System.Diagnostics.ProcessStartInfo
  $start.FileName = $manager
  $start.Arguments = "get"
  $start.UseShellExecute = $false
  $start.RedirectStandardInput = $true
  $start.RedirectStandardOutput = $true
  $start.RedirectStandardError = $true
  $process = [System.Diagnostics.Process]::Start($start)
  $process.StandardInput.Write("protocol=https`r`nhost=github.com`r`n`r`n")
  $process.StandardInput.Close()
  $raw = $process.StandardOutput.ReadToEnd()
  $errorText = $process.StandardError.ReadToEnd()
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) {
    throw "Git Credential Manager failed: $($errorText.Trim())"
  }

  $credential = @{}
  foreach ($line in ($raw -split "`r?`n")) {
    if ($line -match '^([^=]+)=(.*)$') {
      $credential[$matches[1]] = $matches[2]
    }
  }
  if (-not $credential.password) {
    throw "GitHub credentials are unavailable."
  }
  return $credential
}

function Install-PublisherCopy {
  param(
    [string]$Setup,
    [string]$ExpectedVersion
  )

  $wasRunning = [bool](Get-Process -Name "Codex Console" -ErrorAction SilentlyContinue)
  $arguments = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS"
  )
  $install = Start-Process -FilePath $Setup -ArgumentList $arguments -Wait -PassThru
  if ($install.ExitCode -ne 0) {
    throw "The local publisher installation failed with exit code $($install.ExitCode)."
  }

  $installPath = ""
  try {
    $installPath = [string](Get-ItemPropertyValue -LiteralPath "HKCU:\Software\Codex\Codex Console" -Name InstallPath)
  } catch {
    $installPath = Join-Path $env:LOCALAPPDATA "Programs\Codex Console"
  }
  $manifestPath = Join-Path $installPath "_internal\app-manifest.json"
  if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "The installed app manifest was not found after the local upgrade."
  }
  $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ([string]$manifest.version -ne $ExpectedVersion) {
    throw "The local publisher installation is $($manifest.version), not $ExpectedVersion."
  }

  if ($wasRunning) {
    $installedExe = Join-Path $installPath "Codex Console.exe"
    Start-Process -FilePath $installedExe | Out-Null
  }
  Write-Host "Publisher installation synchronized to v$ExpectedVersion."
}

$Credential = Get-GitHubCredential
$Headers = @{
  Authorization = "Bearer $($Credential.password)"
  Accept = "application/vnd.github+json"
  "X-GitHub-Api-Version" = "2022-11-28"
  "User-Agent" = "CodexConsoleDirectPublisher"
}
$Client = New-Object System.Net.Http.HttpClient
$Client.Timeout = [TimeSpan]::FromMinutes(30)
$Client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $Credential.password)
$Client.DefaultRequestHeaders.UserAgent.ParseAdd("CodexConsoleDirectPublisher")
$Client.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json")
$Client.DefaultRequestHeaders.Add("X-GitHub-Api-Version", "2022-11-28")

$Api = "https://api.github.com/repos/$Repository"
$Sha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$Signature = Get-AuthenticodeSignature -LiteralPath $InstallerPath
$SignatureNote = if ($Signature.Status -eq "Valid") {
  "The installer has a valid Authenticode signature from $($Signature.SignerCertificate.Subject)."
} else {
  "This direct GitHub installer currently has no publicly trusted Authenticode signature."
}
$Release = $null
$Published = $false

try {
  $Existing = Invoke-RestMethod -Headers $Headers -Uri "$Api/releases?per_page=100"
  if ($Existing | Where-Object { $_.tag_name -eq $Tag }) {
    throw "$Tag already exists as a GitHub Release."
  }

  $Notes = @(
    "Windows 64-bit setup for Codex Console $Version.",
    "",
    "- Preserves the built-in 16-track tiers, ordering, and 7 wallpapers.",
    "- Uses a leaner application package for faster startup.",
    "- Preserves existing user media and ordering during upgrades.",
    "- Synchronizes the publisher's local installation after publishing.",
    "",
    "Verification:",
    "- Microsoft Defender $DefenderDefinition accepted the release artifacts.",
    "- SHA-256: $Sha256",
    "- $SignatureNote"
  ) -join "`n"
  $CreatePayload = @{
    tag_name = $Tag
    target_commitish = $TargetCommitish
    name = "Codex Console $Tag"
    body = $Notes
    draft = $true
    prerelease = [bool]$Prerelease
    generate_release_notes = $false
  } | ConvertTo-Json -Depth 5
  $Release = Invoke-RestMethod `
    -Method Post `
    -Headers $Headers `
    -Uri "$Api/releases" `
    -ContentType "application/json; charset=utf-8" `
    -Body ([Text.Encoding]::UTF8.GetBytes($CreatePayload))
  Write-Host "Created draft release $($Release.id)."

  $UploadUri = "https://uploads.github.com/repos/$Repository/releases/$($Release.id)/assets?name=$([Uri]::EscapeDataString($Installer.Name))"
  $Asset = $null
  for ($attempt = 1; $attempt -le $UploadAttempts -and -not $Asset; $attempt += 1) {
    Write-Host "Uploading installer ($attempt/$UploadAttempts)..."
    $stream = $null
    $content = $null
    $request = $null
    $response = $null
    try {
      $stream = [IO.File]::Open($InstallerPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
      $content = New-Object System.Net.Http.StreamContent($stream, 1048576)
      $content.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream")
      $content.Headers.ContentLength = $Installer.Length
      $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Post, $UploadUri)
      $request.Headers.ExpectContinue = $false
      $request.Content = $content
      $response = $Client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseContentRead).GetAwaiter().GetResult()
      $responseText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
      if (-not $response.IsSuccessStatusCode) {
        throw "HTTP $([int]$response.StatusCode): $responseText"
      }
    } catch {
      Write-Warning "Upload attempt failed: $($_.Exception.Message)"
    } finally {
      if ($response) { $response.Dispose() }
      if ($request) { $request.Dispose() }
      elseif ($content) { $content.Dispose() }
      elseif ($stream) { $stream.Dispose() }
    }

    $Assets = @(Invoke-RestMethod -Headers $Headers -Uri "$Api/releases/$($Release.id)/assets?per_page=100")
    $Asset = $Assets |
      Where-Object {
        $_.name -eq $Installer.Name -and
        $_.state -eq "uploaded" -and
        [int64]$_.size -eq [int64]$Installer.Length
      } |
      Select-Object -First 1
    if (-not $Asset) {
      foreach ($badAsset in @($Assets | Where-Object { $_.name -eq $Installer.Name })) {
        Invoke-RestMethod -Method Delete -Headers $Headers -Uri "$Api/releases/assets/$($badAsset.id)" | Out-Null
      }
      if ($attempt -lt $UploadAttempts) {
        Start-Sleep -Seconds (5 * $attempt)
      }
    }
  }
  if (-not $Asset) {
    throw "GitHub did not retain a complete installer after $UploadAttempts upload attempts."
  }
  if ($Asset.digest -and $Asset.digest -ne "sha256:$Sha256") {
    throw "The GitHub asset digest does not match the local installer."
  }

  $PublishPayload = @{
    draft = $false
    prerelease = [bool]$Prerelease
    make_latest = if ($Prerelease) { "false" } else { "true" }
  } | ConvertTo-Json
  $PublishedRelease = Invoke-RestMethod `
    -Method Patch `
    -Headers $Headers `
    -Uri "$Api/releases/$($Release.id)" `
    -ContentType "application/json; charset=utf-8" `
    -Body ([Text.Encoding]::UTF8.GetBytes($PublishPayload))
  $Published = $true

  $VerifiedRelease = Invoke-RestMethod -Headers $Headers -Uri "$Api/releases/tags/$Tag"
  $VerifiedAssets = @($VerifiedRelease.assets)
  if (
    $VerifiedRelease.draft -or
    $VerifiedAssets.Count -ne 1 -or
    $VerifiedAssets[0].name -ne $Installer.Name -or
    [int64]$VerifiedAssets[0].size -ne [int64]$Installer.Length
  ) {
    throw "The published GitHub Release did not pass final verification."
  }
  if ($VerifiedAssets[0].digest -and $VerifiedAssets[0].digest -ne "sha256:$Sha256") {
    throw "The published GitHub asset digest changed after publishing."
  }

  Write-Host "Release: $($PublishedRelease.html_url)"
  Write-Host "Download: $($VerifiedAssets[0].browser_download_url)"
  Write-Host "SHA-256: $Sha256"

  if (-not $SkipLocalInstall) {
    Install-PublisherCopy -Setup $InstallerPath -ExpectedVersion $Version
  }
} catch {
  if ($Release -and -not $Published) {
    try {
      Invoke-RestMethod -Method Delete -Headers $Headers -Uri "$Api/releases/$($Release.id)" | Out-Null
      Write-Warning "Removed incomplete draft release."
    } catch {
      Write-Warning "The incomplete draft release could not be removed automatically."
    }
  }
  throw
} finally {
  $Client.Dispose()
  $Credential.Clear()
  $Headers.Clear()
}
