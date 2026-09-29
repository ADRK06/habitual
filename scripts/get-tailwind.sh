#!/usr/bin/env bash
# Downloads the Tailwind CSS standalone CLI binary this project is pinned to.
# Bump VERSION here (and rebuild+commit the compiled CSS) to upgrade Tailwind.
set -euo pipefail

VERSION="v4.3.3"
REPO="https://github.com/tailwindlabs/tailwindcss/releases/download"

os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
  Darwin)
    case "$arch" in
      arm64) asset="tailwindcss-macos-arm64" ;;
      x86_64) asset="tailwindcss-macos-x64" ;;
      *) echo "Unsupported macOS architecture: $arch" >&2; exit 1 ;;
    esac
    ;;
  Linux)
    case "$arch" in
      aarch64|arm64) asset="tailwindcss-linux-arm64" ;;
      x86_64) asset="tailwindcss-linux-x64" ;;
      *) echo "Unsupported Linux architecture: $arch" >&2; exit 1 ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*)
    asset="tailwindcss-windows-x64.exe"
    ;;
  *)
    echo "Unsupported OS: $os" >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
out="$ROOT_DIR/tailwindcss"
[ "$asset" = "tailwindcss-windows-x64.exe" ] && out="$ROOT_DIR/tailwindcss.exe"

echo "Downloading $asset ($VERSION)..."
curl -sL -o "$out" "$REPO/$VERSION/$asset"
chmod +x "$out" 2>/dev/null || true

echo "Installed $out"
