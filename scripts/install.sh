#!/bin/sh
# One-command Rush install (Phase 65 P65-10, F35/F42).
#
# Streamed usage: curl -fsSL <raw-url>/scripts/install.sh | sh
# No source checkout, no Python, no uv: this script only needs curl/wget,
# tar, and a sha256 tool, all of which it detects on PATH. It downloads a
# verified, self-contained `rush` release archive, installs it under a
# user-local data directory, and hands off to the installed binary's own
# `rush install` command for agent connection and (optional) project setup.
set -eu

repo="jamesdsizemore/rush-cli"

os_name=$(uname -s)
machine=$(uname -m)

case "$os_name" in
    Darwin) platform="darwin" ;;
    Linux) platform="linux" ;;
    *)
        printf 'rush install: unsupported OS: %s\n' "$os_name" >&2
        exit 1
        ;;
esac

case "$machine" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64) arch="x86_64" ;;
    *)
        printf 'rush install: unsupported architecture: %s\n' "$machine" >&2
        exit 1
        ;;
esac

asset="rush-${platform}-${arch}.tar.gz"

if [ "$platform" = "darwin" ]; then
    install_dir="${RUSH_INSTALL_DIR:-$HOME/Library/Application Support/Rush/bin}"
else
    install_dir="${RUSH_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/rush/bin}"
fi

download() {
    url=$1
    dest=$2
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$url" -O "$dest"
    else
        printf 'rush install: need curl or wget\n' >&2
        exit 1
    fi
}

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        printf 'rush install: need shasum or sha256sum\n' >&2
        exit 1
    fi
}

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

release_url="https://github.com/${repo}/releases/latest/download"
download "${release_url}/${asset}" "${work_dir}/${asset}"
download "${release_url}/SHA256SUMS" "${work_dir}/SHA256SUMS"

actual_sha=$(sha256_of "${work_dir}/${asset}")
expected_sha=$(awk -v name="$asset" '$2 == name || $2 == "*"name {print $1}' "${work_dir}/SHA256SUMS")

if [ -z "$expected_sha" ] || [ "$actual_sha" != "$expected_sha" ]; then
    printf 'rush install: checksum mismatch for %s -- refusing to install\n' "$asset" >&2
    exit 1
fi

tar -xzf "${work_dir}/${asset}" -C "$work_dir" rush

mkdir -p "$install_dir"
mv -f "${work_dir}/rush" "${install_dir}/rush"
chmod +x "${install_dir}/rush"

printf 'Installed Rush: %s/rush\n' "$install_dir"
case ":$PATH:" in
    *":$install_dir:"*) ;;
    *) printf 'Add %s to your PATH to run `rush` directly.\n' "$install_dir" ;;
esac

"${install_dir}/rush" install --agents all --memory on "$@"
