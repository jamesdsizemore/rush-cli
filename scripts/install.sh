#!/usr/bin/env sh
# Install Rush from this checkout with uv.
set -eu

if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'uv is required: https://docs.astral.sh/uv/' >&2
    exit 1
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
uv tool install --editable "$root"
printf '%s\n' 'Installed Rush. Run: rush --help'
