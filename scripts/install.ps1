# Install Rush from this checkout with uv.
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required: https://docs.astral.sh/uv/"
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
uv tool install --editable $Root
Write-Host "Installed Rush. Run: rush --help"
