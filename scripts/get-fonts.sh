#!/usr/bin/env bash
# Downloads the self-hosted woff2 files for the three Colonies fonts
# (Silkscreen, IBM Plex Sans, IBM Plex Mono) from Google's font CDN and
# saves them into habitual/static/fonts/, where tailwind/input.css's
# @font-face rules expect them.
#
# Every URL below is pinned to a specific, content-hashed Google Fonts
# CDN path (the same way get-tailwind.sh pins a release) - re-run this
# script any time to restore the files, and bump the URLs here (grab
# fresh ones from https://fonts.googleapis.com/css2?family=...) if a
# font needs updating.
#
# IBM Plex Sans ships upstream only as a variable font (wght 100-700),
# so one file covers our 400/500/600 weights - see the font-weight
# range in tailwind/input.css's @font-face rule for it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$SCRIPT_DIR/../habitual/static/fonts"
mkdir -p "$OUT_DIR"

# "name|url" pairs - plain array, not an associative one, so this also
# runs under macOS's stock bash 3.2 (no `declare -A` there).
FONTS=(
  "silkscreen-400.woff2|https://fonts.gstatic.com/s/silkscreen/v6/m8JXjfVPf62XiF7kO-i9YLNlaw.woff2"
  "silkscreen-700.woff2|https://fonts.gstatic.com/s/silkscreen/v6/m8JUjfVPf62XiF7kO-i9aAhAfmyi2A.woff2"
  "ibm-plex-sans-variable.woff2|https://fonts.gstatic.com/s/ibmplexsans/v23/zYXzKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1syxeKYY.woff2"
  "ibm-plex-mono-400.woff2|https://fonts.gstatic.com/s/ibmplexmono/v20/-F63fjptAgt5VM-kVkqdyU8n1i8q1w.woff2"
  "ibm-plex-mono-500.woff2|https://fonts.gstatic.com/s/ibmplexmono/v20/-F6qfjptAgt5VM-kVkqdyU8n3twJwlBFgg.woff2"
)

for entry in "${FONTS[@]}"; do
  name="${entry%%|*}"
  url="${entry#*|}"
  echo "Downloading $name..."
  curl -sL -o "$OUT_DIR/$name" "$url"
done

echo "Fonts saved to $OUT_DIR"
