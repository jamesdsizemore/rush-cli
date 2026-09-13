# One-command Rush install for Windows (Phase 65 P65-10, F35/F42).
#
# Streamed usage: irm <raw-url>/scripts/install.ps1 | iex
# No source checkout, no Python, no uv: this script only needs PowerShell's
# own Invoke-WebRequest and Expand-Archive. It downloads a verified,
# self-contained `rush.exe` release archive, installs it under a user-local
# data directory, and hands off to the installed binary's own `rush install`
# command for agent connection and (optional) project setup.
$ErrorActionPreference = "Stop"

# Older Windows PowerShell (5.1) defaults to a security protocol GitHub
# rejects, which surfaces as a generic "could not create SSL/TLS secure
# channel" failure on both this fetch and the Invoke-WebRequest calls below.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

# Invoke-WebRequest's default progress-bar rendering makes large downloads
# (this archive is ~36 MB) extremely slow in Windows PowerShell 5.1 -- slow
# enough to time out or get interrupted mid-transfer, leaving a truncated
# zip that Expand-Archive then fails to open ("invalid data"). Disabling the
# progress bar restores normal download speed.
$ProgressPreference = "SilentlyContinue"

$Repo = "jamesdsizemore/rush-cli"
$Machine = $env:PROCESSOR_ARCHITECTURE
switch ($Machine) {
    "ARM64" { $Arch = "arm64" }
    "AMD64" { $Arch = "x86_64" }
    default {
        Write-Error "rush install: unsupported architecture: $Machine"
        exit 1
    }
}

$Asset = "rush-windows-$Arch.zip"
$InstallDir = if ($env:RUSH_INSTALL_DIR) { $env:RUSH_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Rush\bin" }

$WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $WorkDir | Out-Null
try {
    $ReleaseUrl = "https://github.com/$Repo/releases/latest/download"
    $ArchivePath = Join-Path $WorkDir $Asset
    $SumsPath = Join-Path $WorkDir "SHA256SUMS"

    Invoke-WebRequest -Uri "$ReleaseUrl/$Asset" -OutFile $ArchivePath
    Invoke-WebRequest -Uri "$ReleaseUrl/SHA256SUMS" -OutFile $SumsPath

    $ActualHash = (Get-FileHash -Path $ArchivePath -Algorithm SHA256).Hash.ToLower()
    $ExpectedLine = Select-String -Path $SumsPath -Pattern ([Regex]::Escape($Asset)) | Select-Object -First 1
    if (-not $ExpectedLine) {
        throw "rush install: no checksum entry for $Asset"
    }
    $ExpectedHash = ($ExpectedLine.Line -split '\s+')[0].ToLower()
    if ($ActualHash -ne $ExpectedHash) {
        throw "rush install: checksum mismatch for $Asset -- refusing to install"
    }

    Expand-Archive -Path $ArchivePath -DestinationPath $WorkDir -Force
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Move-Item -Path (Join-Path $WorkDir "rush.exe") -Destination (Join-Path $InstallDir "rush.exe") -Force
}
finally {
    Remove-Item -Path $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Installed Rush: $InstallDir\rush.exe"

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($UserPath -split ";") -notcontains $InstallDir) {
    $NewUserPath = if ([string]::IsNullOrEmpty($UserPath)) { $InstallDir } else { "$UserPath;$InstallDir" }
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Host "Added $InstallDir to your PATH. Open a new terminal to run 'rush' directly."
}
if (($env:Path -split ";") -notcontains $InstallDir) {
    $env:Path = "$env:Path;$InstallDir"
}

& (Join-Path $InstallDir "rush.exe") install --agents all --memory on @args
